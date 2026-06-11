# SAS Flow Patterns

Full-program migration, passthrough extract handling, fan-in/split, and parity-check patterns.

## Full-program migration: passthrough extracts + DATA step downstream

End-to-end pattern for a real SAS analytics program with ~7 ODBC passthroughs feeding ~10 downstream DATA step transformations that fan into a final `application_table` + a split. The shape of the Dataiku flow matters: every intermediate dataset should stay on the SQL connection for push-down.

**Target shape:**

```
sources on SQL conn → 7 SQL recipes (extracts) → many visual/SQL recipes (appl_*) → Join (fan-in) → Split → outputs
                      └──────── all datasets on the same SQL connection ────────┘
```

**Anti-pattern:** bundle all downstream DATA steps into one Python recipe. Breaks push-down, hides logic, makes step-by-step verification impossible. On real workloads (10M+ rows) the Python route is 10-100× slower than leaving the work on the database.

**Recipe-type decision tree for each DATA step:**

1. Row-wise transform (filter, rename, formula, recode, fill-empty)? → **Prepare**
2. Join with `if a;` / `if a and b;` / no-filter semantics? → **Join**
3. Group aggregation with `sum/avg/min/max/count/stddev`? → **Group**
4. Stack/append (`SET ds1 ds2`)? → **Stack**
5. Pivot (`PROC TRANSPOSE`)? → **Pivot**
6. `PROC SORT NODUPKEY` / "keep first per group"? → **Sort + Distinct** or **Window** (row_number)
7. Needs `LAG`, `ROW_NUMBER`, cumulative sums, state-machine-like patterns? → **SQL recipe**
8. Needs medians / quartiles / percentiles? → **SQL recipe** with `PERCENTILE_CONT`
9. Needs a SAS-specific feature with no SQL equivalent (special missing `.A`–`.Z`, hash with non-equality keys, complex `DO WHILE` state)? → **Python recipe** — only for that step

Reach step 9 only after 1-8 are exhausted.

### Step 1 — Upload source + reference tables to the SQL connection

```bash
dku dataset create SRC_raw --type UploadedFiles -P PROJ
dku dataset upload SRC_raw /path/to/SRC.csv -P PROJ
dku dataset set-schema SRC_raw -P PROJ --definition '[...]'

# Sync to the SQL connection via -t sync --connection (no Python passthrough)
dku recipe create sync_SRC -t sync -i SRC_raw --output-ds SRC \
    --connection <sql_connection> -P PROJ
dku recipe run sync_SRC -P PROJ --wait
```

Loop for every source **and every reference CSV** the DATA step code consumes. A filesystem lookup joined to a SQL-backed dataset will force that join off the engine.

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

Use Phase 3 protocol from the SKILL.md. For visual recipes:
```bash
dku recipe create-<type> RECIPE -i INPUT --output-ds OUTPUT [opts] -P PROJ
dku recipe apply-schema RECIPE -P PROJ
dku recipe run RECIPE -P PROJ --wait
dku dataset info OUTPUT -P PROJ --recompute
```

For SQL recipes (window functions, LAG, percentiles, CTE logic):
```bash
dku dataset create OUTPUT -P PROJ --type <SQLType> -c <sql_connection> \
    --definition '{"params":{"connection":"<sql_connection>","mode":"table","table":"${projectKey}_OUTPUT"}}'
dku recipe create RECIPE -t sql_query -i INPUT --output-ds OUTPUT -P PROJ
dku recipe set-code RECIPE -P PROJ --code @sql/RECIPE.sql
dku recipe apply-schema RECIPE -P PROJ
dku recipe run RECIPE -P PROJ --wait
```

### Step 4 — Fan-in + split

After all `appl_*` datasets are built, use a single Join recipe with all inputs on `customer_id`. `dku recipe create-join` supports multiple `-i`. Default join type is LEFT. Drop overlapping columns in a post-Join Prepare (duplicate column names get `_1`/`_2` suffixes).

Split by dimension with a Split recipe (for many values) or two Prepare filters (for simple cases).

### Step 5 — Parity check

Run the same SAS program against inline `datalines;` blocks of the same synthetic source tables (strip `connect to odbc as remote`, replace `to_date` with SAS date literals). Pull both sides via `dku --format json dataset head` and compare row-by-row. On the first run, expect small mismatches on `.5` boundaries — usually engine rounding semantics. See Rounding below.

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
2. **Visual recipes on filesystem** — for simple extracts and multi-join extracts, Join/Group/Pivot/Window. Loses push-down but stays declarative.

Do NOT translate passthrough SQL or downstream DATA steps to Python recipes just to avoid setting up a SQL connection.

---

## Flow patterns

**Linear:** `raw → [Prepare] → clean → [Sort] → sorted → [Group] → summary`

**Fan-out (split by value):** One Prepare recipe per output:
```bash
dku recipe create-filter prep_mortgages -i source --output-ds mortgages \
    -f 'ACCT_TYPE == "MORT"' -P PROJ
```

**Fan-in:** Join recipe — left join on key, no pre-sort needed.

**Stack / append:** Stack recipe — union all inputs.

**Macros reminder:**
- `%LET var=val` → `dku project set-variable KEY VALUE`
- `%MACRO do_thing(ds)` → project Python library (only if a pure helper)
- `%DO i=1 %TO &count;` → one recipe per iteration, or Scenario loop
- `%INCLUDE` → identify which macros are actually called, migrate only those
