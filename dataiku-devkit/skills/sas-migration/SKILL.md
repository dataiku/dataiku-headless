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
  version: "2.0.0"
  tags: sas, migration, visual-recipes, dataiku
---

> **Agent Cheat Sheet (read this first)**
>
> 1. **Visual recipes first, SQL second, Python last.** `PROC SQL` of simple `filter + group` decomposes into Prepare + Group, not a SQL recipe. Reach for SQL only for window functions, CTEs, or DB passthrough. Reach for Python only when neither works.
> 2. **`DATA step` ≠ Python recipe.** Most `DATA` steps are filter/rename/compute → Prepare. `MERGE BY` is a Join. `SET ds1 ds2` is a Stack. `RETAIN` patterns are almost always group aggregations or window functions — not Python.
> 3. **`merge X(in=a) Y(in=b); by k; if a;` is a LEFT JOIN.** Don't over-think it. `if a and b;` is INNER. No filter is full outer.
> 4. **`PROC FORMAT` inlines into a GREL formula.** Do NOT create a separate format artifact. `put(var, spend_tier.)` with `low-500 = 'Low'` ranges → `if(var <= 500, "Low", ...)`. See `references/function-mapping.md`.
> 5. **`dku recipe create-filter` builds a Prepare recipe now.** The Sampling recipe type silently ignores the filter formula on many DSS versions. `create-filter` auto-builds `FilterOnCustomFormula` — use it.
> 6. **Group recipe adds an extra `count` column by default.** Pass `--no-global-count` for SAS/PROC SQL parity — PROC SQL only produces columns the user explicitly aggregated.
> 7. **Verify with `--recompute`.** `dku dataset count DS -P PROJ --recompute` — DSS does not auto-refresh metrics after a build, so the cached count is stale.
> 8. **Always rename aggregation outputs.** Group recipe auto-names as `{col}_{func}` (`amount_sum`), not the SAS alias (`total_revenue`). Add a `ColumnRenamer` step to restore SAS-style names.
> 9. **Keep date columns as STRING at ingest.** `dku dataset set-schema` with `type: date` on a CSV with ISO dates silently nulls every row. ISO strings compare and aggregate chronologically correctly anyway.
> 10. **Never trust `dku dataset head -o json | wc -l` for row counts.** Use `dku dataset count --recompute`.
> 11. **`PROC UNIVARIATE` → Python recipe, not Group.** Group recipe aggregations are `sum/avg/min/max/count/stddev` only — no median, no quantiles. For stats migrations, use `numpy.percentile(x, p, method="averaged_inverted_cdf")` (matches SAS `QNTLDEF=5`) and `numpy.std(x, ddof=1)` (sample std — numpy default is population). pandas `quantile()` default is the wrong type.
> 12. **`connect to odbc as remote(...)` → SQL recipe, NOT skip.** The SQL inside the `from connection to remote(SELECT ...)` body is real transformation code. Register each source table as a Dataiku dataset on a SQL connection (`postgresql-local`, `duckdb_local`, or a real cloud DW), then `dku recipe create -t sql_query` with all sources as inputs and the translated SELECT as the code. 100% parity achieved this way on a 14-join production passthrough. Details in `references/enterprise-patterns.md`.
>
> Also use the `dku-cli` skill for CLI specifics and the `dataiku` skill for platform knowledge.

# SAS Migration Skill

Migrate SAS programs (.sas / .egp / .flw) to Dataiku DSS flows. This skill covers the 5-phase migration plan, top gotchas, and pointers into detailed references.

Before writing any Prepare recipe steps, read `dataiku/references/prepare-processors.md` for exact processor types and parameters, and `dataiku/references/formulas.md` for the full verified GREL function reference.

---

## Migration Plan (5 phases)

Every migration follows this loop. Execute in order. Do NOT skip phases.

### Phase 0 — Preflight

Verify the environment before touching any SAS code.

```bash
dku whoami                          # must succeed — if not: dku auth login
dku connection list                 # find a writable+managed connection (e.g. filesystem_managed)
dku project create PROJECT_KEY --name "Project Name"
```

Store the managed connection name and project key — every subsequent command uses them.

### Phase 1 — Extract & inventory

**Goal:** Produce a complete inventory of every SAS step, its inputs, outputs, and what it does. No Dataiku planning yet — just understand the SAS.

Present the inventory to the user in this format:

```
| # | Source File | SAS Step | What It Does | Inputs | Outputs | Migratable? |
|---|-------------|----------|--------------|--------|---------|-------------|
| 1 | load.sas | PROC IMPORT | Import homeequity.csv | homeequity.csv | WORK.HOMEEQUITY | Yes → Upload |
| 2 | prep.sas | DATA step | Compute LTV, recode BAD | WORK.HOMEEQUITY | WORK.HE_CLEAN | Yes → Prepare |
```

Flag non-migratable patterns (CAS infra, ODS, SASHELP joins, job control) explicitly — do not silently drop.

Full parsing details for .egp / .flw / .sas / Python-in-SAS: **`references/inventory-parsing.md`**.

### Phase 2 — Migration plan

**Goal:** For each migratable SAS step, map to exactly one Dataiku recipe. Present as a table, get user confirmation before building.

```
| # | SAS Step | Dataiku Recipe | Type | Input | Output | Key Operations |
|---|----------|----------------|------|-------|--------|----------------|
| 1 | DATA LTV | Prepare | Visual | he | he_clean | formula: MORTDUE/VALUE, recode BAD |
| 2 | PROC SQL join | Join | Visual | he_clean + us_data | he_enriched | Left join on STATE |
| 3 | WHERE splits | 3× Prepare | Visual | he_final | mort, pers, auto | Filter on ACCT_TYPE |
```

Pick recipe types from **`references/recipe-mapping.md`** (full translation tables for DATA steps, PROC SQL, PROC MEANS, PROC TRANSPOSE, AutoML, RETAIN traps, canonical patterns).

Priority: **Visual → SQL → Python.** Reach for code recipes only when no visual recipe fits.

### Phase 3 — Build & verify (one recipe at a time)

Build each recipe, validate with `apply-schema`, run, verify the output. Never batch — one recipe per cycle.

```bash
# 3.1 — Upload source data (first time only)
dku dataset create DS --type UploadedFiles -P PROJ &&
dku dataset upload DS /path/to/file.csv -P PROJ &&

# CRITICAL: upload auto-detects ALL columns as STRING. Fix immediately:
dku dataset set-schema DS -P PROJ -d '[
  {"name":"id","type":"bigint"},
  {"name":"amount","type":"double"},
  {"name":"dt","type":"string"}
]'  # NOTE: leave date columns as string — see gotcha #9

# 3.2 — Create recipe (visual shortcuts auto-create output datasets)
dku recipe create-filter filter_active -i DS --output-ds active \
    -f 'status == "A" && amount > 0' -P PROJ

# 3.3 — Validate BEFORE running (catches formula errors early)
dku recipe apply-schema filter_active -P PROJ

# 3.4 — Run
dku recipe run filter_active -P PROJ --wait

# 3.5 — Verify output
dku dataset count active -P PROJ --recompute    # --recompute avoids stale cache
dku dataset schema active -P PROJ
dku dataset head active -P PROJ -n 5
```

Compare row count against the SAS log (SAS always prints `NOTE: Table WORK.X created, with N rows`). If counts differ, investigate before continuing.

After each recipe: report to user `[recipe_name]: [input] → [output], [N] rows. Matches SAS.` Then move on. Do not batch.

### Phase 4 — Integration test

After ALL recipes built, validate the complete flow end-to-end.

```bash
dku recipe list -P PROJ
dku dataset list -P PROJ
dku dataset head FINAL_OUTPUT -P PROJ -n 5 -o json    # spot-check final values
```

Present a migration summary table: SAS step → Dataiku recipe → output dataset → row count → status. Note anything skipped (non-migratable infrastructure, missing reference data).



---

## Top Gotchas (quick reference)

The ones most likely to cause silent failure. Full catalog in **`references/gotchas.md`**.

### Dataiku/CLI

| Gotcha | Fix |
|---|---|
| Upload auto-detects columns as STRING | Always `set-schema` with correct types immediately after upload |
| `set-schema` with `type: date` on CSV → all null | Keep as `string`; use `startsWith()` / `max()` for ISO dates |
| `dku recipe create-filter` (sampling type) silently ignores formula | Use the CLI's `create-filter` — it builds a Prepare recipe with `FilterOnCustomFormula` |
| Group recipe adds an extra `count` column | Pass `--no-global-count` for PROC SQL / SAS parity |
| Group outputs auto-named `{col}_{func}` | Add `add-rename` to restore SAS aliases (`amount_sum` → `total_revenue`) |
| `dku dataset count` shows stale cache after build | Pass `--recompute` (alias `--fresh`) |
| `apply-schema` required before first run | Otherwise computed columns silently missing |
| `dateonly` JSON has trailing `00:00:00` | Strip to first 10 chars in parity checks |
| Global `dku` CLI cached by `uv tool install` | Use `--force --reinstall` together |

### SAS semantics (will silently change values if missed)

| Gotcha | Fix |
|---|---|
| Missing (`.`) is negative infinity in comparisons | `WHERE amount > 0` excludes missing. Add `COALESCE` / imputation |
| Blank string IS missing in SAS | `missing(" ")` = true. Dataiku treats empty string ≠ null |
| `SUM statement` (`total + x;`) treats `.` as 0 | But `total = total + x;` propagates `.` forever. Read the code carefully |
| LAG inside IF is wrong | `if cond then prev = lag(x)` skips the queue. LAG must be unconditional |
| Character length truncation | Set by first reference. `a='AB';` then `a='ABCDEF';` → `'AB'`. Check LENGTH statements |
| `<>` in DATA step = MAX operator | Not inequality. `a <> b` = `max(a,b)`. Only in WHERE/PROC SQL does `<>` mean `!=` |
| `format var fmt.;` is display-only | Safe to skip. But `var = put(var, fmt.);` is a value assignment — must migrate |

Full verified behavior catalog in **`references/sas-semantics.md`**.

---

## Reference map

| Reference | When to read |
|---|---|
| `references/inventory-parsing.md` | Phase 1 — extracting inventory from .egp / .flw / .sas, handling `%include`, flagging non-migratable patterns |
| `references/recipe-mapping.md` | Phase 2 — choosing a recipe type for any SAS construct, RETAIN traps, PROC SQL decomposition, AutoML, canonical CLI sequences |
| `references/sas-semantics.md` | Any time you need to understand *why* a SAS program produces a given value — PDV, MERGE semantics, missing value rules, macro scoping |
| `references/function-mapping.md` | Translating SAS functions (`PUT`, `INPUT`, `SCAN`, `INTCK`, ...) to GREL or SQL; PROC FORMAT ranges; SAS formats → Prepare processors |
| `references/gotchas.md` | Full 3-table catalog: Dataiku/CLI, SAS parsing, SAS behavior |
| `references/enterprise-patterns.md` | When the SAS program uses ODBC passthrough (`connect to odbc as remote(...)`) or is a DB-native driver script (T-MSIS style) — migrate each passthrough as a **SQL recipe** on a Dataiku SQL connection. Passthrough is NOT a skip — it's a data source |


## Error Recovery

| Error | Fix |
|---|---|
| `dku whoami` fails | `dku auth login` |
| `Unknown function 'X'` in GREL | Check `references/function-mapping.md` — case matters (`toTitlecase`, not `toTitleCase`) |
| `output dataset does not exist` | Create it first: `dku dataset create DS --type Filesystem -c CONNECTION -P PROJ` |
| Recipe run fails | Run `apply-schema` first. Then check: wrong connection? missing schema update? |
| Row count mismatch with SAS | Check filters, null handling, schema types (STRING vs numeric affects filter evaluation) |
