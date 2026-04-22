---
name: sas-migration
description: Migrate SAS Enterprise Guide projects (.egp), SAS Studio flows (.flw), and SAS programs (.sas) to Dataiku DSS flows. Use when the user provides SAS code, an EGP file, a flow file, or asks to convert/migrate/translate SAS to Dataiku.
triggers:
  - sas migration
  - migrate sas
  - convert sas
  - translate sas
  - .sas file
  - .egp file
  - .flw file
  - proc sql
  - data step
  - proc format
metadata:
  author: dataiku
  version: "3.0.0"
  tags: sas, migration, visual-recipes, dataiku
---

# SAS Migration

Migrating SAS programs (`.sas`, `.egp`, `.flw`) to a Dataiku DSS flow. Pair this skill with `dku-cli` (CLI execution) and `dataiku` (platform knowledge). When the target is a SQL connection, also read the `dku-cli` skill's `references/sql-engines.md` § GREL → SQL push-down gotchas.

## Rules

1. **Visual → SQL → Python.** Reach for SQL only when the logic needs `LAG`/`ROW_NUMBER`, `PERCENTILE_CONT`, multi-CTE pipelines, or is a direct port of an existing passthrough `SELECT`. Reach for Python only when neither visual nor SQL can express the semantics (hash lookups with non-equality keys, true PDV state machines with cross-row mutation). "One SQL file is tidier" is not a reason.
2. **One engine per flow.** If the sources live on a SQL connection, every intermediate dataset (extracts, lookups, reference CSVs, fan-ins) must live on the same connection. A single Python recipe in the middle forces every upstream row through DSS memory and destroys push-down for the rest of the flow.
3. **Build one recipe at a time.** Create → configure → `apply-schema` → run → verify row count + sample → report → next. Never batch.
4. **`dku` CLI for every step.** If you reach for `dataikuapi` directly you are either hitting a CLI gap (file it) or skipping Phase 3.
5. **DATA step ≠ Python recipe.** Most DATA steps decompose into Prepare (filter/rename/compute) + Join (`MERGE`) + Group/Window (RETAIN). `merge X(in=a) Y(in=b); by k; if a;` is a LEFT JOIN. `if a and b;` is INNER.
6. **`PROC FORMAT` inlines into a formula.** No separate format artifact. `put(var, spend_tier.)` with `low-500='Low'` → nested `if()`. See `references/translation.md`.
7. **Verify with `--recompute`.** `dku dataset info DS -P PROJ --recompute` — DSS caches row counts and does not auto-refresh after a build.
8. **Date columns stay STRING at ingest.** `dku dataset set-schema` with `type: date` on a CSV silently nulls every row. ISO strings compare and aggregate chronologically anyway.
9. **`dku recipe create-filter` builds a Prepare recipe.** The Sampling recipe's filter schema is unstable across DSS versions and silently drops the formula on many instances.
10. **Group recipe adds a `count` column by default.** Pass `--no-global-count` for PROC SQL / PROC MEANS parity.
11. **For int → string casts in a Prepare recipe pushed down to SQL, use `concat("", col)`.** `"" + col` compiles to SQL numeric addition and fails with `invalid input syntax`. `toString(col)` is the Shaker-side cast and does not always survive push-down — `concat("", col)` is the portable form. See the `dku-cli` skill's `references/sql-engines.md` § GREL → SQL push-down gotchas.
12. **Organize the flow into zones as you build.** A migrated SAS project yields dozens of recipes and datasets — a flat flow is unreadable. Group by stage (ingest, prepare, join, aggregate, output) or functional area (credit, collateral, reporting) with `dku flow zones` / `dku flow move`. Assign each recipe and its output to its zone immediately after the recipe runs, not in a post-hoc cleanup pass.
13. **Document the migration with a wiki and descriptions.** Before reporting done: add a project wiki (`dku wiki create`) covering the source SAS layout, the migration map (SAS step → recipe), and any deviations from parity. Set short descriptions on every dataset (`dku dataset set-metadata --short-desc`) and give recipes clear names so the flow is self-explanatory when a reviewer opens it. Use `dku dataset ai-describe --save` and `dku project ai-describe --save` to bootstrap.

---

## Migration plan

### Phase 0 — Preflight

```bash
dku whoami                          # must succeed — if not: dku auth login
dku connection list                 # find a writable+managed connection
dku project create PROJ --name "Project"
```

Store the connection name and project key — every subsequent command uses them.

### Phase 1 — Extract & inventory

Produce a complete inventory of every SAS step, its inputs, outputs, and what it does. No Dataiku planning yet — just understand the SAS. Present to the user for confirmation before Phase 2.

```
| # | Source | SAS Step | What It Does | Inputs | Outputs | Migratable? |
|---|--------|----------|--------------|--------|---------|-------------|
| 1 | load.sas | PROC IMPORT | Import homeequity.csv | homeequity.csv | WORK.HOMEEQUITY | Yes → Upload |
| 2 | prep.sas | DATA step | Compute LTV, recode BAD | WORK.HOMEEQUITY | WORK.HE_CLEAN | Yes → Prepare |
```

#### Parsing the source files

**`.sas`** — read directly. Follow every `%include` chain. Embedded `datalines;` blocks are test data, not production input. `%macro` bodies are not the unit of migration; what the macro *generates* at each call site is. `libname` → Dataiku connection.

**`.egp`** — ZIP archive. Extract with `unzip project.egp`. Inside:
- `project.xml` is **UTF-16** — `open(f, 'rb').read().decode('utf-16')`; plain `open(f)` garbles it.
- `<Element><Type>CONTAINER</Type>` → process flow groups.
- `<Element><Type>TASK</Type>` → executable tasks.
- `CodeTask-*/code.sas` — read directly.
- `Query-*/Log-*/result.log` — Query Builder tasks have NO `.sas` file; the generated SQL is in the log, prefixed with `s`.
- `ImportTask-*/*.xml` — CSV field mappings.
- `EGTask-*` — empty EG-native placeholders, no code.

**`.flw`** — JSON, not XML. `json.load(f)`. `flow['nodes']` → sub-flows; each node has `dataFlowAndBindings.dataFlow.{nodes,connections}`. Node `nodeType`: `step`, `table`, `outputTable`.

**Python-in-SAS** — `proc python; submit; ... endsubmit;` blocks. Extract the code between `submit;`/`endsubmit;`, migrate to a Python recipe. Ignore the SAS-side bridge.

#### Non-migratable patterns

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

Tell the user: *"Steps #N are SAS infrastructure — no recipe equivalent. Dataiku equivalents: [connections / project variables / scenarios]."*

#### Deduplicating multi-file projects

Real projects often have the same transformation implemented in `DATA step`, `PROC SQL`, and `proc python; submit;`. Identify the canonical production version, migrate that one, and note the alternatives as "skipped (alternative of step N)" in the inventory. Present the choice to the user before proceeding.

#### `%include` chains

Small codebase (<5 includes, <500 lines): parse everything. Large codebase with macros-of-macros: you are likely dealing with a driver script — read `references/translation.md` § Enterprise driver scripts. Shared utility macros (`%mf_*`, `%mp_*`): migrate call sites only, never the macro library itself.

### Phase 2 — Migration plan

For each migratable step, map to exactly one Dataiku recipe. Present as a table, get user confirmation before building.

```
| # | SAS Step | Recipe | Type | Input | Output | Key Operations |
|---|----------|--------|------|-------|--------|----------------|
| 1 | DATA LTV | Prepare | Visual | he | he_clean | formula: MORTDUE/VALUE, recode BAD |
| 2 | PROC SQL join | Join | Visual | he_clean + us_data | he_enriched | Left join on STATE |
| 3 | WHERE splits | 3× Prepare | Visual | he_final | mort, pers, auto | Filter on ACCT_TYPE |
```

Pick recipe types from `references/translation.md`. Priority: **Visual → SQL → Python**.

### Phase 3 — Build & verify (one recipe at a time)

```bash
# 3.1 — Upload source data (first time only)
dku dataset create DS --type UploadedFiles -P PROJ && \
dku dataset upload DS /path/to/file.csv -P PROJ && \
dku dataset set-schema DS -P PROJ -d '[
  {"name":"id","type":"bigint"},
  {"name":"amount","type":"double"},
  {"name":"dt","type":"string"}
]'
# Leave date columns as string (gotcha #8).

# 3.2 — Create recipe (visual shortcuts auto-create outputs)
dku recipe create-filter filter_active -i DS --output-ds active \
    -f 'status == "A" && amount > 0' -P PROJ

# 3.3 — Validate BEFORE running (catches formula errors early)
dku recipe apply-schema filter_active -P PROJ

# 3.4 — Run
dku recipe run filter_active -P PROJ --wait

# 3.5 — Verify output
dku dataset info active -P PROJ --recompute
dku dataset schema active -P PROJ
dku dataset head active -P PROJ -n 5
```

Compare row count against the SAS log (SAS prints `NOTE: Table WORK.X created, with N rows`). If counts differ, investigate before continuing.

After each recipe, report: `[recipe_name]: [input] → [output], [N] rows. Matches SAS.` Then move on.

### Phase 4 — Integration test

```bash
dku recipe list -P PROJ
dku dataset list -P PROJ
dku dataset head FINAL_OUTPUT -P PROJ -n 5 -o json
```

Present a migration summary: SAS step → recipe → output dataset → row count → status. Note anything skipped.

---

## Top gotchas (quick reference)

Full catalogs live in `references/semantics.md` (SAS language rules) and `references/translation.md` (recipe mechanics). These are the ones most likely to cause silent failures.

### Dataiku / CLI

| Gotcha | Fix |
|---|---|
| Upload auto-detects all columns as STRING | Always `set-schema` with correct types immediately after upload |
| `set-schema` with `type: date` on CSV → all null | Keep as `string`; use `startsWith()` / `max()` on ISO dates |
| `dku recipe create-filter` (sampling type) silently ignores formula | Use the CLI's `create-filter` — it builds a Prepare recipe with `FilterOnCustomFormula` |
| Group recipe adds an extra `count` column | Pass `--no-global-count` for PROC SQL / SAS parity |
| Group outputs auto-named `{col}_{func}` | Add `add-rename` to restore SAS aliases (`amount_sum` → `total_revenue`) |
| `dku dataset info` row count is stale after build | Pass `--recompute` — DSS does not auto-recompute metrics on build |
| `apply-schema` required before first run | Otherwise computed columns silently missing |
| `dateonly` JSON has trailing `00:00:00` | Strip to first 10 chars in parity checks |
| `dku dataset create --type SQL` fails on restricted licenses | Use concrete subtype: `--type PostgreSQL`, `--type Snowflake`, etc. |
| Default `create --type <SQLType>` params miss `mode`+`table` | Pass `--definition '{"params":{"connection":"<c>","mode":"table","table":"${projectKey}_<name>"}}'` |
| `sql_query` output dataset must pre-exist | It's a `SingleOutputRecipeCreator`, not a `CodeRecipeCreator`. Create output first |
| `sql_query` recipe payload is raw text, not JSON | `get-definition` and `set-code` on SQL recipes handle text payloads |
| SQL recipe output table has 0 columns initially | Run `apply-schema` before the first build — otherwise `INSERT has more expressions than target columns` |
| `${DKU_DATASET_<name>_TABLE_NAME}` not valid in `sql_query` | Use `"${projectKey}_<dataset>"` — DSS substitutes at run time |

### SAS parsing

| Gotcha | Details |
|---|---|
| EGP `project.xml` is UTF-16 | `.read().decode('utf-16')`; plain `open(f)` garbles |
| EGP Query tasks have no `.sas` file | SQL is in `Query-*/Log-*/result.log` (`s`-prefixed lines) |
| `.flw` files are JSON | `json.load()` — nodes + connections define the DAG |
| SASHELP tables don't exist in Dataiku | User must provide equivalent reference data |
| `%include` chains may pull in thousands of macro lines | Follow every include, or recognize as a driver script |

SAS language gotchas (missing values, MERGE semantics, `<>` operator, LAG traps, PROC UNIVARIATE defaults) live in `references/semantics.md`.

---

## Reference map

| Reference | When to read |
|---|---|
| `references/semantics.md` | Any time you need to understand *why* a SAS program produces a given value — PDV, MERGE semantics, missing value rules, macro scoping, LAG trap, PROC UNIVARIATE defaults |
| `references/translation.md` | DATA/PROC → recipe mapping, canonical Join+Prepare patterns, PROC FORMAT, rounding parity, enterprise ODBC passthrough workflow, SAS function → GREL/SQL tables, SAS→Postgres translations |
| `dku-cli` skill's `references/sql-engines.md` | When the target connection is a SQL engine — cross-connection landing with `-t sync --connection`, `dku sql query` transaction semantics, `dataset info --recompute`, **and GREL → SQL push-down gotchas** (read before writing any GREL in a Prepare recipe whose input AND output are on a SQL connection) |

## Error recovery

| Error | Fix |
|---|---|
| `dku whoami` fails | `dku auth login` |
| `Unknown function 'X'` in GREL | Case matters — `toTitlecase` not `toTitleCase`. See `references/translation.md` |
| `output dataset does not exist` | `dku dataset create DS --type Filesystem -c CONNECTION -P PROJ` |
| Recipe run fails | Run `apply-schema` first; then check connection / schema |
| Row count mismatch with SAS | Check filters, null handling, schema types (STRING vs numeric affects filter evaluation) |
| Value mismatch on `.5` boundaries | Rounding mode — SAS is half-away-from-zero for any sign; Python/pandas/PG DOUBLE are banker's; DSS in-memory `round()` is Java round-half-up (matches SAS for positives, not for negatives). See `references/translation.md` § Rounding parity |
