# SAS Migration

Source-specific entrypoint for migrating SAS programs (`.sas`, `.egp`, `.flw`) to a Dataiku DSS flow. Read the top-level `migration` SKILL.md first for the cross-source rules, phases, and common gotchas. This file holds only the parts that differ for SAS.

Pair with `dku-cli` (CLI execution) and `dataiku` (platform knowledge). When the target is a SQL connection, also read `dku-cli`'s `playbooks/tabular-flow.md` and `references/formulas.md` § GREL → SQL push-down.

- [SAS-specific rules](#sas-specific-rules)
- [Phase 1 — Parsing the source files](#phase-1--parsing-the-source-files) — `.sas` / `.egp` / `.flw` / `.sas7bdat`, macro variables, `%include`, non-migratable patterns
- [Collapse triggers](#collapse-triggers--running-the-phase-2-collapse-pass)
- [SAS-specific gotchas](#sas-specific-gotchas) — verification, value-mismatch debugging
- [Reference map](#reference-map)

## SAS-specific rules

In addition to the cross-source rules in the top-level SKILL.md:

1. **DATA step ≠ Python recipe.** Most DATA steps decompose into Prepare (filter / rename / compute) + Join (`MERGE`) + Group / Window (RETAIN). `merge X(in=a) Y(in=b); by k; if a;` is a LEFT JOIN. `if a and b;` is INNER. Going to Python is almost always premature.
2. **`PROC FORMAT` inlines into a formula.** No separate format artifact. `put(var, spend_tier.)` with `low-500='Low'` → nested `if()`. See `procs.md` § PROC FORMAT range notation.

## Phase 1 — Parsing the source files

### `.sas`

Read directly. Follow every `%include` chain. Embedded `datalines;` blocks are test data, not production input. `%macro` bodies are not the unit of migration; what the macro *generates* at each call site is. `libname` → Dataiku connection.

### `.egp` (Enterprise Guide project)

ZIP archive. Extract with `unzip project.egp`. Inside:

- **Encoding rule:** `project.xml` is **UTF-16** — `open(f, 'rb').read().decode('utf-16')`; plain `open(f)` garbles it. Every other XML / log file in the bundle (`EGTask-*/*.xml`, `Query-*/Log-*/result.log`, `ImportTask-*/*.xml`, `CodeTask-*/*.xml`) is **UTF-8 with a BOM** — use `open(f, encoding='utf-8-sig')`. Defaulting to `utf-16` for the whole bundle yields CJK glyphs (`믯㲿砿汭瘠牥楳湯`); defaulting to `utf-8` chokes on the BOM.
- `<Element><Type>CONTAINER</Type>` → process flow groups.
- `<Element><Type>TASK</Type>` → executable tasks.
- `CodeTask-*/code.sas` — read directly.
- `Query-*/Log-*/result.log` — Query Builder tasks have NO `.sas` file; the generated SQL is in the log, prefixed with `s`.
- `ImportTask-*/*.xml` — CSV field mappings.
- `EGTask-*/*.xml` — EG-native task definitions (Summary Statistics / Table Analysis / Bar Chart / Forecast / etc.). Read `<Task name="…" asm="SAS.EG.Tasks.<Family>">` for the task type; the XML lists role variables (`<Var name=… cls='DatasetColumn'/>`), BY groups (`<Role name='RoleCLASS'>`), and dataset bindings. There is no `.sas` file (EG generates the code on submit) but the task intent is fully encoded in the XML — translate it like any other task, never stub it as a placeholder. Common families: `SAS.EG.Tasks.Describe` (PROC MEANS / FREQ / UNIVARIATE), `SAS.EG.Tasks.GraphBar`, `SAS.EG.Tasks.Forecast`.

### `.flw` (SAS Studio flow)

JSON, not XML. `json.load(f)`. `flow['nodes']` → sub-flows; each node has `dataFlowAndBindings.dataFlow.{nodes,connections}`. Node `nodeType`: `step`, `table`, `outputTable`.

### `.sas7bdat` source tables

DSS does not upload `.sas7bdat` directly — convert to CSV first via pandas, then upload. SAS stores all numerics as `double`, so pandas `read_sas` returns `id=1077430.0` (float); a later `dku dataset set-schema id:bigint` silently nulls every value and downstream joins produce zero rows — cast id-like columns to nullable `Int64` before writing the CSV:

```python
import pandas as pd, numpy as np
df = pd.read_sas('source.sas7bdat')
# datetime first (must run before Int64 cast — np.issubdtype rejects pandas extension dtypes)
for c in df.columns:
    try:
        if np.issubdtype(df[c].dtype, np.datetime64):
            df[c] = df[c].dt.strftime('%Y-%m-%d')
    except TypeError:
        pass
# nullable int for join keys / class targets
for c in ['id', 'member_id', 'loan_status']:
    if c in df.columns:
        df[c] = df[c].astype('Int64')   # capital I — pandas nullable int
# bytes → str
for c in df.select_dtypes(include=['object']).columns:
    df[c] = df[c].apply(lambda v: v.decode('utf-8','replace') if isinstance(v, bytes) else v)
df.to_csv('source.csv', index=False)
```

After `dku dataset upload + set-schema`, sanity-check with `dku --format json dataset head <ds> -P PROJ -n 3` and confirm the id values are populated (not `null`). If they're null, the float-formatted-to-bigint silent cast happened — re-run the conversion with the `Int64` cast in place.

### Python-in-SAS

`proc python; submit; ... endsubmit;` blocks. Extract the code between `submit;` / `endsubmit;`, migrate to a Python recipe. Ignore the SAS-side bridge.

### PROC SQL passthrough — translate the body

`proc sql; connect to <engine> as remote (...); create table X as select ... from connection to remote(...); quit;` is SAS pass-through to a remote engine. The SELECT body is real flow logic (joins, filters, projections, aggregates) and must be migrated like any other set of operations — never stubbed as a header-only "warehouse delivers this" placeholder, regardless of whether the warehouse is reachable from DSS.

Translate the body into one or more recipes against the equivalent DSS-side connection. The recipe-type choice follows the usual rules: a single SQL recipe when the body needs `LAG`/`ROW_NUMBER`/`PERCENTILE_CONT` / multi-CTE push-down that visual recipes don't expose; otherwise visual recipes (Join, Group, Filter, Distinct, …) — same as any other DATA / PROC step. When the original warehouse is reachable as a Dataiku connection, point the recipes at it directly so push-down survives end-to-end (one engine per flow). When it isn't, the translation is unchanged; only the input wiring differs.

### SAS macro variables → DSS project variables

Macro variables that vary per run (`&day_M12.`, `&day_M1.`, `&run_id.`, region selectors) map directly to **DSS project variables**:

```bash
dku project set-variables -P PROJ --set day_M1=2024-12-01 --set day_M12=2024-01-01
```

**`${var}` expands inside GREL** (string substitution before parse) — same as in SQL recipes and dataset names. Quote it for strings/dates; bare for numerics:

```bash
dku recipe add-formula prep --column tenure_m \
    --expr 'diff(asDateOnly(account_creation_date, "yyyy-MM-dd"), asDateOnly("${day_M1}", "yyyy-MM-dd"), "months") + 1' -P PROJ
```

One variable then drives every time-relative filter; change it and rebuild. A numeric `${var}` column can infer `bigint` and silently null later decimals — multiply by `1.0` and `set-schema` to `double` (see `../ayx/tools-io-apps-ml.md` § Concrete parametric-app flow).

### `%include` chains

Small codebase (<5 includes, <500 lines): parse everything. Large codebase with macros-of-macros: you are likely dealing with a driver script — read `flow-patterns.md`. Shared utility macros (`%mf_*`, `%mp_*`): migrate call sites only, never the macro library itself.

### Inventory shape

```
| # | Source | SAS Step | What It Does | Inputs | Outputs | Migratable? |
|---|--------|----------|--------------|--------|---------|-------------|
| 1 | load.sas | PROC IMPORT | Import homeequity.csv | homeequity.csv | WORK.HOMEEQUITY | Yes → Upload |
| 2 | prep.sas | DATA step | Compute LTV, recode BAD | WORK.HOMEEQUITY | WORK.HE_CLEAN | Yes → Prepare |
```

### Non-migratable patterns

These have no recipe equivalent. Flag them; do not silently drop.

| SAS pattern | Reason | Dataiku answer |
|---|---|---|
| `cas mysession;`, `proc casutil;`, `caslib _all_ assign;` | CAS infra | Not applicable |
| `options`, `proc printto`, `%sysfunc(find(&_SASPROGRAMFILE))` | Session management | Not needed |
| `%JOB_CONTROL_RD`, `%JOB_CONTROL_UPDT`, `%max_run_id` | External run tracking | Scenarios + scenario history API |
| `SAS.df2sd()`, `SAS.submit()` | Python↔SAS data bridge | Migrate the Python logic directly |
| `ODS TAGSETS.EXCELXP`, `DDE` | Excel presentation | Dataiku Dashboard |
| `SASHELP.ZIPCODE`, `SASHELP.US_DATA`, ... | Built-in SAS reference data | User must provide equivalent |
| `PROC DATASETS` (delete) | WORK cleanup | DSS manages datasets differently |
| `PROC PWENCODE` | Password encoding for LIBNAME | Dataiku connection credentials |
| `ABORT`, `ERROR`, `LIST`, `LOSTCARD`, `PUTLOG`, `REDIRECT`, `DESCRIBE`, `EXECUTE` (DATA-step), `DISPLAY`, `WINDOW`, `LABEL`/`Label:`/`GOTO`/`LINK`/`LEAVE`/`CONTINUE` | Log / debug / interactive / intra-step control flow | Drop — see `data-step.md` |

Tell the user: *"Steps #N are SAS infrastructure — no recipe equivalent. Dataiku equivalents: [connections / project variables / scenarios]."*

---

## Collapse triggers — running the Phase-2 collapse pass

> **Source-agnostic graph collapses now live in `references/flow-collapse.md`** (Tier-2, re-checked on the built graph in Phase 3.5). The rows below are *source-idiom detectors* for Phase-2 planning; rows that are really DSS-graph shapes point there for mechanics instead of repeating them.

SAS is *not* Alteryx: a single SAS DATA step is already chunky (`merge + compute + bin + filter + output` in one block), so the typical collapse direction is "many SAS plumbing/in-place steps → fewer DSS recipes" rather than "many tools → one recipe". Several DATA steps actually *expand* to two recipes (Join + Prepare) — that is correct, not a missed collapse.

**Expected ratio band for SAS: ~1.2–2.5×** (vs Alteryx's 3–5×). Anchor on the value hot-spots below, not on the raw step count. A SAS program with no `proc sort`s, no in-place rewrites, and no per-dim fan-in legitimately migrates 1:1.

| Trigger pattern in the SAS source | DSS collapse | Steps fused |
|---|---|---|
| Standalone `proc sort data=X; by k; run;` whose only purpose is to enable a subsequent `merge by k` or `by k` DATA step | Drop entirely — DSS Join / Group / Window do not require sorted inputs | N → 0 |
| `proc sort + data; by k; if first.k then output;` (or `if last.k`) | One Window with `rowNumber == 1` post-filter (order DESC for `last.k`); `create-distinct --on` only when a keys-only output is fine — dedup mapping: `procs.md` § PROC → recipe | 2 → 1 |
| `proc sort + data; by k; retain counter; counter+1; if last.k then output;` | One Group recipe (count + max date per key); follow with one Prepare for the `_cat` binning | 2-3 → 1-2 |
| Multiple in-place rewrites of the same dataset (`data X; set X; ...; run;` repeated 2–5× — e.g. one block to clean names, the next to recode payment, the next to fix IDs) | One Prepare with N steps | N → 1 |
| **Per-dim fan-in to a customer reference table.** Multiple `data appl_X (keep=customer_id …); merge appl_reference_table(in=a) manip_X(in=b); by customer_id; if a; if X1=. then X1=0; …; run;` blocks — one per dimension (tenure, options, devices, claims, …) | **One multi-input Join (LEFT) of `ref + manip_*`** + **one Prepare doing all the fill-empty defaults at once.** This is the single biggest collapse in any SAS analytical migration — the per-dim `appl_X` intermediates exist purely as SAS DATA-step ergonomics. | 2N → 2 (e.g. 11 dims → 2 recipes instead of 22) |
| Single DATA step doing `merge X(in=a) Y(in=b); by k; if a; <compute>; <bin>; run;` | Join (LEFT) + Prepare. NOT a SQL recipe — see `data-step.md`. | 1 → 2 (expansion — flag the trap; agents often reach for SQL here, which is wrong) |
| Multi-output `data A B C; set X; if c1 then output A; else if c2 then output B; ...;` | One Split recipe with N output filters | N+1 → 1 |
| Pre-merge rename via `(rename=(old=new))` in the merge | Fold the rename into the Join recipe's column-renaming flag, or drop the rename if the only reason was BY-key alignment | 2 → 1 |
| Same lookup table joined twice under different aliases (e.g. `plan_levels_list` joined as `_before` then `_after` to attach two level columns) | Either one SQL recipe with two CTE joins, or two visual Joins (no Prepare aliasing step needed) | 4-5 → 1-2 |
| `proc sort nodupkey` | One recipe, no pre-Sort — DSS dedup needs no sorted input (agents otherwise add a redundant Sort); mapping: `procs.md` § PROC → recipe | 1 → 1 (not a fusion, but flag the foot-gun) |
| `data _NULL_;` log-only steps, `proc print`, display-only `format` statements | Drop — already covered as non-migratable above | N → 0 |
| `%macro foo(ds); ...; %mend; %foo(a); %foo(b); %foo(c);` where the macro body is identical and the inputs share a key | One Stack of the inputs + one Prepare (or one Window if the body needs per-group ordering); not three separate recipes — this is the "Hoist below union" collapse, `references/flow-collapse.md` catalog | 3 macro expansions → 1-2 |
| `proc sql; create table X as select ...; quit;` doing only `WHERE` + `GROUP BY` + simple aggregates | Filter + Group (visual, two recipes) — but if the surrounding flow is on SQL anyway, leaving as a SQL recipe is also fine. Do NOT translate trivial PROC SQL to a Python recipe. | 1 → 1-2 |
| Per-feature blocks (tenure, consumption, elapsed, …) that ONLY need a column already present in `appl_reference_table` or trivially join-able from one extra extract | Skip the dedicated `appl_X` checkpoint — add the extract as another input to the master Join, compute the feature columns inline in the master Prepare alongside categorize + default-fill | 4-5 per block → 0 (folded into the existing master pair) |
| **DATA-step BY-group state machine** (RETAIN + first./last. + multiple conditional updates that propagate state across rows) | **Does NOT collapse to one Window.** Realistic count is a four-recipe visual pipeline: Window-lag → Prepare-markers → Window-aggregate → Prepare-final. See `sql-translations.md` § Visual-only fallback. Reach for Python only after exhausting this pattern. | 1 SAS step → 4 DSS recipes (expansion — flag in plan) |

**Where the ratio actually matters.** In-place rewrites and per-dim fan-in account for 60–80% of the collapse on a typical SAS analytics program — if the plan retains separate `appl_*` datasets per dimension or multiple Prepare recipes rewriting the same dataset, re-walk these triggers before presenting.

---

## SAS-specific gotchas

Cross-source CLI / Dataiku gotchas live in `../../dku-cli/playbooks/tabular-flow.md`. SAS *language* gotchas (PDV, MERGE semantics, missing values, `<>` operator, LAG traps, PROC UNIVARIATE defaults) live in `semantics.md`. Parsing gotchas (EGP encodings, `.flw` JSON, SASHELP, `.sas7bdat` id-nulling, `%include` chains) live in the Phase-1 sections above.

### Source-specific verification

After Phase 3 build, compare row count against the SAS log: `NOTE: Table WORK.X created, with N rows`. If counts differ, investigate before continuing.

### Source-specific value-mismatch debugging

| Symptom | Likely cause |
|---|---|
| Value mismatch on `.5` boundaries | Rounding mode — SAS is half-away-from-zero for any sign; Python/pandas/PG DOUBLE are banker's; DSS in-memory `round()` is Java round-half-up (matches SAS for positives, not for negatives). See `functions-formats.md` |
| Filter dropped more rows than SAS | SAS `where` treats missing as smallest value; DSS GREL `isnull()` must be explicit. SAS `if x > 0` keeps `x = .` as false; equivalent GREL is `x > 0` (NULLs do not pass filters in DSS, same as SAS) |
| MERGE produced different rows than Join recipe | `merge` semantics are *not* a left/inner join — see `semantics.md` § MERGE |
| Migrated `MEAN(col)` / `STD(col)` per row produced per-row identity values, not the global aggregate | SAS PROC SQL silently auto-remerges (log: `NOTE: The query requires remerging summary statistics back with the original data`). DSS Window does NOT do global-only aggregates even with unbounded frame. Use Group(no key) + CROSS Join + Prepare — see `procs.md` |

---

## Reference map

| Reference | When to read |
|---|---|
| `semantics.md` | Any time you need to understand *why* a SAS program produces a given value — PDV, MERGE semantics, missing value rules, macro scoping, LAG trap, PROC UNIVARIATE defaults |
| `data-step.md` | DATA step, RETAIN, ARRAY, DO, SELECT/WHEN, external file I/O |
| `procs.md` | PROC mapping, PROC SQL decomposition, transpose, univariate, formats, stats |
| `sql-translations.md` | SAS → SQL function table, PERCENTILE_CONT, RETAIN → LAG state machines, visual-only fallback |
| `functions-formats.md` | Function mapping, GREL/SQL equivalents, rounding, dates |
| `ml-scenarios.md` | Visual ML, scheduling, checks, reporting, scenarios |
| `flow-patterns.md` | Enterprise driver scripts, passthrough extracts, fan-in/split, parity checks |
| `../references/workflow.md` | Phase-by-phase mechanics |
| `../../dku-cli/playbooks/tabular-flow.md` | Recipe selection, collapse mechanics, SQL engines & cross-connection landing, flow organization (zones/naming/wiki), cross-source gotchas |
| `../../dku-cli/references/formulas.md` | GREL reference + § GREL → SQL push-down |
