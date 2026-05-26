# Alteryx Migration

Source-specific entrypoint for migrating Alteryx workflows (`.yxmd`, `.yxzp`, `.yxdb`) to a Dataiku DSS flow. Read the top-level `migration` SKILL.md first for the cross-source rules, phases, and common gotchas. This file holds only the parts that differ for Alteryx.

Pair with `dku-cli` (CLI execution) and `dataiku` (platform knowledge). When the target is a SQL connection, also read `dku-cli` skill's `references/sql-engines.md` § GREL → SQL push-down gotchas.

## Approach — job, not tool

**Avoid tool equivalency.** Map the *job to be done*, not the Alteryx tool. Several Alteryx tools collapse into a single Prepare recipe; one Alteryx tool may split into several DSS recipes; and plenty of Alteryx patterns (intermediate-dataset avoidance, desktop-style previews, manual flow layout) exist because Alteryx is desktop-first, not because the user actually needs them in DSS. Before migrating a tool, ask *what is this tool doing for the user?* — sometimes the DSS answer is "the platform already does that, no recipe needed" (record counts, intermediate-dataset visibility, schema propagation).

Corollary: when the Alteryx workflow depends on desktop-only behaviors (local file drag-drop, live dataset previews on every tool, one-screen-does-everything), call that out as an onboarding issue, not a migration gap. Point the user to DSS flow zones, flow views (record count, last build), and `dku dataset head` for the same job. Read `frictions.md` when the user pushes back on a DSS concept rather than a specific tool.

## Alteryx-specific rules

In addition to the cross-source rules in the top-level SKILL.md:

1. **An Alteryx tool is not a recipe 1:1.** One Alteryx tool often collapses into a Prepare step (Formula, AlteryxSelect, TextToColumns, RegEx, DynamicRename, RecordID, DateTime → all Prepare processors). Fan out only when the semantics genuinely differ (Join → Join, Summarize → Group, CrossTab → Pivot, Union → Stack, Sort → Sort). **Reverse direction:** several Alteryx tools also routinely collapse INTO one DSS recipe — see § Collapse triggers below. Expected ratio for a fresh migration is **3:1 to 5:1** (Alteryx tool count ÷ DSS recipe count).
2. **`GenerateRows` + equi-Join is the Alteryx workaround for range joins.** In Dataiku, prefer SQL `BETWEEN` (or Join with a conditional condition) when on a SQL engine. Off SQL, a single Prepare recipe with `ColumnSplitter` → `forRange` formula → `ArrayFold` then an equi-Join is the canonical pattern. Do NOT drop to Python. See `workflow-patterns.md`.
3. **Alteryx types are explicit; DSS inference is not.** `AlteryxSelect` carries `type="Int32"|"Double"|"V_WString"|"Date"|"DateTime"` per column. Always call `dku dataset set-schema` right after upload with the types from the AlteryxSelect metadata — don't trust DSS's STRING-for-everything CSV inference.
4. **TextInput tools in `.yxmd` are inline data.** Extract to CSV before uploading. The XML embeds rows as `<Data><r><c>…</c></r></Data>` and fields as `<Fields><Field name="…"/></Fields>`; there is no external file for these.

## Phase 1 — Parsing the source files

### `.yxmd`

Plain XML (UTF-8). `xml.etree.ElementTree.parse(f)`. Top-level shape:

```xml
<AlteryxDocument>
  <Nodes>
    <Node ToolID="N">
      <GuiSettings Plugin="…"/>
      <Properties>
        <Configuration>…</Configuration>
      </Properties>
    </Node>
    …
  </Nodes>
  <Connections>…</Connections>
</AlteryxDocument>
```

- `GuiSettings.Plugin` → tool type, e.g. `AlteryxBasePluginsGui.Formula.Formula`, `AlteryxBasePluginsGui.Join.Join`, `AlteryxBasePluginsGui.TextInput.TextInput`.
- `Properties/Configuration` → all tool parameters. Schema depends on the tool. See `translation.md`.
- `<Connections>` → DAG. Each `<Connection>` has `<Origin ToolID="X" Connection="Output|Join|Left|Right"/>` and `<Destination ToolID="Y" Connection="Input"/>`. Join tool emits three outputs: `Left` (unmatched left), `Join` (matches), `Right` (unmatched right).
- `TextBox` and `BrowseV2` plugins are presentation-only — ignore in inventory, not migratable.

### `.yxzp`

ZIP archive containing the `.yxmd` plus packaged data files. `unzip workflow.yxzp` and work from the `.yxmd` inside.

### `.yxwz`

Alteryx **Analytic App** (also called "Wizard") — same XML schema as `.yxmd` (root `<AlteryxDocument>`, same `Nodes`/`Connections`). Parse with the same `xml.etree.ElementTree` recipe as `.yxmd`. The challenge file pair often pairs `start_file.yxmd` with `solution.yxwz` rather than `solution.yxmd` — extension change is the only signal.

App-specific plugins (drop them in inventory, treat like `TextBox`/`BrowseV2`):

| Plugin | Purpose | Migration |
|---|---|---|
| `AlteryxGuiToolkit.Tab` (`Tab`) | UI tab grouping | Drop — presentation only |
| `AlteryxGuiToolkit.Questions.DropDown` / `TextBox` / `Date` / `…` (`DropDown`, `TextBox`, etc. under `Questions.*`) | User-input widget | Drop — replaced by static value, see Action below |
| `AlteryxBasePluginsGui.Action.Action` (`Action`) | Wires a widget's value into another tool's config at runtime | Drop the wiring; **substitute the user value into the target tool statically** before extracting it. The connection `(question_tool, target_tool, "Action")` shows what the widget feeds |

**Action-target value substitution.** An `Action` mutates a downstream tool (typically a `TextInput` whose 1-row content is a parameter). The default value baked into the source tool is rarely the value used to generate the documented expected output. Pick the value that the *expected output* uses — read it directly from the `BrowseV2`-attached TextInput in the solution. E.g., if Tool 60 is `Position Number=3333` (default) but expected_output rows have `Position Number=33333`, override your uploaded dataset to `33333` before building. The static migration trades parametricity for fidelity to the documented test case.

**App parametricity in DSS.** If the user wants a real "interactive lookup" surface (not just a one-off migration), the Dataiku equivalents are: Dataiku **Application Designer** (form fields → dataset filters), **project variables** + a scenario, or a **webapp**. Static migration first, then layer one of these on top — don't try to encode interactivity into the flow itself.

### `.yxdb`

Alteryx's native binary dataset format. DSS reads these natively: create a dataset on a managed folder containing the `.yxdb`, and DSS parses the schema. Caveat: `.yxdb` date/datetime fields have no timezone; by default DSS reads them as strings. Set a timezone in the dataset format config to parse as date. No need for Python / yxdb-specific libraries.

### TextInput extraction

```python
import xml.etree.ElementTree as ET, csv
root = ET.parse("workflow.yxmd").getroot()
for node in root.findall("./Nodes/Node"):
    if "TextInput" not in node.find("./GuiSettings").get("Plugin", ""):
        continue
    cfg = node.find("./Properties/Configuration")
    fields = [f.get("name") for f in cfg.findall("./Fields/Field")]
    rows = [[c.text or "" for c in r.findall("./c")] for r in cfg.findall("./Data/r")]
    with open(f"tool_{node.get('ToolID')}.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(fields); w.writerows(rows)
```

**Single-column TextInput holding comma-delimited text** (the typical "fake CSV in one column" pattern, where Field_1 contains values like `"poem text",123,'date'`): the default `.csv` write + `dku dataset upload` autodetect path **mis-parses these** — DSS picks `,` as separator, treats `"` as field quote, strips the wrapping quotes, and produces the wrong column shape (or 1 column "line" with header detection failing). Workaround: write `.tsv` (or any extension whose autodetected separator is absent from the data), then `dku dataset get-definition → set-definition` with `formatParams.separator = "\t"`, `quoteChar = ""`, `parseHeaderRow = true`, and an explicit `schema.columns: [{"name": "Field_1", "type": "string"}]`. Then split inside a Prepare recipe with `ColumnSplitter`. Note: even with `quoteChar = ""`, DSS may still strip a leading `"`-quoted segment on read — verify the parsed value with `dku dataset head -o json` before adding split steps.

**Mega-field input — DSS CSV reader has a hard 131072-byte per-field limit.** When uploading a single-row CSV whose one column holds a large blob (full HTML page, multi-page XML document, large JSON), `dku dataset head` errors with `DSSError: field larger than field limit (131072)` regardless of `formatParams.maxRowChars` (which is set to 100M by default — that's a per-row limit, not per-field). The 131072 ceiling is a CSV-reader internal limit, not configurable via dataset definition. Workaround: **pre-split the blob into multiple rows BEFORE upload**, choosing a record-level delimiter that mirrors the downstream parsing intent (e.g. split full HTML on `<h3` to get one row per doctor block; split XML on the record-wrapper tag). This is exactly what Alteryx's `TextToColumns(split-to-rows on \n)` does upstream of HTML-parse flows — pre-baking it into the Python upload prep is the DSS-friendly equivalent. Verified Challenge_040: 378-KB HTML field → split by `<h3` into 1069 doctor-block rows, each ~200-500 chars, well under the 131072 cap.

**Same trap, different separator — values containing `:` / `;` / `|` get split.** A single-column TextInput whose values contain a colon (`4:00`, `13:00` time strings, `SCC11103: Fire Warning`) or semicolon trips DSS auto-detect into picking that character as separator, producing `col_0`/`col_1` columns instead of the intended `date_time` column. Symptom: `dku dataset head` shows the value chopped at the first `:`/`;`/`|`, OR returns rows where the column-2 values are all blanks. Same fix path: `dku dataset get-definition → set-definition` with `formatParams.separator = ","`, `parseHeaderRow = true`, and explicit `schema.columns`.

**Stronger variant — DSS sometimes flips `formatType: "csv"` → `"line"` when it can't reconcile a separator.** Symptom: `dku dataset head` returns rows including the header row (the column shows up in row 1 as a literal value). Cause: DSS auto-detect fell back to single-column "one row per line" reading; the `formatParams` you supplied with `separator`/`parseHeaderRow` is silently ignored because the `line` reader doesn't use those keys. `set-definition` does NOT auto-flip `formatType` — you must explicitly set `formatType: "csv"` AND repopulate `formatParams` with the full CSV shape (`style: "excel"`, `charset: "utf-8"`, `separator: ","`, `quoteChar: '"'`, `escapeChar: "\\"`, `parseHeaderRow: true`, `skipRowsBeforeHeader: 0`, `skipRowsAfterHeader: 0`). Verify: after `set-definition`, `dku dataset get-definition <ds> -o json | jq .formatType` must show `csv` (not `line`); `dku dataset head` should return N-1 rows (header consumed) rather than N rows including the literal header.

**Stronger form of the same trap — leading `"` silently DROPS rows.** When TextInput rows themselves can start with `"` (e.g. a quote dataset where some entries begin with `"I was the best man..."`), even an explicit `quoteChar=""` does not stop DSS from treating the leading double-quote as a CSV quote and discarding rows whose internal quotes don't balance. Symptom: `dku dataset head -n 30` returns fewer rows than the source has lines (e.g. 11 of 17), and the missing rows are exactly the ones starting with `"`. Verify with `wc -l source.tsv` (lines − 1 = expected) vs `dku dataset info <ds> --recompute -o json | jq .rows`. Fix: pre-process the TSV with a Python pass that does `line.replace('"', '')` — strip ALL `"` from the data before upload. The text content is rarely sensitive to quote characters (Alteryx's TextInput preserves them but downstream string ops typically don't depend on them), and this is the only reliable way to get DSS to ingest 100% of rows. **After every re-`upload`, re-apply `set-definition`** — upload silently resets `formatParams` back to autodetected.

### External file inputs

`AlteryxBasePluginsGui.DbFileInput.DbFileInput`. The configuration has a `<File>` path. These files are usually shipped alongside the workflow; if missing, ask the user.

**`.yxdb` files (Alteryx Database) are readable from Python.** Earlier guidance assumed `.yxdb` was a closed binary format requiring Alteryx Designer to open — that is wrong. The community library [`yxdb`](https://pypi.org/project/yxdb/) (PyPI, Apache-2.0) reads `.yxdb` files directly in pure Python:

```bash
pip install yxdb
```

```python
from yxdb.yxdb_reader import YxdbReader
r = YxdbReader(path='/path/to/Result.yxdb')   # NOTE: kwarg `path=`, NOT positional
print(r.num_records)                           # row count
for f in r._fields:                            # MetaInfoField list — note the leading underscore
    print(f.name, f.data_type, f.size)        # `data_type` is "String"/"V_String"/"Int16"/"Double"/etc., NOT `type`
while r.next():                                # advance row-by-row
    for i in range(len(r._fields)):
        v = r.read_index(i)
        ...
```

API quirks (verified against `yxdb==1.0.x` on Python 3.11):
- Constructor takes `path=` kwarg or `stream=` kwarg — calling with positional raises `TypeError("either 'path' or 'stream' must be provided")`.
- Field list is `r._fields` (leading underscore — public `r.fields` attribute does not exist).
- Each field is a `MetaInfoField` with attributes `name`, `data_type`, `size`, `scale`. The type attribute is `data_type` — `f.type` raises `AttributeError`.
- Iteration: call `r.next()` (returns False at EOF) and read cells with `r.read_index(i)` — there is no `for row in r` iterator.

**Implication for blocked-with-binary-data challenges:** any prior `BLOCKED.md` entry that cites "yxdb is binary, no Python reader, can't extract ground truth" is now stale and worth a re-pick — `yxdb` solves that part. The polygon / spatial-data complaint in Challenge_027's blocker is independent of file-format readability.

The expected-output `.yxdb` shipped alongside a `.yxmd` is the **authoritative ground truth** — read it via `yxdb.YxdbReader`, walk every row, and compare against `dku dataset head -o json` of the final dataset. Do NOT trust the cached `BrowseV2` data — it can be empty and is not always present.

### Inventory shape

```
| # | Tool ID | Plugin | What It Does | Inputs | Outputs | Migratable? |
|---|---------|--------|--------------|--------|---------|-------------|
| 1 | 13 | TextInput | Customer records (2678 rows, 5 cols) | — | #29 | Yes → UploadedFiles dataset |
| 2 | 29 | TextToColumns | Split "Range" on "-" into Range1,Range2 | #13 | #30 | Yes → Prepare |
| 3 | 34 | Join | Join customers.Postal Area = ranges.Area | #13, #33 | #36 | Yes → Join recipe |
```

### Non-migratable patterns

| Alteryx pattern | Reason | Dataiku answer |
|---|---|---|
| `TextBox`, `ToolContainer` layout | GUI annotation | Ignore — use wiki / flow zone names |
| `BrowseV2` | Result viewer | Open dataset in DSS UI, or `dku dataset head` |
| `Macro` (standard) | Reusable sub-workflow | **App-as-recipe** is the closest equivalent, or inline at every call site. See `tools-io-apps-ml.md` |
| `BatchMacro` | FOR-EACH over a control dataset | **Partitioned dataset** (when split logic is data-driven), or the **scenario-loop plugin**. See `tools-io-apps-ml.md` |
| `IterativeMacro` | Until-condition loop | **Hierarchy / transitive closure** (most common — walk-up-parent, descendants-of, ancestor pairs) → **SQL recursive CTE** on any SQL connection (1 sync + 1 sql_query recipe, depth-independent). **Allocation / state-based termination** → **scenario-loop plugin**. **Else** → Python recipe. See `tools-io-apps-ml.md` |
| `Dynamic Input` | Data-driven file/query selection | **Dynamic Recipe Repeat** (native) for parametric SQL/export. **Dynamic Dataset Repeat** (native) on a managed folder + List Contents + TopN picks the latest file. See `tools-io-apps-ml.md` |
| `Detour` / "build container on condition" | Conditional flow branch | Flow Zones don't branch — use a **Split recipe** that routes all rows to one output vs. none based on a condition. See `frictions.md` |
| `AlteryxApp` (interactive prompts) | Desktop user input | Dataiku App (custom form) or project variables. See `Analytic App migration` note below |
| `Email` / `Render` / `Report*` tools | Desktop reporting | Dataiku Dashboard + Scenario reporter |
| `RunCommand` / `Python` tool (inline) | Shell / embedded Python | Python recipe or shell recipe |
| `Pre-SQL Statement` / `Post-SQL Statement` on Input/Output | Side-effect SQL | Pre/post-run scenario step or SQL recipe |

Tell the user: *"Tools #N are Alteryx infrastructure — no recipe equivalent. Dataiku equivalents: [scenarios / dashboards / apps]."*

---

## Tool → recipe quick reference

Full details in `translation.md`. This table is what to open first.

| Alteryx Tool | Dataiku Recipe | Notes |
|---|---|---|
| `TextInput` | Dataset (UploadedFiles) | Extract inline XML data to CSV, upload, set-schema |
| `DbFileInput` / `DbFileOutput` | Dataset | Map Alteryx ODBC connection → DSS SQL connection |
| `Formula` | Prepare (Formula step) | Alteryx formula → GREL; `[Field]` → bare `Field` only for valid identifiers; otherwise use `val("Field")` / `numval("Field")` / `strval("Field")` |
| `AlteryxSelect` | Prepare (ColumnRenamer, ColumnsSelector, CastType) | Rename + retype + reorder + drop — always collapses into one Prepare |
| `Filter` | Prepare (FilterOnCustomFormula) **or** Split recipe | If ONLY the True branch is consumed → Prepare filter. If BOTH branches are consumed → Split recipe with `condition` pre-computed (cleaner than two inverse filters) |
| `Sort` | Sort | |
| `Sample` | Top N | Modes: First N, Last N, Random N, Every Nth — use Top N with appropriate sort |
| `Unique` | Window + RANK=1 filter, **or** Distinct | DSS `Distinct` deduplicates on ALL columns — if Alteryx `Unique` uses a subset of columns as keys AND keeps the other columns, Distinct is wrong. Use Window: partition by the key columns, order by tiebreak, add `ROW_NUMBER`, post-filter `rank == 1` |
| `Join` | Join | Equi-join; Left/Inner/Right map directly. One recipe can emit the matched output plus two extra outputs for unmatched left and unmatched right rows ("Drop unmatched rows" → "Send unmatched rows to other output dataset(s)"). DSS also has an `antijoin` type |
| `JoinMultiple` | Chain Joins (or Python) | No native N-way join recipe |
| `AppendFields` (cartesian) | Join (type: `CROSS`) or SQL recipe | |
| `Union` | Stack | Use `schemaMode: strict` or `free`; see common-gotchas |
| `Summarize` | Group | Pass `--no-global-count` (Summarize is explicit about aggregations) |
| `CrossTab` | Pivot **or restructure to skip the pivot** | Wide pivot with value column + aggregation. ⚠ Pivot's modality scan is UI-only and `dku` cannot trigger it; even setting `pivots[0].explicitValues` doesn't populate the output's modality cache. Restructure to compute the per-modality columns inline upstream when possible. See `tools-join-reshape.md` |
| `Transpose` | Prepare `add-fold` (stock `MultiColumnFold`) **or restructure to skip the unpivot** | NEVER `pd.melt`. If `add-fold` errors with `FoldColumnsByName ... plugin not installed`, reinstall the CLI — current versions emit stock `MultiColumnFold`. Even better: most Transposes feed a downstream Group; compute the per-category aggregate per-component in a Prepare and skip the long form entirely. See `tools-join-reshape.md` |
| `MultiRowFormula` | Prepare (Formula processor with `val()` offset), up/down filler, or Window | **Prefer Prepare `val("col", default, offset)` for simple prior-row refs** (requires "Preserve ordering" on the input). "Fill empty with previous value" → up/down filler processor. Complex lag/lead/cumulative → Window recipe |
| `RunningTotal` | Window | Cumulative sum over partition |
| `RecordID` | Prepare (AddId) or Window (RowNumber) | Choose by whether order matters |
| `TextToColumns` | Prepare (`ColumnSplitter`) | `NumFields` → `limit`; delimiter → `separator`; `ColumnSplitter` auto-types numeric outputs as bigint |
| `RegEx` | Prepare (ExtractRegex / ReplaceRegex) | Mode: Parse → Extract; Replace → Replace; Tokenize → `ColumnSplitter` with `separator` as a regex |
| `DynamicRename` | Prepare (ColumnRenamer + bulk rules) | If Alteryx renames from a second input, build a Python recipe |
| `DateTime` | Prepare (DateParser, DateFormatter) | See `tools-state-parsing.md` and `dataiku` skill's prepare reference |
| `GenerateRows` | **SQL `BETWEEN`** > **`ColumnSplitter` + `forRange` + `ArrayFold`** (Prepare, any connection) > Cross-join + Filter fallback > Python (last resort) | `ArrayFold` emits one row per array element. `ArrayUnfold` is the sibling processor that expands into columns. See `workflow-patterns.md` |
| `JSONParse` | Prepare (`UnfoldObject`, `ColumnSplitter`) | For flat JSON. Deep nesting → Python |
| `Download` | Python recipe | HTTP IO has no visual recipe |
| `FindReplace` | Prepare (Find and Replace processor, "Read replacements from a dataset") | No Python needed — the Find and Replace processor has an "Advanced" mode that reads the remap table from an editable dataset. For Alteryx's whole-word-in-text replacement, fall back to Python |
| Spatial.`CreatePoints` | Prepare (Concat to WKT: `POINT(lon lat)`) or Python (shapely) | |
| Spatial.`Distance` | Prepare (GeoDistance processor) or Python (shapely) | |
| Spatial.`FindNearest` | **GeoJoin recipe** (then compute-distance) or Python (sklearn BallTree) | GeoJoin supports contains, within-distance, intersects, touches, disjoint |
| Spatial.`PolyBuild` (sequence-polyline of grouped, ordered points) | **Python (shapely) for the geometry itself** — but if the downstream is just `SpatialInfo.LengthMi` (total trip distance), skip PolyBuild entirely: Window `lag(point_wkt)` partitioned by group, ordered by sequence → Prepare with `geoDistance(point_wkt, point_wkt_lag, "MILES")` → Group `sum(leg_miles)`. 5 visual recipes, no Python. See `tools-io-apps-ml.md` |
| Spatial.`MapInput` | User-provided WKT/GeoJSON dataset | No drawing tool |
| Spatial.`Buffer` | Prepare (`create area around geopoint` processor) or `geoBuffer` GREL formula | GeoRouter plugin for routing-aware buffers |
| Spatial.`Generalize` / `Smooth` | `geoSimplify` GREL formula | |
| Spatial.`Spatial Match` (contains/intersects/touches) | GeoJoin recipe per relation, or `geoWithin`/`geoContains` GREL | GeoJoin must be one recipe per relation |
| `PearsonCorrelation` | **SQL recipe with `CORR(COALESCE(col, 0), …)`** (Sync first if input isn't on a SQL connection) | Visual-first / headless-safe path. Alteryx treats null as 0 (not pairwise complete) — wrap nullable columns in `COALESCE(col, 0)` for parity. See `tools-io-apps-ml.md` and `semantics.md`. Statistics cards are UI-only (not scenario-runnable). |

---

## Collapse triggers — running the Phase-2 collapse pass

The migration skill rule 13 ("N source steps → far fewer DSS recipes") says you must do a collapse pass after the 1:1 draft. This is the trigger list for Alteryx.

Each row below describes a pattern that appears in nearly every Alteryx workflow. If you find one in your draft, collapse it before showing the plan to the user.

| Trigger pattern in the draft | DSS collapse | Tools fused |
|---|---|---|
| `Formula → AlteryxSelect → TextToColumns → DateTime → Formula → Filter` chain — any consecutive run of single-row-transform tools | One Prepare recipe (each tool becomes a step) | N → 1 |
| `TextToColumns(delim="\s/:") → Formula(padleft each split + concat) → AlteryxSelect(drop splits) → DateTime(parse)` — the canonical Alteryx "**zero-pad date string before parse**" macro (typically wrapped in a `*.yxmc` like `DateTime_Exercise34_Solution.yxmc`). The split/padleft/concat dance exists because some Alteryx versions need zero-padded inputs to the DateTime tool. | One Prepare recipe with `DateParser → DateFormatter (overwrite source col) → DateFormatter (emit ISO datetime variant)`. DSS `DateFormatter` zero-pads natively via the format pattern (`MM/dd/yyyy HH:mm` vs source's `M/d/yyyy H:mm`); the manual splitting and padleft are redundant. See `tools-state-parsing.md`. | 4 → 1 |
| `Filter (true branch) → Group/Join/Sort → Filter` | One visual recipe with `preFilter` + `postFilter` set (rule 12) | 3 → 1 |
| `Formula (computed col) → Group/Join/Window` | One visual recipe with `computedColumns` populated (rule 12) | 2 → 1 |
| Per-input `Formula` adding a literal `source = "X"` column **before** a `Union` | `dku recipe create-stack --origin-column source` | N+1 → 1 |
| `Union → Transpose → Summarize` chain that ends in per-key aggregates | Skip the union AND the unpivot. Compute the per-key aggregates **inside each input's Prepare** with `add-formula` (one formula per output key). The inputs go directly into the next stage with their aggregate columns already populated. | union + transpose + summarize → 0 extra recipes (folded into upstream Prepares) |
| `Summarize → CrossTab` whose only purpose is to fan a per-key value into N columns for a downstream join | Compute the N columns inline upstream with `add-formula` (one per modality); skip both the summarize and the pivot. Also avoids the modality-scan blocker (see `dku-cli/references/common-gotchas.md`). | 2 → 0 |
| `CrossTab → Filter (column-existence check) → Summarize (count)` — pivot to wide, filter on "all of these columns are present", then count surviving rows | Replace with `create-group` whose `computedColumns` derives one indicator per modality (`is_food=if(MealDealItem=="Food",1,0)`) and aggregates `max(is_food/...)` per partition key. Then a SECOND `create-group` with `keys: []` (global aggregate, one output row), `computedColumns` for the existence check (`pmd=if(has_food+has_drink+has_side==N, 1, 0)`), aggregating `count(*)` for the denominator and `sum(pmd)` for the numerator. Eliminates both the Pivot recipe (which has a CLI modality-scan blocker) and the Filter recipe. | 3 → 2 |
| Alteryx `BatchMacro` whose body iterates the same op over a control parameter | DSS expresses per-key iteration as a CROSS or equi-join on the control column. The macro body (often 5–10 tools — filters, selects, appends, a formula) collapses to 1 join + 1 prepare. | macro → 2 |
| `Join → Sort → BrowseV2` (or any chain ending in `BrowseV2` / `Render`) | Drop the `BrowseV2` — UI-only, no recipe. | N → N-1 |
| `WeightedAvg.yxmc` standard macro (or any per-group `sum(x*w)/sum(w)`) | One `create-group` with `computedColumns` (`Weighted = X × W`) aggregating sum of both, then one Prepare to divide. | macro → 2 |
| Per-input `AlteryxSelect` doing ONLY a rename (different first-col names being unified before a Union) | Fold into the Union via `--origin-column` if the rename was just for source-tagging, or keep the rename as the SOLE step in each per-input Prepare. | rename + literal-add → rename only |
| `Summarize (GroupBy distinct values) → Sort DESC → Sample (First N) → RecordID → Join (back onto source on the same column)` — the canonical Alteryx "dense-rank top-N" idiom (build a `(value, rank)` lookup table for the top-N distinct values, then join the rank back onto every source row) | One `create-window` with `--compute denseRank::rank --order-key value:desc` (no partition), then one Prepare with `FilterOnNumericalRange` `rank ∈ [1, N]` + `ColumnRenamer` to fix the auto-name. The Sort/Sample/RecordID/Join chain disappears because `denseRank` is the rank-distinct-values function natively. | 5 → 2 |
| `Transpose → MultiRowFormula → CrossTab → JoinMultiple → AlteryxSelect → Transpose` (long → window → wide → join → wide → long): a round-trip whose only purpose is to attach the moving-average column(s) back to the wide row before re-melting | Compute everything in long form: fold once with imputation (`FillEmpty` per metric col + `MultiColumnFold`) → Window for the lag aggregations → Prepare for the boundary-coalesce + average → emit the final long output as a Stack of projections (one per "stream": original-metric, moving-avg-3, moving-avg-6, …). The wide-form round-trip and the JoinMultiple disappear. | 6 → 4 |
| `MultiRowFormula` with `<OtherRows>Nearest</OtherRows>` (boundary fills with the partition's first/last value) | DSS Window's natural `Lag(col, k)` returns null at the boundary — DOES NOT match. The visual answer: Window with explicit `Lag` for each offset PLUS `FirstValue` over partition, then a Prepare with `if(isBlank(strval("col_lag_k")), numval("col_first"), numval("col_lag_k"))` per offset, then the average formula. See `tools-state-parsing.md`. | (translation rule, not a tool fusion) |
| `Sort → RunningTotal → MultiRowFormula` where the MultiRowFormula references `[Row-1:RunTot_X]` (the prior row's cumsum) and `NumRows=1` — the canonical "greedy allocation" / "fill-by-priority" pattern (warehouse distribution, capacity-constrained ranking, top-K-by-budget) | The Sort is redundant — the Window recipe's `--order-key` does the ordering. The lag is redundant — algebra: `[Row-1:RunTot_X] = RunTot_X - X` (the previous cumulative is exactly the current cumulative minus the current row's contribution). One `create-window` (cumulative sum, partition + order) + one `add-formula` that references `Required_sum - Required` instead of a separate lag column. The Window's output column is `<col>_sum` (DSS hardcodes — no rename at create time; chain a `add-rename` if the downstream step really needs the Alteryx name). | 3 → 2 |
| `MultiColumnFold` step in a Prepare where the input has nulls in any folded column | Fold silently DROPS rows where the value is null. Pre-impute with `add-fill-empty` (one per folded col) BEFORE the fold step in the SAME Prepare. If the original null status is needed downstream (rare), use a sentinel-string fold pattern (`if(isBlank, "@@NULL@@", concat("", numval(col)))` per metric → fold → find-replace `@@NULL@@` → `""`). See `tools-join-reshape.md`. | (Prepare-step ordering, not a tool fusion) |
| `Formula(split ambiguous code into letter + number/suffix) → MultiRowFormula(forward-fill the suffix from the prior row when empty) → MultiRowFormula(disambiguate the letter by looking at [Row+1:letter])` — the canonical "compact-encoded sequence with positional disambiguation by neighbor" pattern (Alteryx date strings like `J07,F,M,A,M,J,J,...,J08,...` where the year appears only at January and the month letter is ambiguous between Jan/Jun/Jul, Mar/May, Apr/Aug) | ONE Window + ONE Prepare. Window: `--computed-col 'letter=substring(code,0,1):string' --computed-col 'suffix=if(length(code)>1, substring(code,1), ""):string' --order-key row_idx --compute 'max:suffix:' --rename suffix_max:suffix_filled --compute 'lead:letter:' --rename letter_lead:next_letter`. The cumulative-max-over-string trick forward-fills the year because `'' < '07' < '08'` lexicographically (works for monotonic suffixes — see `dku-cli/references/recipe-survey.md` § Window aggregation framing). Then Prepare: one cascading `add-formula` that picks the full month name from `(letter, next_letter)` pairs, plus `add-formula` for any straight column copies, plus `ColumnsSelector` to drop intermediates. | 3 → 2 (cannot go lower — the cumsum/forward-fill is fundamentally serial, but the lookahead+forward-fill+lead all fit in ONE Window) |
| `DbFileInput(.txt, no delimiter, one column per line) → Filter (drop blank/junk) → Formula (cascade-classify each line into Field=Company_Name|Address|Phone|FAX|Notes|Website) → MultiRowFormula(RecordNumber += 1 when Field=="Company_Name") → CrossTab(GroupBy=RecordNumber, Header=Field, Data=Field_1, Method=Concat) → RegEx ParseComplex (split trailing phone off Address)+ → Formula (coalesce extracted vs original) → AlteryxSelect (drop intermediate cols)` — the canonical "free-text records separated by blank lines, with positional-field-per-line layout, parse to a structured table" pattern (mailing lists, contact directories, scraped HTML rendered as plain text) | Cannot collapse below ~4 recipes — the cumsum step is fundamentally serial. Stable shape: (1) `dku dataset upload` the .txt as a CSV with `(row_idx, line)` columns (pre-baked at upload, not workflow logic). (2) **Prepare `classify`** — `add-filter-rows` (drop blank/junk) + `add-formula trim` + `add-formula Field=if(endsWith(line,"fax"),"FAX", if(match(line,/.*?(\d{3}.\d{3}.\d{4}.*)/)!=null,"Phone", if(startsWith(line,"http"),"Website", if(startsWith(line,"..."),"Notes", if(<address heuristic>,"Address","Company_Name")))))` + `add-formula is_company=if(Field=="Company_Name",1,0)`. Note GREL `match()` requires the WHOLE string to match (see `dataiku/references/formulas.md` § Regex) — anchor with `/.*?(...)/` or it silently returns null. (3) **Window `numbering`** — `--order-key row_idx --compute 'sum:is_company:' --rename is_company_sum:RecordNumber` (cumsum gives RecordNumber). The third segment of `--compute` is silently ignored; use `--rename` for output naming. (4) **Group `pivot`** — `-k RecordNumber` + 6 `--computed-col 'NAME=if(Field=="NAME",line,null):string'` (one per output column) + 6 `--agg 'NAME:concat'` (the CrossTab equivalent — DSS concat default separator is comma) + 6 `--rename 'NAME_concat:NAME'` + `--no-global-count`. (5) **Prepare `final`** — two `add-formula` steps to extract trailing phone with two regex variants (`/.*?(\d{3}-\d{3}-\d{4}.*)/` and `/.*?(1-\d{3}-\d{3}-\d{4}.*)/`; check the `1-` variant FIRST or the simpler regex eats the leading `1-`), then strip-and-coalesce into Address/Phone, then `add-step ColumnsSelector keep=false` to drop intermediates. The two RegEx ParseComplex tools become two formulas; the final Formula+AlteryxSelect fold into the same Prepare. | 8 → 4 (2:1 — below the 3:1 target, but the cumsum forces a Window between the per-row classify and the per-record pivot) |
| `DbFileInput(*.xls wildcard) → MultiRowFormula(Row=row_within_file) → Formula(if Row==K1 then col else null, if Row==K2 then col else null, …) → Summarize(GroupBy FileName, Max of each conditional col)` — the canonical Alteryx "needle-in-table" / "extract values at fixed (row, column) positions across many sheets" pattern | Pre-bake the multi-file read offline (per `tools-core.md`): one CSV with `FileName,row_idx,F1..Fn` columns, `row_idx=1..N` per file. Then ONE `create-group` with `--computed-col 'value_at_K1=if(numval("row_idx")==K1, numval("Fc1"), null):double'` per extraction (folds the Formula tool), `-k FileName --agg value_at_K1:max` (folds the Summarize), and `--rename FileName:'Display Name' --rename value_at_K1_max:Final_Name` (renames group key + aggs in one shot — `--rename` works on both, see `dku-cli/references/commands.md`). The MultiRowFormula collapses to the `row_idx` baked at conversion time. | 4 → 1 |
| `RecordID → Formula(replace delim) → TextToColumns(split-to-rows) → Unique(drop dups on RecordID) → RegEx ParseComplex (extract leading decimal) → Summarize(GroupBy RecordID, Sum)` — the canonical "**encoded-string fan-out + per-row aggregate**" pattern: a single string column packs N values per row (URL-encoded order lines, CSV-in-cell, log lines, name-value pairs glued with a delimiter) and the workflow's job is one aggregate per *original* row | **Prepare(extract row-key + SplitFold + RegexpExtractor leading-decimal + RemoveRowsOnEmpty + ColumnsSelector) → Group(sum)**. The row-key extraction (e.g. `ato\.(\d+)` for an order ID baked into the same string) replaces RecordID/Unique — preserves stable identity through the fan-out. SplitFold separator is the per-item delimiter (e.g. `atm2.`). The leading-decimal regex `^([\d.]+)` matches Alteryx ParseComplex `(\d+\.?\d*)` semantics — see `tools-state-parsing.md` for why anchoring on a closing `]` silently drops rows. The first SplitFold-emitted row per group has no number and is dropped by `RemoveRowsOnEmpty` on the regex output. | 6 → 2 |
| `RecordID + TextToColumns(split-to-rows on "<") + RegEx(ParseComplex tag/value) + MultiRowFormula(forward-fill section context) + Filter + CrossTab + AlteryxSelect(rename) + Filter(BS=="Bill") + DynamicRename(Billing_*) + Filter(BS=="Ship") + DynamicRename(Shipping_*) + Join(Bill,Ship on RecordID) + Filter(tag=="reference") on the orig branch + Join(parent,wide on RecordID) + 2× Cleanse macro` — the canonical "**XML-in-cell with N nested attributes per row, output as wide row**" pattern. Long-form decompose + per-section pivot + self-join + parent-rejoin. Typical for e-commerce XML exports (customer billing/shipping). | **One DSS Prepare recipe with N `add-formula` GREL `match()` extracts**: one formula per leaf attribute with pattern `(?s).*?<{section}>.*?<{tag}>(.*?)</{tag}>.*` (anchor on section-wrapper tag BEFORE leaf tag — without the section anchor the `.*?` first-match always lands on the Billing copy). DSS GREL `match()` runs regex against the whole cell, eliminating the long-form decompose-then-recompose. See `tools-state-parsing.md`. | 17 → 1 |
| `Replace → ReplaceFirst → TextToColumns → Sample → MultiRowFormula → CrossTab → MultiRowFormula → Formula → AlteryxSelect` chain — every tool manipulates ONE string column whose net job is "parse this structured text (HTML, JSON-as-string, XML-in-cell, CSV-in-cell) into rows" | **One Prepare recipe**, fully visual. The trick is to **split on the row-level tag, NOT the cell-level tag**. For HTML: (1) `SplitFold` separator=`<tr` (folds the input into one row per HTML row, including outer wrappers); (2) `add-filter-rows --formula 'contains(Description,"</td>") && length(split(Description,"<td>")) > 2'` (keeps only rows with two-or-more `<td>` cells, drops the prefix/placeholder/wrapper rows that have <2); (3) `RegexpExtractor` `pattern=<td>(.*?)</td>\s*<td>(.*?)</td>` `extractAllOccurrences=false` (the per-row regex non-greedy-pairs each `<td>` with its nearest `</td>` correctly because we already isolated each row — the cross-cell wrapper-eats-inner-`</td>` problem only exists when matching across the WHOLE document); (4) two `add-rename` steps `1→Name`, `2→Value` (RegexpExtractor names output cols by capture-group index); (5) `add-find-replace --column Value --find '<Null>' --replace '' --matching FULL_STRING` (preserves literal `<John Doe>`/`<2019-09-20>` cell values that share the angle-bracket shape but aren't the null sentinel); (6) `add-delete-columns --columns Description`. **Falls back to Python ONLY** when the table structure is too irregular for row-level SplitFold (rowspan/colspan, nested `<tr>` elements that aren't whole-row delimiters, mixed inline-vs-block markup). **`<br/>` vs `<br />` regex trap:** real-world HTML has both forms; use `<br\s*\/>` not `<br\/>` in regex captures, or you silently miss ~1% of rows. Same applies to any self-closing tag. Pre-bake the row-level split as a Python upload-prep step when the source is one big mega-field (DSS's 131072-byte per-field limit forces this — see § TextInput extraction "Mega-field input"). | 9 → 1 |
| `Summarize (per-partition aggregate, e.g. AvgNo0 of Units by Year-Month) → Join (back to original on the partition key, attaching the aggregate to every source row)` — the canonical Alteryx idiom for "compute a partition-wide statistic and broadcast it onto every row" (used in imputation pipelines, normalization, ratio-to-group calculations). Per-partition AVG-with-zero-exclusion uses `AvgNo0` action. | One `create-window … --frame-unbounded` with `-k <partition>` + `--computed-col 'val_no0=if(val==0, null, val):double'` (zero-exclusion lifts to a computed col since AVG ignores nulls) + `--compute 'avg:val_no0:'` + `--rename val_no0_avg:Partition_Average`. The `--frame-unbounded` flag is REQUIRED — DSS Window default is cumulative within partition (avg accumulates row-by-row), only the LAST row of each partition gets the partition-wide value; `--frame-unbounded` sets `enableLimits=true, limitPreceding/Following=false` AND the payload-level `legacyUnboundedWindowStreamBehavior=true` (without the legacy flag, DSS streams cumulatively even with limits cleared). See `dku-cli/references/recipe-survey.md` § Window aggregation framing. Multiple partition levels (e.g. monthly + annual rollups) chain as separate Window recipes (one per partition shape). | 2 → 1 (per partition level) |
| `Transpose(wide→long, key=partition) → Self-Join (Cross-join within partition by joining on partition key) → Filter [Merchant1] != [Merchant2] → RecordID → Transpose(again, key=RecordID,partition) → Sort(by Value asc) → Sort(by Name asc) → Join(by record position to align names with sorted values) → CrossTab(group=RecordID,partition; header=Name; data=Value; method=First) → Unique → AlteryxSelect(drop RecordID)` — the canonical "**all unordered pairs of items per group**" idiom (per-user merchant combos, per-document term pairs, per-customer product co-occurrences). Alteryx's 11-tool dance is reinventing C(N,2) by Transpose-then-self-join-then-sort-pairs-alphabetically-then-CrossTab-back. | **Three recipes**: (1) **Prepare** (wide→long with sentinel): N × `add-fill-empty --column M_i --value '@@EMPTY@@'` (preserves empty-cell rows that `MultiColumnFold` would otherwise DROP — see `tools-join-reshape.md`) + `add-fold --columns "M1,M2,…,MN" --key-column m_name --value-column m_val` + `add-delete-columns m_name,Count` (drop the fold-name col and any non-key columns). (2) **Self-Join**: `create-join … -i long -i long -k UserID -j INNER`, then patch payload via `set-settings`: set both `virtualInputs[i].outputColumnsSelectionMode: MANUAL`, set `selectedColumns: [{"name":"UserID","table":0,"type":"bigint"},{"name":"m_val","table":0,"alias":"left_val"},{"name":"m_val","table":1,"alias":"right_val"}]` (default `AUTO_NON_CONFLICTING` SILENTLY drops one m_val — see `dataiku/references/visual-recipe-payloads.md`), set `postFilter: {"enabled": true, "uiData": {"mode": "CUSTOM"}, "expression": "left_val < right_val"}` — strict `<` simultaneously drops self-pairs (l==r) AND deduplicates symmetric pairs (only keeps lex-ordered ones). (3) **Distinct** (`create-distinct`) — collapses the K duplicates produced when a partition has K sentinel rows that all map to the same `(@@EMPTY@@, real_merchant)` lex-sorted pair. Then **one Prepare** (often foldable into step 2 via `computedColumns` if you want 2 recipes total): two `add-find-replace --column X --find '@@EMPTY@@' --replace '' --matching FULL_STRING` to strip the sentinel + `add-rename --mappings '{"left_val":"Merchant1","right_val":"Merchant2"}'`. The Sort/Sort/Join-by-position dance is replaced by `<` lex-ordering directly; the second Transpose + CrossTab disappear because we never needed a long-form intermediate; the Unique becomes the 3rd-recipe Distinct. | 11 → 3 or 4 |
| `Join(left=A, right=lookup1) + Join(left=A, right=lookup2) → Union` — the canonical "**fork-join-union with two heterogeneous lookups**" pattern: one source dataset (e.g. draft picks) is enriched against TWO lookup tables (e.g. hitter projections, pitcher projections), each lookup producing rows with its own role-specific columns, and the two enriched outputs unioned together so each source row appears exactly once with EITHER lookup-A's or lookup-B's columns populated (the other set null). Alteryx pattern: 2 DynamicRename + 2 Formula + 2 Join + 1 Union = 7 tools. | **Stack-then-single-join.** Pre-tag each lookup with an origin column AND with the role-specific rank/key column already named for the final schema (e.g. `Hitter Rank = Rank` in prep_hitters, `Pitcher Rank = Rank` in prep_pitchers), then **Stack the lookups first** (`create-stack ... --mode UNION` — DSS Stack unions the schemas, missing columns become null in the other half), then **one Join** of the source dataset against the unioned lookup. The role-disambiguating "Hitter Rank vs Pitcher Rank" columns naturally fall out: each lookup row contributes only its column, the other is null after stack. The Union (162) is the upstream Stack; the two Joins (159, 163) become one Join. Saves 1 recipe. Tested on Challenge_029 (fantasy-baseball draft enrichment): 9 transformation tools → 6 recipes via this trick (vs 7+ without it). | 7 → 4 |
| `Sample(First 1) → Formula(extract row-0 stamp) → AppendFields(cartesian with main branch) [+ Sample(skip header rows) → DynamicRename(promote row-N as headers) → MultiRowFormula(forward-fill category) → Filter(keep data rows)]` — the canonical "**messy spreadsheet with embedded headers + global stamp + category fill-down**" pattern. Source is a copy-pasted financial/ops report where row 0 has a date or report title, rows 1–K are blank/column-header noise, and the body alternates `(category-header row, several data rows under it)` with the category text in column A and column B blank for headers but populated for data rows. The Alteryx flow stamps every data row with row-0's date (Sample+Formula+AppendFields), promotes row K's text as field names (DynamicRename), forward-fills the category (MultiRowFormula), then drops non-data rows (Filter). | **ONE Prepare recipe, fully visual.** All steps in order: (1) `add-formula --column Date --expr 'if(startsWith(F1, "Ranks as of "), substring(F1, 12), null)'` — extracts the row-0 stamp; (2) `add-step UpDownFiller --params '{"columns":["Date"],"up":false}'` — broadcasts row-0's value to all rows by filling the nulls; (3) `add-formula --column ShareClass --expr 'if(isBlank(F2) && !isBlank(F1) && !startsWith(F1,"Ranks as of"), F1, null)'` — captures the category text only on category-header rows (predicate: F1 has text, F2 blank, not the row-0 stamp); (4) `add-step UpDownFiller --params '{"columns":["ShareClass"],"up":false}'` — forward-fills category onto every data row beneath; (5) `add-filter-rows --formula '!isBlank(F2)'` — keeps only data rows (drops the date row, blank rows, and category-header rows in one go since all three have blank F2); (6) `add-rename --mappings '{"F1":"TNA","F2":"Fund","F3":"1 day", … }'` — promotes the F-name placeholders to real field names (this is what DynamicRename was doing); (7) `add-delete-columns --columns 'F6,F7,F8,row_idx'` — drop unused. **Only NULL triggers UpDownFiller** — formulas must return `null`, not `""` (see `dataiku/references/prepare-processors.md` § UpDownFiller). The cross-join branch disappears because UpDownFiller broadcasts the row-0 value inline. The DynamicRename disappears because promoting headers via column-rename is static once you've sampled the source file once. Tested on Challenge_028 (American Funds daily ranks): 49-row × 14-col messy input → 40-row × 13-col clean output, exact match. | 7–8 → 1 |
| `MultiRowFormula(forward-fill row-level group header) → RecordID → Transpose(wide→long) → Filter(drop empty cells) → Formula(extract numeric col-index from F-name) → MultiRowFormula(forward-fill ANOTHER row-level marker) → Filter(split header rows out) → AppendFields(cartesian with sub-group lookup table) → MultiRowFormula(compute end-of-range) → Filter(in-range only) → Join(metric headers on F-name) → CrossTab(group × header → wide)` — the canonical "**wide layout with structured repeating column blocks**" pattern. Source spreadsheet has K identical column-blocks repeated across the row (e.g. `(brand1: m1..mN, brand2: m1..mN, …)` for K brands × N metrics) interleaved with sparse row-level group headers (Holding Co names appearing every M rows, with their data rows below). The Alteryx flow's job is to discover the block boundaries dynamically (Transpose to long, locate column-index ranges per sub-group via AppendFields cartesian, Join on column-name to attach metric labels, CrossTab back to wide-per-block). | When the block structure is **fixed-format** (same N metrics per block, in the same order — read the row 1/row 2/row N rows once during inventory to confirm), skip the entire pivot/unpivot pair and the cartesian range-join: ONE Prepare to forward-fill the group-header column with `UpDownFiller` (returning `null` from a `CreateColumnWithGREL` step — empty string `""` is NOT a fill trigger, only `null` is) + `FilterOnCustomFormula` to keep only data rows + drop garbage groups (e.g. `Holding Co != "January 0, 1900"`); then **K per-block Prepares** (one per repeated column-block) each doing `add-rename --mappings '{"F1":"WEEK","F<start>":"DOLLARS",…,"F<start+N-1>":"AVG PRICE","holding_co_raw":"Holding Co"}'` + `add-formula --column Brand --expr '"<block-name>"'` + `add-delete-columns --columns 'F<all-other-F-cols>'`; then **one Stack** to union all blocks. The dynamic discovery, the cartesian filter, the column-name join, AND the unpivot/pivot pair all collapse together. | 12 → K+2 (typically 4–8 blocks → 6–10 recipes for what was 12+ Alteryx tools) |

---

## Alteryx-specific gotchas

Cross-source CLI / Dataiku gotchas live in `dku-cli/references/common-gotchas.md`. Alteryx *language* gotchas (null propagation, `IF THEN ELSE`, `[_CurrentField_]`, `ToString(date, format)`) live in `semantics.md`.

### Alteryx parsing

| Gotcha | Details |
|---|---|
| `.yxmd` is UTF-8 XML (unlike SAS `.egp` which is UTF-16) | Standard `ET.parse()` works |
| TextInput data is inline — no external file | Extract `<Data>` rows to CSV before upload |
| `BrowseV2` and `TextBox` are not migratable | Skip in inventory |
| Join tool has THREE outputs (Left/Join/Right) | Only wire the one(s) actually consumed downstream |
| Field names often contain spaces | Quote in GREL with `numval("Customer ID")` / `strval("Customer ID")` — DSS does NOT accept Alteryx `[brackets]` and the GREL parser rejects backticks in `create-filter` formulas (see `dku-cli/references/common-gotchas.md`) |
| `Select *Unknown` keeps/drops unseen columns | Handle upstream if schema drift matters; DSS has no "match any future column" equivalent |
| Alteryx `Null()` is the null literal in formulas | Map to GREL empty string / DSS NULL — `isnull()` in GREL |
| TextInput numeric columns with thousands separators (`1,234`) | Strip commas in Prepare before cast — Alteryx auto-coerces, DSS doesn't |

### Source-specific verification

After Phase 3 build, compare row count and a 3-row sample against the Alteryx result (either the solution `.yxmd`'s `BrowseV2` cached data, or the ground-truth CSV the user provided). If counts differ, investigate before continuing.

**The cached BrowseV2 / pre-baked ground-truth `TextInput` is the authority — NOT the recipe parameters in the solution `.yxmd`.** Challenges occasionally ship solutions whose tool params do not match the cached output (e.g. a `RegEx Replace` config says `replace="\n" with " "` but the cached output has no space — the newline was actually removed, not space-substituted; the challenge author edited the params after capturing the output). When the params and the cached output disagree, **trust the cached output**. Read the params for *what to do* (which fields, which column gets renamed where) but treat the cached values as the validation target.

### Source-specific value-mismatch debugging

| Symptom | Likely cause |
|---|---|
| Row count mismatch | Check nulls in join keys (Alteryx drops nulls by default on Inner join — DSS does too, but double-check filter conditions). Check string-vs-numeric comparisons. Check unique/distinct semantics (Alteryx `Unique` is hash-based, stable; DSS `Distinct` is too) |
| Value mismatch on decimals | Alteryx `Double` ≈ IEEE 754 but display-rounded to 6 digits by default; DSS prints full precision. Compare rounded values |
| Filter matched different rows | Alteryx `Null()` in a formula returns a true null; GREL formulas with missing inputs return empty string by default. `isnull()` and `isBlank()` are not interchangeable |

---

## Reference map

| Reference | When to read |
|---|---|
| `semantics.md` | When you need to understand *why* an Alteryx tool produces a given value — data types, null handling, formula syntax, Join's three outputs, multi-row formula window semantics |
| `translation.md` | Translation entrypoint and focused reference map |
| `tools-core.md` | TextInput, DbFile, Formula, Select, Filter, Sort, Sample, Unique |
| `tools-join-reshape.md` | Join, JoinMultiple, AppendFields, Union, Summarize, CrossTab, Transpose |
| `tools-state-parsing.md` | MultiRowFormula, RunningTotal, RecordID, TextToColumns, RegEx, DateTime |
| `tools-io-apps-ml.md` | Download, FindReplace, spatial, macros, dynamic input, yxdb, email, Excel, analytic apps, predictive tools |
| `workflow-patterns.md` | Range joins, reroutes, component-stat chains, correlation, recurring collapse patterns |
| `frictions.md` | Onboarding-level frictions: intermediate-dataset philosophy, record counts, `*Unknown` columns, build semantics, flow layout. Read when the user pushes back on a DSS concept rather than a tool |
| `../references/workflow.md` | Phase-by-phase mechanics |
| `dku-cli/references/recipe-survey.md` | Picking a recipe type |
| `dku-cli/references/common-gotchas.md` | Cross-source Dataiku/CLI gotchas |
| `dku-cli/references/flow-organization.md` | Zones, naming, wiki, descriptions |
| `dku-cli` skill's `references/sql-engines.md` | When the target connection is a SQL engine |
