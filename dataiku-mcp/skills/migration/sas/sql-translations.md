# SAS → SQL recipe translations

SQL-recipe translations for SAS constructs, split out of `procs.md` (which owns the
PROC → recipe map and the canonical visual patterns). Read when the flow is SQL-backed —
or, for the § Visual-only fallback, when a state machine must stay visual without SQL.

The rows below come in two flavours:

- **Portable (standard SQL)** — string ops, `CASE WHEN`, `IS NULL`, `GREATEST`/`LEAST` work as-is on Postgres, Snowflake, BigQuery, Redshift, Oracle, SQL Server, DuckDB.
- **Engine-specific** — date math (`AGE`, `make_interval`), numeric casts (`::numeric`, `::double precision`), and `to_char` format strings are **Postgres-specific**. For other engines, swap in the native equivalents — cross-engine date math in `functions-formats.md` § Dates.

| SAS | Standard SQL or **Postgres** | Portability |
|---|---|---|
| `intck('month', d1, d2)` | **PG**: `(EXTRACT(YEAR FROM AGE(d2, d1)) * 12 + EXTRACT(MONTH FROM AGE(d2, d1)))::bigint` | PG only — `AGE()` is Postgres-specific |
| `intck('day', d1, d2)` | **PG**: `(d2 - d1)::bigint` (date subtraction returns int) | PG only — Snowflake/BigQuery need `DATEDIFF` / `DATE_DIFF` |
| `intnx('month', d, n)` | **PG**: `d + make_interval(months => n)` | PG only — Snowflake: `DATEADD(MONTH, n, d)`, BigQuery: `DATE_ADD(d, INTERVAL n MONTH)` |
| `round(x, 0.1)` | **PG**: `round(x::numeric, 1)` — cast to NUMERIC for half-away-from-zero | PG only — other engines don't need the cast; Snowflake/BQ/Redshift/Oracle/SQL Server `ROUND` is already half-away-from-zero |
| `put(num, best.)` | **PG/Oracle**: `trim(to_char(num, 'FM999999999999'))` | PG/Oracle — Snowflake: `TO_VARCHAR(num)`, BigQuery: `CAST(num AS STRING)` |
| `input(str, best.)` | **PG**: `NULLIF(str, '')::double precision` | PG only — other engines: `CAST(NULLIF(str, '') AS DOUBLE)` or `TRY_CAST` |
| `substr(s, start, len)` | `SUBSTRING(s, start, len)` | **Portable** — 1-indexed in every engine |
| `tranwrd(s, a, b)` | `REPLACE(s, a, b)` | **Portable** |
| `scan(s, n, delim)` | `SPLIT_PART(s, delim, n)` | PG / Redshift / Snowflake / DuckDB — BigQuery: `SPLIT(s, delim)[OFFSET(n-1)]` |
| `strip(s)` / `trim(s)` | `TRIM(s)` | **Portable** |
| `upcase(s)` / `lowcase(s)` | `UPPER(s)` / `LOWER(s)` | **Portable** |
| `catx(sep, a, b, c)` | `concat_ws(sep, a, b, c)` — skips NULLs | PG / MySQL / Snowflake — BigQuery: `ARRAY_TO_STRING([a, b, c], sep)` |
| `missing(x)` numeric | `x IS NULL` | **Portable** |
| `missing(x)` char | `x IS NULL OR x = ''` — SAS treats blanks as missing | **Portable** |
| `ifn(cond, a, b)` | `CASE WHEN cond THEN a ELSE b END` | **Portable** |
| `max of (a, b, c)` | `GREATEST(a, b, c)` | Most engines — SQL Server needs `CASE WHEN` |
| `min of (a, b, c)` | `LEAST(a, b, c)` | Most engines — SQL Server needs `CASE WHEN` |

### `PROC UNIVARIATE` → `PERCENTILE_CONT`

Standard SQL — works on Postgres, Oracle, SQL Server, Snowflake, BigQuery, Redshift, DuckDB.
Parity caveat: `PERCENTILE_CONT` interpolates linearly; SAS defaults to `QNTLDEF=5`
(averaged inverted CDF), so values differ at non-integer positions — `semantics.md`
§ PROC UNIVARIATE defaults.

```sql
SELECT
  customer_id,
  PERCENTILE_CONT(0.5)  WITHIN GROUP (ORDER BY amount) AS median,
  PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY amount) AS q1,
  PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY amount) AS q3
FROM "${projectKey}_transactions"
GROUP BY customer_id
```

### `RETAIN` state machines → `LAG` + cumulative sums

Standard SQL window functions + CTEs — portable across engines. The only non-portable bit below is `COUNT(*)::bigint` (PG cast syntax); other engines use `CAST(COUNT(*) AS BIGINT)`.

SAS:
```sas
retain last_plan plan_before_change nb_changes;
if first.customer_id then do;
  last_plan = current_plan;
  nb_changes = 0;
end;
if current_plan ne last_plan then do;
  plan_before_change = last_plan;
  last_plan = current_plan;
  nb_changes = nb_changes + 1;
end;
if last.customer_id then output;
```
→
```sql
WITH ordered AS (
  SELECT customer_id, plan, date,
    LAG(plan) OVER (PARTITION BY customer_id ORDER BY date) AS prev_plan
  FROM "${projectKey}_events"
),
changes AS (
  SELECT *,
    CASE WHEN prev_plan IS NOT NULL AND plan <> prev_plan THEN 1 ELSE 0 END AS is_change
  FROM ordered
),
per_cust_last_change AS (
  SELECT customer_id, MAX(date) AS last_change_date
  FROM changes WHERE is_change = 1
  GROUP BY customer_id
),
change_details AS (
  SELECT co.customer_id, co.prev_plan AS plan_before_change, co.date
  FROM changes co
  JOIN per_cust_last_change lc
    ON co.customer_id = lc.customer_id AND co.date = lc.last_change_date
),
counts AS (
  SELECT customer_id, COUNT(*)::bigint AS nb_changes
  FROM changes WHERE is_change = 1
  GROUP BY customer_id
),
all_customers AS (
  SELECT DISTINCT customer_id FROM "${projectKey}_events"
)
SELECT
  ac.customer_id,
  COALESCE(cd.plan_before_change, 'No change') AS plan_before_change,
  COALESCE(cnt.nb_changes, 0) AS nb_plan_changes
FROM all_customers ac
LEFT JOIN change_details cd ON ac.customer_id = cd.customer_id
LEFT JOIN counts cnt ON ac.customer_id = cnt.customer_id
```

Use `"${projectKey}_tablename"` as the table reference — DSS substitutes `${projectKey}` at run time and Postgres is case-sensitive on identifiers.

#### Visual-only fallback (no SQL connection available)

When the flow runs on a Filesystem connection (DSS engine, no SQL push-down), the SQL recipe above is unavailable. The state machine still maps to **all-visual recipes** — Python is NOT the answer. The pattern is a **four-recipe pipeline using a composite "date|prev_value" marker** to recover `prev_plan` at the latest change row per partition:

1. **Window-lag** — partition customer_id, order by date asc; `--compute 'lag:plan_family_name:1'`. Output adds `plan_family_name_lag1` per row.

2. **Prepare-markers** — adds `change_flag` (0/1 derived from lag vs current) and a composite text marker that encodes `last_update_date|plan_family_name_lag1` only on change rows:

```bash
dku recipe add-formula prepare_plan_state_markers --column change_flag \
    --expr 'if(isBlank(plan_family_name_lag1) || plan_family_name == plan_family_name_lag1, 0, 1)'
dku recipe add-formula prepare_plan_state_markers --column change_composite \
    --expr 'if(change_flag == 1, last_update_date + "|" + plan_family_name_lag1, "")'
# Then: dku dataset set-schema OUTPUT -d '... change_flag: bigint ...'
# (GREL formula columns default to STRING; downstream Window's sum:change_flag fails on STRING.)
```

3. **Window-aggregate** — partition customer_id, order asc; aggregate over the partition with `sum:change_flag` (cumulative count of transitions = `nb_plan_changes`) and `max:change_composite` (lexicographic max of `YYYY-MM-DD|plan` picks the LATEST change's marker because ISO date prefixes sort chronologically):

```bash
dku recipe create-window window_plan_state_agg \
    -i plan_state_markers --output-ds plan_state_aggregated \
    -k customer_id --order-key 'last_update_date' \
    --compute 'sum:change_flag:' --compute 'max:change_composite:' \
    --compute 'rowNumber::' --compute 'count:customer_id:' \
    --rename 'change_flag_sum:nb_plan_changes' \
    --rename 'change_composite_max:composite_max' \
    --rename 'rownumber:rn' --rename 'customer_id_count:cnt' \
    --post-filter 'rn == cnt' -P PROJ
```

4. **Prepare-final** — split the composite back into `last_change_date` + `plan_before_change`, compute `time_since_last_change`, and bin:

```bash
dku recipe add-formula prepare_plan_state_final --column last_change_date \
    --expr 'if(composite_max == "", "", split(composite_max, "|")[0])'
dku recipe add-formula prepare_plan_state_final --column plan_before_change \
    --expr 'if(composite_max == "", "No change", split(composite_max, "|")[1])'
dku recipe add-formula prepare_plan_state_final --column time_since_last_change \
    --expr 'if(isBlank(last_change_date), "", "" + diff(asDateOnly(last_change_date, "yyyy-MM-dd"), asDateOnly("2024-12-01", "yyyy-MM-dd"), "months"))'
```

**Why the composite marker.** `max(date)` over the partition gives the latest change date, but the Window aggregation can't read `prev_plan` AT that latest-change row directly — `last_value` on a string returns the value at the partition's last row regardless of the change_flag. Encoding `(date, prev_plan)` as a single sortable string lets `max` pick the row chronologically and the post-pivot Prepare splits it back. Same trick applies to any "value of column Y at the row where condition X is last true per partition" SAS pattern. (Window's `firstLastNotNull` aggregation with DESC order and null-elsewhere markers gives the same answer; the composite handles ties deterministically.)
