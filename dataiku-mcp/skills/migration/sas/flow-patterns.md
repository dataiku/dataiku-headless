# SAS Flow Patterns

Full-program migration, passthrough extract handling, fan-in/split, and parity-check patterns.

## Full-program migration: passthrough extracts + DATA step downstream

End-to-end pattern for a real SAS analytics program with ~7 ODBC passthroughs feeding ~10 downstream DATA step transformations that fan into a final `application_table` + a split. The shape of the Dataiku flow matters: every intermediate dataset should stay on the SQL connection for push-down.

**Target shape:**

```
sources on SQL conn → 7 SQL recipes (extracts) → many visual/SQL recipes (appl_*) → Join (fan-in) → Split → outputs
                      └──────── all datasets on the same SQL connection ────────┘
```

**Recipe choice** follows the standard rules (recipe altitude + one engine per flow: migration `SKILL.md`; recipe selection: `../../dku-cli/playbooks/tabular-flow.md`). SAS deltas:
- `merge … by k;` with `if a;` / `if a and b;` / no filter → LEFT / INNER / FULL Join (`semantics.md` § MERGE semantics).
- Medians / percentiles → visual Window-rank pattern (`../ayx/tools-join-reshape.md` § Median / percentile); SQL `PERCENTILE_CONT` only when the input is already SQL-backed.
- Python only for a SAS feature with no SQL equivalent (special missing `.A`–`.Z`, hash with non-equality keys, complex `DO WHILE` state) — and only for that step.

### Step 1 — Land sources on the SQL connection

Upload + `create-sync --connection` per source (`../../dku-cli/playbooks/tabular-flow.md` § SQL recipe, cross-connection landing) — **including every reference CSV the DATA steps consume**: a filesystem lookup joined to a SQL-backed dataset forces that join off the engine.

### Step 2 — One SQL recipe per passthrough

The output must pre-exist on the SQL connection with `mode: "table"` params — the default `dku dataset create --type <SQLType>` does NOT set these, and the recipe run fails with `Can only write to a SQL dataset in TABLE mode`.

```bash
dku dataset create extract_base_plan -P PROJ --type <SQLType> -c <sql_connection> \
    --definition '{"params":{"connection":"<sql_connection>","mode":"table","table":"${projectKey}_extract_base_plan"}}'

dku recipe create extract_base_plan -t sql_query -i src_fact \
    --output-ds extract_base_plan -P PROJ
dku recipe add-input extract_base_plan dim_1 -P PROJ
dku recipe add-input extract_base_plan dim_2 -P PROJ
# ... one add-input per additional source table (dku recipe create -t sql_query takes only one -i)

dku recipe set-code extract_base_plan -P PROJ --code @/path/to/extract.sql
dku recipe apply-schema extract_base_plan -P PROJ   # propagates SELECT columns to the target table
dku recipe run extract_base_plan -P PROJ --wait
dku dataset info extract_base_plan -P PROJ --recompute
```

Translate the passthrough body character-for-character. Adaptations:
- `to_date('2024/12/31','yyyy/mm/dd')` → `DATE '2024-12-31'` or `'2024-12-31'` if text
- `src_fact fml` → `"${projectKey}_src_fact" fml` — DSS substitutes `${projectKey}` at run time
- `calculated col` SAS-only shorthand → repeat the expression or use a subquery

### Step 3 — Downstream flow, one recipe at a time

Phase 3 protocol (create → apply-schema → run → verify): `../references/workflow.md` § Phase 3. Every SQL recipe follows the Step-2 shape: TABLE-mode output dataset first, then `create -t sql_query` + `set-code`.

### Step 4 — Fan-in + split

After all `appl_*` datasets are built, use a single Join recipe with all inputs on `customer_id`. `dku recipe create-join` supports multiple `-i`. Default join type is LEFT. Drop overlapping columns in a post-Join Prepare (duplicate column names get `_1`/`_2` suffixes).

Split by dimension with a Split recipe (for many values) or two Prepare filters (for simple cases).

### Step 5 — Parity check

Run the same SAS program against inline `datalines;` blocks of the same synthetic source tables (strip `connect to odbc as remote`, replace `to_date` with SAS date literals). Pull both sides via `dku --format json dataset head` and compare row-by-row. On the first run, expect small mismatches on `.5` boundaries — usually engine rounding semantics. See `functions-formats.md` § Rounding parity.

### Recognizing enterprise driver scripts

Some SAS inventories are not analyst scripts at all but **driver scripts** for production database builds. Signs:

- Top-level `.sas` is <200 lines but almost entirely `%include` / `%macro` invocations
- Shared macro libraries: `AWS_Shared_Macros.sas`, `tms_config.sas`, `da_config.sas`
- Connection macros: `%TMSIS_CONNECT`, `%TMSIS_DISCONNECT`, `%DBCONN`
- Job control: `%JOB_CONTROL_RD`, `%JOB_CONTROL_UPDT`, `%max_run_id`
- SQL passthrough inside the included files: `execute ( ... ) by <libref>_passthrough;`
- Target tables in a specific schema: `&DA_SCHEMA..TAF_ANN_PL_LCTN`

These still migrate to SQL recipes — the passthrough is data + a query, both with Dataiku equivalents. Don't treat passthrough as "infrastructure we can't touch". The only difference from analyst scripts is scope and surrounding orchestration.

| SAS concept | Dataiku equivalent | Notes |
|---|---|---|
| SQL passthrough block | SQL recipe (`sql_query`) | One recipe per block |
| ODBC connection | Dataiku SQL connection | Defined once in `dku connection list` |
| Source tables in passthrough | Datasets on the SQL connection | Register each one |
| `%TMSIS_CONNECT` / `DISCONNECT` | — | Recipes open/close connections automatically |
| `%JOB_CONTROL_RD` (read job params) | Project variables | `dku project set-variables`; read via `${variable}` in SQL |
| `%JOB_CONTROL_UPDT` (write times) | Scenario run history | Dataiku tracks start/end/status automatically |
| `%max_run_id` / lookup by `DA_RUN_ID` | Scenario `last-run` API | Don't replicate the SAS run-tracking table |
| Global macro vars (`&YEAR`, `&DA_RUN_ID`) | Project variables | |
| `proc printto log="..."` | Dataiku job logs | Automatic |
| `%INCLUDE` of 10+ macro files | Migrate call sites only | Never migrate the macros themselves |
| Per-month `_01`..`_12` expansion macros | SQL recipe with `CASE WHEN` per month | Migrate the expanded form |

### When the user has no SQL connection

1. **Use `duckdb_local`** — any modern DSS install has a local DuckDB connection. DuckDB speaks close-to-Postgres SQL, supports window functions and `PERCENTILE_CONT`, and is fine for verification migrations.
2. **Visual recipes on filesystem** — for simple extracts and multi-join extracts, Join/Group/Pivot/Window. Loses push-down but stays declarative. State machines stay visual too: `sql-translations.md` § Visual-only fallback.

Do NOT translate passthrough SQL or downstream DATA steps to Python recipes just to avoid setting up a SQL connection.

Macro translation (`%LET`, `%MACRO`, `%DO`, `%INCLUDE`) → `semantics.md` § Macro patterns.
