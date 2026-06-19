# KNIME Migration

Source-specific entrypoint for migrating KNIME workflows (`.knwf`, `.knar`, workflow
directories) to a Dataiku DSS flow. Read the top-level `migration` SKILL.md first for the
cross-source rules and phases. This file holds only the parts that differ for KNIME.

Pair with `dku-cli` (CLI execution & platform knowledge). For workflows containing
Learner/Predictor nodes, also read `../../dku-cli/playbooks/analytics-apps.md` (visual ML)
— most KNIME ML chains collapse into one DSS ML task, not into recipes.

## Approach — job, not node

Same rule as Alteryx: **map the job to be done, not the node**. KNIME amplifies this in two
ways:

1. **KNIME is graph-maximalist.** Engine plumbing (`Table to H2O`, `H2O Local Context`,
   `Normalizer (Apply)` pairs), UI widgets (`Integer Configuration`, `Table Row to
   Variable`), and per-step type casts (`Number To String` before a Learner) are all
   first-class nodes. A large fraction of any KNIME workflow is infrastructure that has NO
   DSS equivalent because DSS does that job implicitly. Expected ratio is **3:1 to 8:1**
   (KNIME node count ÷ DSS recipe count) — higher than Alteryx because of the
   infrastructure nodes and because ML chains collapse into ML tasks.
2. **Loops are usually hyperparameter search in disguise.** `Interval Loop Start → k-Means
   → … → Loop End` is a k grid. `Parameter Optimization Loop Start/End` around a threshold
   rule is cut-off optimization. DSS visual ML does both natively (k list on the clustering
   algorithm; threshold optimization on a metric). Do NOT migrate these loops as scenario
   loops or Python — delete them and configure the grid on the ML task.

## KNIME-specific rules

1. **Learner + Predictor + Scorer (+ Partitioning) is ONE DSS ML task**, not 4 recipes.
   Partitioning before a Learner → the ML task's train/test split policy
   (`dku ml set-split A M --train-ratio 0.7`). The Predictor on the held-out partition and
   the Scorer → DSS computes holdout metrics natively. `Model Writer` → the deployed saved
   model in the flow. A separate "Deployment" workflow reading the model (`Model Reader` +
   `Predictor`) → one scoring recipe against the same saved model.
2. **Rule Engine immediately after a Predictor is a classification threshold**, not a
   recipe. `$P (Class=1)$ > 0.3 ⇒ "1"` → `dku model set-threshold SAVED_MODEL 0.3`. Only
   translate Rule Engine to a Prepare step when it encodes real business rules.
3. **Type-cast nodes before Learners usually vanish.** `Number To String` on the target
   exists because KNIME learners need a nominal target; DSS classification accepts numeric
   class columns. `String To Number` after a Rule Engine exists because Rule Engine emits
   strings. Check the consumer before migrating any cast node.
4. **Configuration nodes are project variables.** `Integer/String/Double Configuration` →
   `dku project set-variables PROJ --set name=value`. If the user wants the interactive
   surface, that's a Dataiku App on top — static variables first.
5. **Annotations are zone names.** `workflow.knime` annotations ("Read and filter data",
   "Model Training") map to `dku flow create-zone` + `dku flow move --type AUTO`. Metanode
   names are also good zone names.

## Phase 1 — Parsing the source files

### Container formats (all ZIPs)

| Extension | Contents |
|---|---|
| `.knwf` | ZIP, one top-level folder = one workflow |
| `.knar` | ZIP, several workflow folders |
| `.table` | KNIME native table — ALSO a zip: `spec.xml` (schema), `meta.xml` (row count), `data.bin` (gzip rows) |
| Model Writer `.zip` | KNIME-internal serialized model — NOT portable, retrain in DSS |

### Workflow directory layout

```
<Workflow>/
├── workflow.knime              # the DAG: nodes + connections + annotations
├── workflow.svg                # rendered preview — open it first for orientation
├── data/                       # the knime.workflow.data area: source files readers
│   │                           # reference, Model Writer outputs, AND any outputs the
│   │                           # executed run wrote = your ground truth
├── <Node Name> (#<id>)/settings.xml          # one folder per node
└── <Metanode Name> (#<id>)/workflow.knime    # metanodes nest recursively
```

### workflow.knime

Generic KNIME Config XML, namespace `http://www.knime.org/2008/09/XMLConfig`. Everything is
`<config key>` + `<entry key type value>`:

- `config[nodes]/config[node_N]`: `id`, `node_settings_file`, `node_is_meta`, `node_type`
  (`NativeNode` | `MetaNode` | `SubNode`).
- `config[connections]/config[connection_N]`: `sourceID`, `destID`, `sourcePort`,
  `destPort`. Port `-1` = metanode boundary.
- `config[annotations]`: zone labels and notes. `%%00010` = newline escape.
- `entry[state]`: `EXECUTED` means the `data/` outputs are real run results.

MetaNode → `node_settings_file` points at a nested `workflow.knime`; recurse. SubNode
(Component) wraps an inner workflow one directory down with `VirtualSubNodeInput/Output`
boundary nodes — treat those two as wiring, not steps.

### settings.xml (per node)

- `entry[factory]` = Java factory class — **the node-type key for translation** (e.g.
  `org.knime.base.node.preproc.filter.column.DataColumnSpecFilterNodeFactory`).
- `config[model]` = all parameters, recursively.
- `config[flow_stack]` = flow-variable values at save time — the *executed* parameter
  values, which may differ from the dialog defaults in `model`. When they disagree about a
  loop range or a parameter, **trust `flow_stack` / the ground-truth output**, not the
  dialog value (same authority rule as Alteryx's cached BrowseV2).
- Column filters: `included_names`/`excluded_names` arrays. `enforce_option:
  EnforceExclusion` = keep-unseen-columns (like Alteryx `*Unknown` — DSS has no equivalent;
  pin the explicit list).
- File readers: `model/…/path` with `file_system_specifier: knime.workflow.data` → the file
  is in `data/` inside the archive.

### Parser

~60 lines of `xml.etree.ElementTree` produce the full inventory; no library needed:

```python
import xml.etree.ElementTree as ET
from pathlib import Path
NS = {"k": "http://www.knime.org/2008/09/XMLConfig"}

def entries(cfg):
    return {e.get("key"): e.get("value") for e in cfg.findall("k:entry", NS)}

def parse(wf_dir, prefix=""):
    root = ET.parse(wf_dir / "workflow.knime").getroot()
    nodes, conns = [], []
    for n in root.find("k:config[@key='nodes']", NS).findall("k:config", NS):
        ne = entries(n)
        nid, rel = prefix + ne["id"], ne["node_settings_file"]
        if ne.get("node_is_meta") == "true":
            nodes.append((nid, (wf_dir / rel).parent.name, "(metanode)"))
            sub_n, sub_c = parse((wf_dir / rel).parent, prefix=nid + ":")
            nodes += sub_n; conns += sub_c
        else:
            s = entries(ET.parse(wf_dir / rel).getroot())
            nodes.append((nid, s.get("name"), s.get("factory")))
    for c in root.find("k:config[@key='connections']", NS).findall("k:config", NS):
        ce = entries(c)
        conns.append((prefix + ce["sourceID"], prefix + ce["destID"]))
    return nodes, conns
```

Drill into a node's parameters by parsing its `settings.xml` `config[model]` subtree the
same way.

### Reading `.table` ground truth (single rows / small tables)

`data.bin` inside the `.table` zip is gzip. After a length-prefixed row key, cells follow
as `a\x82` + 8-byte big-endian IEEE-754 double or `a\x83` + length-prefixed UTF-8 string.
For one-row deployment inputs it is usually faster to find the row in the source CSV: the
KNIME row key (`Row83937`) is the 0-based row index of the source dataset. For larger
`.table` files, ask the user to export CSV from KNIME instead of writing a decoder.

### Inventory shape

```
| # | Node ID | Factory (short) | What It Does | Inputs | Outputs | Migratable? |
|---|---------|-----------------|--------------|--------|---------|-------------|
| 1 | 57 | CSVTableReader | creditcard.csv (284807 rows, 31 cols) | — | #58 | Yes → UploadedFiles dataset |
| 2 | 58 | NumberToString2 | Class → string (learner ceremony) | #57 | #34 | Drop — DSS accepts numeric target |
| 3 | 34 | Partition | stratified 70/30 split | #58 | #35,#36 | Yes → ML task split policy |
```

Metanode children get prefixed IDs (`59:44`); list them inline under the parent and
reuse the metanode name as the flow-zone name.

## Collapse triggers — running the Phase-2 collapse pass

The migration skill's Phase-2 rule ("N source steps → far fewer DSS recipes") sends you
here after the 1:1 draft. These patterns appear in nearly every KNIME workflow:

| Draft pattern | Collapse |
|---|---|
| Reader → cast → Partitioning → Learner → Predictor → Scorer → Model Writer | Dataset + ONE ML task (+ deploy). 6–7 → 1 |
| Any `Normalizer`/`Apply` pair feeding ML only | Fold into ML task rescaling. 2 → 0 |
| Consecutive single-row transforms (Column Filter, Rename, String Manipulation, Math Formula, Rule Engine-as-rules) | One Prepare, one step each. N → 1 |
| `X To Variable → CASE/loop` chains | Scenario constructs. N → 0 recipes |
| `Metanode` boundary | NOT a recipe boundary — inline its nodes into the parent inventory, use the metanode name as a flow-zone name |
| Loop Start/End around an ML parameter | Algorithm grid. N → 0 |

Sanity ratio for the Phase-2 plan: **≥3:1** nodes→recipes; ML-heavy workflows reach 8:1
(fraud sample: 13 nodes + 5-node metanode → 1 prepare-less ML task + 2 recipes + 1 scenario).

## Non-migratable / infrastructure patterns

| KNIME pattern | Reason | Dataiku answer |
|---|---|---|
| `Table to H2O`, `H2O to Table`, `H2O Local Context` | Engine plumbing | Drop — DSS manages engines |
| `Normalizer` + `Normalizer (Apply)` pair around ML | Manual feature rescaling | `dku ml set-feature A M <col> --rescaling AVGSTD` (or NONE when KNIME had no Normalizer) |
| `Number To String` / `String To Number` before/after ML nodes | KNIME type ceremony | Usually drop (rule 3) |
| `Integer/String Configuration`, `Table Row to Variable`, `Variable to Table Column` | Flow-variable plumbing | Project variables |
| `Data to Report`, BIRT `.rptdesign`, `Text Output Widget` | Legacy reporting | Dashboard + insights |
| `Timer Info` + `Math Formula` on it | Latency measurement | Drop — DSS job metrics |
| `Cache` | Performance hint | Drop — datasets are materialized |
| `CASE Switch` + `Send Email` | Conditional alerting | Scenario: build step + conditional email reporter |
| Keras layer nodes (`DLKeras*`) | Layer-by-layer visual DL (deprecated in KNIME 5 too) | Python recipe with a Keras/TF code env, or DSS Deep Learning; flag for redesign |
| `Python Script` node | Embedded code | Python recipe (copy the script; KNIME `input_table_1` → `dataiku.Dataset.get_dataframe()`) |
| Loop Start/End around ML parameters | Hyperparameter search | ML task grid (rule "loops", above) |
| `Chunk Loop`, `Group Loop` over data | Batch iteration | Usually a Group/Window/Join restructure; scenario-loop only if genuinely iterative |

## Verification

- `state=EXECUTED` workflows ship their outputs in `data/` — that is the parity target.
  Compare row counts and values with `dku dataset head -o json` after each functional unit.
- k-Means parity is **approximate by design**: KNIME uses `FIRST_ROWS` init capped at
  `maxNrIterations=10` (often unconverged); DSS sklearn uses converged k-means++. Compare
  segment interpretation (sizes, centroid ordering), not exact assignments. See
  `semantics.md`.
- RF/classifier parity: compare holdout AUC/confusion within tolerance, not tree-identical
  predictions (different RNG, different missing-value handling).

## Reference map

| Reference | When to read |
|---|---|
| `translation.md` | Node → DSS mapping table + collapse triggers |
| `semantics.md` | Why a KNIME value differs: k-means init, partitioning, thresholds, flow variables |
| `../references/workflow.md` | Phase-by-phase mechanics |
| `../../dku-cli/playbooks/tabular-flow.md` | Recipe-type choice, CLI traps |
| `../../dku-cli/playbooks/analytics-apps.md` | Visual ML: create/train/deploy/score via CLI |
