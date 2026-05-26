# SAS Migration

Source-specific entrypoint for migrating SAS programs (`.sas`, `.egp`, `.flw`) to a Dataiku DSS flow. Read the top-level `migration` SKILL.md first for the cross-source rules, phases, and common gotchas. This file holds only the parts that differ for SAS.

Pair with `dku-cli` (CLI execution) and `dataiku` (platform knowledge). When the target is a SQL connection, also read `dku-cli` skill's `references/sql-engines.md` § GREL → SQL push-down gotchas.

## SAS-specific rules

In addition to the cross-source rules in the top-level SKILL.md:

1. **DATA step ≠ Python recipe.** Most DATA steps decompose into Prepare (filter / rename / compute) + Join (`MERGE`) + Group / Window (RETAIN). `merge X(in=a) Y(in=b); by k; if a;` is a LEFT JOIN. `if a and b;` is INNER. Going to Python is almost always premature.
2. **`PROC FORMAT` inlines into a formula.** No separate format artifact. `put(var, spend_tier.)` with `low-500='Low'` → nested `if()`. See `translation.md`.

## Phase 1 — Parsing the source files

### `.sas`

Read directly. Follow every `%include` chain. Embedded `datalines;` blocks are test data, not production input. `%macro` bodies are not the unit of migration; what the macro *generates* at each call site is. `libname` → Dataiku connection.

### `.egp` (Enterprise Guide project)

ZIP archive. Extract with `unzip project.egp`. Inside:

- `project.xml` is **UTF-16** — `open(f, 'rb').read().decode('utf-16')`; plain `open(f)` garbles it.
- `<Element><Type>CONTAINER</Type>` → process flow groups.
- `<Element><Type>TASK</Type>` → executable tasks.
- `CodeTask-*/code.sas` — read directly.
- `Query-*/Log-*/result.log` — Query Builder tasks have NO `.sas` file; the generated SQL is in the log, prefixed with `s`.
- `ImportTask-*/*.xml` — CSV field mappings.
- `EGTask-*` — empty EG-native placeholders, no code.

### `.flw` (SAS Studio flow)

JSON, not XML. `json.load(f)`. `flow['nodes']` → sub-flows; each node has `dataFlowAndBindings.dataFlow.{nodes,connections}`. Node `nodeType`: `step`, `table`, `outputTable`.

### `.sas7bdat` source tables

DSS does not upload `.sas7bdat` directly — convert to CSV first via pandas, then upload. **The id-column gotcha is silent and high-impact:** SAS stores all numerics as `double`, so pandas `read_sas` returns `id=1077430.0` (float). If you `to_csv` and then `dku dataset set-schema id:bigint`, every value becomes `null` without error and downstream joins produce zero rows. Cast id-like columns to nullable `Int64` before writing the CSV:

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

After `dku dataset upload + set-schema`, sanity-check with `dku dataset head <ds> -P PROJ -n 3 -o json` and confirm the id values are populated (not `null`). If they're null, the float-formatted-to-bigint silent cast happened — re-run the conversion with the `Int64` cast in place.

### Python-in-SAS

`proc python; submit; ... endsubmit;` blocks. Extract the code between `submit;` / `endsubmit;`, migrate to a Python recipe. Ignore the SAS-side bridge.

### PROC SQL passthrough is ingest, not flow

`proc sql; connect to <engine> as remote (...); create table X as select ... from connection to remote(...); quit;` blocks describe **what the warehouse delivers to SAS WORK**, not flow logic. Two paths:

- **Warehouse reachable from DSS** — model as a SQL recipe on the same connection. Push-down preserved end-to-end, including subsequent visual recipes if rule 2 (one engine per flow) is honored.
- **Warehouse NOT reachable** — model the `extract_*` output as an INPUT dataset (header-only CSV with the right typed schema; the user wires real data later). Migrate only the **post-extract** logic. This is the default for code-only migrations.

Either way the inventory line for a passthrough block reads `Yes → Input dataset (warehouse delivered)` or `Yes → SQL recipe`, never `Yes → Visual recipe pipeline`. Do not translate 8 LEFT JOINs in a passthrough into 8 visual Join recipes — that's transliteration of the *warehouse query plan*, not migration of the SAS *flow*.

### SAS macro variables → DSS project variables

Macro variables that vary per run (`&day_M12.`, `&day_M1.`, `&run_id.`, region selectors) map directly to **DSS project variables**:

```bash
dku project set-variables -P PROJ --set day_M1=2024-12-01 --set day_M12=2024-01-01
```

**GREL formulas inside Prepare recipes do NOT interpolate `${var}`.** This is the friction. The working pattern is **set the project variable AND hard-code the value inline in formulas**:

```bash
dku recipe add-formula prep --column tenure_m \
    --expr 'diff(asDateOnly(account_creation_date, "yyyy-MM-dd"), asDateOnly("2024-12-01", "yyyy-MM-dd"), "months") + 1' -P PROJ
```

The project variable serves as documentation + a single source of truth for scenarios that template-render formulas; the inline literal is what actually executes. When the value changes, both must be updated. SQL recipes and dataset names DO interpolate `${day_M1}` — only GREL inside Prepare/visual-recipe filters/computed-columns is the limitation.

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

The migration skill rule 13 ("N source steps → far fewer DSS recipes") says you must do a collapse pass after the 1:1 draft. SAS is *not* Alteryx: a single SAS DATA step is already chunky (`merge + compute + bin + filter + output` in one block), so the typical collapse direction is "many SAS plumbing/in-place steps → fewer DSS recipes" rather than "many tools → one recipe". Several DATA steps actually *expand* to two recipes (Join + Prepare) — that is correct, not a missed collapse.

**Expected ratio band for SAS: ~1.2–2.5×** (vs Alteryx's 3–5×). Anchor on the value hot-spots below, not on the raw step count. A SAS program with no `proc sort`s, no in-place rewrites, and no per-dim fan-in legitimately migrates 1:1.

Each row below describes a pattern that appears in nearly every analytic SAS program. If you find one in your draft, collapse it before showing the plan to the user.

| Trigger pattern in the SAS source | DSS collapse | Steps fused |
|---|---|---|
| Standalone `proc sort data=X; by k; run;` whose only purpose is to enable a subsequent `merge by k` or `by k` DATA step | Drop entirely — DSS Join / Group / Window do not require sorted inputs | N → 0 |
| `proc sort + data; by k; if first.k then output;` (or `if last.k`) | One Distinct (keep first/last per group) or one Window with `rowNumber=1` | 2 → 1 |
| `proc sort + data; by k; retain counter; counter+1; if last.k then output;` | One Group recipe (count + max date per key); follow with one Prepare for the `_cat` binning | 2-3 → 1-2 |
| Multiple in-place rewrites of the same dataset (`data X; set X; ...; run;` repeated 2–5× — e.g. one block to clean names, the next to recode payment, the next to fix IDs) | One Prepare with N steps | N → 1 |
| **Per-dim fan-in to a customer reference table.** Multiple `data appl_X (keep=customer_id …); merge appl_reference_table(in=a) manip_X(in=b); by customer_id; if a; if X1=. then X1=0; …; run;` blocks — one per dimension (tenure, options, devices, claims, …) | **One multi-input Join (LEFT) of `ref + manip_*`** + **one Prepare doing all the fill-empty defaults at once.** This is the single biggest collapse in any SAS analytical migration — the per-dim `appl_X` intermediates exist purely as SAS DATA-step ergonomics. | 2N → 2 (e.g. 11 dims → 2 recipes instead of 22) |
| Single DATA step doing `merge X(in=a) Y(in=b); by k; if a; <compute>; <bin>; run;` | Join (LEFT) + Prepare. NOT a SQL recipe — see `data-step.md`. | 1 → 2 (expansion — flag the trap; agents often reach for SQL here, which is wrong) |
| Multi-output `data A B C; set X; if c1 then output A; else if c2 then output B; ...;` | One Split recipe with N output filters | N+1 → 1 |
| Pre-merge rename via `(rename=(old=new))` in the merge | Fold the rename into the Join recipe's column-renaming flag, or drop the rename if the only reason was BY-key alignment | 2 → 1 |
| Same lookup table joined twice under different aliases (e.g. `plan_levels_list` joined as `_before` then `_after` to attach two level columns) | Either one SQL recipe with two CTE joins, or two visual Joins (no Prepare aliasing step needed) | 4-5 → 1-2 |
| `proc sort nodupkey` | One Distinct recipe (sort+dedupe is one DSS op — agents otherwise add a redundant Sort) | 1 → 1 (not a fusion, but flag the foot-gun) |
| `data _NULL_;` log-only steps, `proc print`, display-only `format` statements | Drop — already covered as non-migratable above | N → 0 |
| `%macro foo(ds); ...; %mend; %foo(a); %foo(b); %foo(c);` where the macro body is identical and the inputs share a key | One Stack of the inputs + one Prepare (or one Window if the body needs per-group ordering); not three separate recipes | 3 macro expansions → 1-2 |
| `proc sql; create table X as select ...; quit;` doing only `WHERE` + `GROUP BY` + simple aggregates | Filter + Group (visual, two recipes) — but if the surrounding flow is on SQL anyway, leaving as a SQL recipe is also fine. Do NOT translate trivial PROC SQL to a Python recipe. | 1 → 1-2 |
| Per-feature blocks (tenure, consumption, elapsed, …) that ONLY need a column already present in `appl_reference_table` or trivially join-able from one extra extract | Skip the dedicated `appl_X` checkpoint — add the extract as another input to the master Join, compute the feature columns inline in the master Prepare alongside categorize + default-fill | 4-5 per block → 0 (folded into the existing master pair) |
| **DATA-step BY-group state machine** (RETAIN + first./last. + multiple conditional updates that propagate state across rows) | **Does NOT collapse to one Window.** Realistic count is a four-recipe visual pipeline: Window-lag → Prepare-markers → Window-aggregate → Prepare-final. See `data-step.md`. Reach for Python only after exhausting this pattern. | 1 SAS step → 4 DSS recipes (expansion — flag in plan) |

**Where the ratio actually matters.** The two heavy hitters are *in-place rewrites* (item 4) and *per-dim fan-in* (item 5). On a typical SAS analytics program these two alone account for 60–80% of the collapse. If your plan retains separate `appl_*` datasets for each dimension or has multiple Prepare recipes that all rewrite the same dataset, re-walk these triggers before presenting.

---

## SAS-specific gotchas

Cross-source CLI / Dataiku gotchas live in `dku-cli/references/common-gotchas.md`. SAS *language* gotchas (PDV, MERGE semantics, missing values, `<>` operator, LAG traps, PROC UNIVARIATE defaults) live in `semantics.md`.

### SAS parsing

| Gotcha | Details |
|---|---|
| EGP `project.xml` is UTF-16 | `.read().decode('utf-16')`; plain `open(f)` garbles |
| EGP Query tasks have no `.sas` file | SQL is in `Query-*/Log-*/result.log` (`s`-prefixed lines) |
| `.flw` files are JSON | `json.load()` — nodes + connections define the DAG |
| SASHELP tables don't exist in Dataiku | User must provide equivalent reference data |
| `%include` chains may pull in thousands of macro lines | Follow every include, or recognize as a driver script |
| `.sas7bdat` numeric IDs export as `1077430.0` (float) → bigint cast silently NULLs every value, downstream joins produce 0 rows | Cast to nullable `Int64` in pandas before `to_csv` (see § `.sas7bdat` source tables above). Sanity-check `dku dataset head` after `set-schema`. |

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
| `translation.md` | SAS translation entrypoint and focused reference map |
| `data-step.md` | DATA step, RETAIN, ARRAY, DO, SELECT/WHEN, external file I/O |
| `procs.md` | PROC mapping, SQL, transpose, univariate, formats, stats |
| `functions-formats.md` | Function mapping, GREL/SQL equivalents, rounding, dates |
| `ml-scenarios.md` | Visual ML, scheduling, checks, reporting, scenarios |
| `flow-patterns.md` | Enterprise driver scripts, passthrough extracts, fan-in/split, parity checks |
| `../references/workflow.md` | Phase-by-phase mechanics |
| `dku-cli/references/recipe-survey.md` | Picking a recipe type |
| `dku-cli/references/common-gotchas.md` | Cross-source Dataiku/CLI gotchas |
| `dku-cli/references/flow-organization.md` | Zones, naming, wiki, descriptions |
| `dku-cli` skill's `references/sql-engines.md` | When the target connection is a SQL engine — cross-connection landing, GREL → SQL push-down gotchas |
