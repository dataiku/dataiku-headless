# SQL Engines: CLI mechanics when the connection is a SQL database

Use this reference when the task involves a SQL-connection dataset (Postgres, Snowflake, BigQuery, Redshift, …) on either side of a recipe. This file covers the **CLI mechanics** only — cross-connection landing, `dku sql query` transaction behavior, post-build metric refresh, and stale-table recovery. For GREL → SQL compilation gotchas (what `toString(col)` becomes, banker's rounding on DOUBLE, etc.), see the `dataiku` skill's `references/formulas.md` § GREL → SQL push-down.

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

## `dku sql query` transaction behavior

`dku sql query` runs every statement inside a short-lived DSS streaming session. SELECTs work as expected. For DDL/DML (CREATE / DROP / ALTER / INSERT / UPDATE / DELETE), the CLI reports `◆ Statement executed on <connection>` and exits 0 — **but the change is silently rolled back unless you add an explicit `COMMIT`**.

Verified on DSS 14.4 + PostgreSQL:

```bash
# Silently rolled back — "Statement executed" is a lie
dku sql query --connection rds 'CREATE TABLE public.t (id int)'
dku sql query --connection rds "SELECT tablename FROM pg_tables WHERE tablename='t'"
# → empty result, table was not created

# This persists:
dku sql query --connection rds 'CREATE TABLE public.t (id int); COMMIT'
dku sql query --connection rds "SELECT tablename FROM pg_tables WHERE tablename='t'"
# → 't'
```

**Always append `; COMMIT`** (or wrap in `BEGIN; … ; COMMIT`) when using `dku sql query` to create tables, drop tables, insert rows, or perform any other DDL/DML. The CLI does not warn you when a statement has been rolled back.

For cleanup scripts, prefer a one-shot Python recipe over `dku sql query` — `SQLExecutor2(connection=...).query_to_df(...)` runs in a normal autocommit session and does not need an explicit commit:

```python
from dataiku.core.sql import SQLExecutor2
SQLExecutor2(connection="rds").query_to_df(
    'DROP TABLE IF EXISTS "PROJECT_dataset_name"'
)
```

---

## `dataset info --recompute` after a build

DSS caches `records:COUNT_RECORDS`, `basic:SIZE`, and `basic:COUNT_FILES` and does NOT recompute them automatically after a recipe build. `dku dataset info DS -P PROJ` will return stale numbers (or `(not computed)` if the dataset has never been probed) until you pass `--recompute`.

```bash
dku dataset build OUT -P PROJ --wait
dku dataset info OUT -P PROJ --recompute   # forces fresh row count / size / file count
```

Use `--recompute` as the canonical post-build verification step. Without it, an agent's verification can trust pre-build numbers.

---

## Stale physical tables and schema drift

DSS 14.4 handles most column-type drift automatically: `dku recipe apply-schema` + rebuild of the writing recipe propagates the Prepare recipe's output schema to the physical SQL table, even when `noDropOnSchemaMismatch: true` is set on the output dataset. Verified on PG with a bigint → text column type change.

You only need manual intervention when the physical table was created with the wrong types out of band (e.g., pre-created via `dataset create --type PostgreSQL` with an explicit schema that doesn't match what the recipe now produces). In that case, drop the physical table via a one-shot Python recipe before rebuilding:

```python
# Drop_stale.py — in a disposable Python recipe
from dataiku.core.sql import SQLExecutor2
SQLExecutor2(connection="rds").query_to_df(
    'DROP TABLE IF EXISTS "PROJECT_dataset_name"'
)
```

Then `dku recipe apply-schema RECIPE -P PROJ && dku recipe run RECIPE -P PROJ --wait` recreates the physical table from the updated schema. The table name convention is `"<PROJECT_KEY>_<dataset_name>"` (double-quoted, case-sensitive on Postgres).

**Do NOT use `dku sql query 'DROP TABLE …'`** for this — see the transaction section above. The drop will silently roll back without a `COMMIT`.

---

## When to read this file

- Before running `dku recipe create -t sync` or `-t sql_query` with `--connection`
- Before using `dku sql query` for anything other than SELECT
- When verifying row counts post-build (`--recompute`)
- When a physical SQL table was pre-created with the wrong schema and needs to be dropped
- For GREL → SQL compilation gotchas, read the `dataiku` skill's `references/formulas.md` § GREL → SQL push-down
