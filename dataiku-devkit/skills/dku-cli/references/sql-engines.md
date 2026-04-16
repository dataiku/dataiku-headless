# SQL Engines: landing, push-down, and recovery

Use this reference when the task involves a SQL-connection dataset (Postgres, Snowflake, BigQuery, Redshift, …) on either side of a recipe — landing CSV/filesystem data, Prepare recipes that push down to SQL, or recovering from a stale physical table.

The `dku` CLI itself is engine-agnostic. This file collects the engine-specific idioms, gotchas, and recovery snippets that tend to bite agents on the first try.

---

## Landing data across connections with `sync`

`sync` moves data from one dataset to another — typically across connections (CSV → Postgres, filesystem → Snowflake, etc.). Unlike most visual recipes (which require the output to pre-exist), **`-t sync --connection X`** auto-creates the output as a managed dataset on the target connection. One recipe call, no Python passthrough.

```bash
# Upload a CSV and land it in Postgres in one chain
dku dataset create src_events --type UploadedFiles -P PROJ && \
dku dataset upload src_events events.csv -P PROJ && \
dku recipe create sync_events -t sync -i src_events --output-ds pg_events \
  --connection postgresql-local -P PROJ && \
dku dataset build pg_events -P PROJ --wait
```

Swap `--connection postgresql-local` for your target — `snowflake-prod`, `bigquery-main`, `redshift-warehouse`, etc. Use `dku connection list` to enumerate managed SQL connections.

The same pattern works for **`-t sql_query --connection X`** when the source is another SQL-connection dataset and you want a custom SELECT landed as a new managed table:

```bash
dku recipe create extract_active -t sql_query -i pg_source_table \
  --output-ds pg_active_subset --connection postgresql-local -P PROJ
# then open the recipe, edit the SELECT, and build
```

**Rule:** if your first instinct is to write a Python recipe that just `read_dataframe()` → `write_dataframe()` to move data between connections, stop — `-t sync --connection X` does it as a first-class DSS feature with schema propagation, lineage, and no Python code.

---

## GREL → SQL push-down gotchas

When a Prepare recipe has BOTH a SQL-connection input AND a SQL-connection output, DSS compiles the Shaker script to SQL and pushes it down to the database engine. Several common GREL idioms compile to **broken** or **silently wrong** SQL. Tested on PostgreSQL; most also apply to Snowflake, BigQuery, Redshift.

| GREL | Compiles to (SQL) | Fails because | Use instead |
|---|---|---|---|
| `toString(col)` | `"col"` (wrapper stripped) | result stays in the column's original type — a bigint in the ELSE branch of a CASE will reject the THEN string literal | `concat("", col)` |
| `"" + col` where col is numeric | `'' + "col"` | SQL `+` is numeric addition in every engine, not string concat; `'' + bigint` errors | `concat("", col)` |
| `strval(col)` (no default) | varies by DSS version | inconsistent — sometimes identity, sometimes `strval(col, "")` | `concat("", col)` for reliability, or `strval(col, "")` with explicit empty default |
| `round(x * 10) / 10` on a DOUBLE column | banker's rounding (half-to-even) on Postgres DOUBLE | `1.25 → 1.2` instead of `1.3` (some engines use half-away-from-zero, others half-to-even) | `floor(x * 10 + 0.5) / 10` |
| `concat(numeric1, numeric2)` | varies | two numeric args may compile to addition on some engines | wrap at least one in `""`: `concat("", a, b)` |

**Rule of thumb for int → string casts that need to survive push-down:** use `concat("", col)`. It compiles to `'' || CAST(col AS VARCHAR)` or equivalent on every major SQL engine. `toString()` is a Java/shaker-only function and gets stripped when DSS translates the expression to SQL.

### Diagnosing a push-down compilation bug

If a Prepare recipe fails at build time with a PG/Snowflake error like `invalid input syntax for type bigint: "..."`, look at the job log:

```bash
dku job log "$(dku job list -P PROJ -o json | jq -r '.[0].id')" -P PROJ | grep -B 50 "Position:"
```

The log dumps the generated SQL around the failure — you'll see your GREL expression compiled into a CASE/CAST that chose the wrong type. The fix is almost always one of the replacements in the table above.

### Checking the selected engine

DSS logs the selected engine twice — once pre-run and once post-reselection:

```bash
dku job log <JOB_ID> -P PROJ 2>&1 | grep -i "selected engine\|engines ok"
```

If `After reselection, selectedEngine is DSS` appears on a recipe that should push down, some formula in the recipe is not translatable (e.g. single-arg `strval(col)`) and DSS fell back to in-memory execution — the output column may end up empty even though the job succeeds.

---

## Common engine-specific recipe mistakes

| Mistake | Fix |
|---------|-----|
| Python passthrough recipe just to land a CSV in a SQL connection | `dku recipe create sync_X -t sync -i csv --output-ds sql_table --connection <sql_conn> -P PROJ` — auto-creates the managed table |
| `toString(col)` in a Prepare recipe fails on SQL-output | GREL `toString()` compiles to SQL identity. Use `concat("", col)` for int→string casts that push down cleanly |
| `"" + col` concat fails with PG `invalid input syntax` | GREL `+` compiles to SQL numeric addition. Use `concat("", col)` instead |
| Stale physical table blocks a Prepare rebuild after column type change | `dku dataset set-schema` updates the logical schema but not the physical table on the DB side. Drop it via a one-shot Python recipe: `SQLExecutor2(connection='<sql_conn>').query_to_df('DROP TABLE IF EXISTS "PROJECT_name"')` then rebuild |

### Stale physical table — recovery snippet

When you change a column's type on a Prepare recipe that writes to a SQL connection, DSS updates the *logical* schema in the DSS metadata but does NOT recreate the *physical* table on the database side. The next build then fails with a type-mismatch error from the engine.

```python
# One-shot Python recipe (no inputs, no outputs) to drop the stale table
from dataiku.core.sql import SQLExecutor2
SQLExecutor2(connection="postgresql-local").query_to_df(
    'DROP TABLE IF EXISTS "PROJECT_name"'
)
```

Then re-run the Prepare recipe — DSS will recreate the physical table from the updated schema. The table name in DSS convention is `"<PROJECTKEY>_<dataset_name>"` (quoted, case-sensitive on Postgres).

---

## When to read this file

- Before running `dku recipe create -t sync` or `-t sql_query` with `--connection`
- Before writing any GREL expression in a Prepare recipe whose input AND output are on a SQL connection
- When a Prepare recipe fails on build with a SQL type-mismatch error from the database engine
- When a rebuild after a column-type change fails with the old type still reported by the engine
