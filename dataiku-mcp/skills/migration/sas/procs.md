# SAS PROC Translation

Translation details for SAS PROCs, canonical visual patterns, and SQL-recipe translations.

## PROC → recipe

| PROC | Recipe | Type | Notes |
|---|---|---|---|
| `PROC SORT` | Sort | Visual | |
| `PROC SORT NODUPKEY` | Sort + Prepare (RemoveDuplicates) | Visual | First row per BY combo |
| `PROC SORT NODUP` | Prepare (RemoveDuplicates) | Visual | Exact row duplicates only |
| `PROC SQL` (simple filter/aggregation) | Prepare + Group | Visual | Decompose |
| `PROC SQL` (joins) | Join | Visual | Break into visual steps |
| `PROC SQL` (window / CTE / complex) | SQL recipe | Code | |
| `PROC SQL` (ODBC passthrough) | SQL recipe on a Dataiku SQL connection | Code | See Enterprise driver scripts below |
| `PROC MEANS` / `PROC SUMMARY` | Group | Visual | Only `n/mean/std/min/max/sum/count` — percentile/median/mode need SQL or Python |
| `PROC UNIVARIATE` | SQL recipe first, Python as fallback | SQL / Code | SQL recipe with `PERCENTILE_CONT(p) WITHIN GROUP (ORDER BY col)` preserves push-down. Python only when the engine has no percentile function |
| `PROC FREQ` | Group (+ Pivot for multi-dim) | Visual | One-way frequencies → Group with count. Two-way cross-tabs (`TABLES a*b`) → Group by `(a, b)` then Pivot with `a` as row key, `b` as column key |
| `PROC TRANSPOSE` | Pivot | Visual | `ID` → pivot column, `VAR` → value. Unmatched cells become `.` (missing), not 0 |
| `PROC LOGISTIC` / `PROC REG` / `PROC GLM` | AutoML | Visual | Binary classification / regression |
| `PROC CLUSTER` / `PROC FASTCLUS` | AutoML | Visual | Clustering |
| `PROC IMPORT` | Dataset upload | — | `--type UploadedFiles` |
| `PROC EXPORT` | Dataset download / Sync | — | |
| `PROC SURVEYSELECT` | Sample (or train/test split in AutoML) | Visual | Random/stratified; for `samprate=0.7 outall` use the Sample recipe's train/test mode |
| `PROC FORMAT value …` | Prepare (formula with nested `if`) | Visual | Inline into a single formula — don't create a separate format artifact |
| `PROC APPEND` | Stack | Visual | |
| `PROC RANK` | Prepare (formula) or Window | Visual | |
| `PROC STDIZE` / `PROC STANDARD` | Prepare (Rescale processor) | Visual | Z-score / min-max / range standardisation. `STANDARD` uses sample stddev (`n-1`); `STDIZE` defaults to `method=STD` — same result |
| `PROC TRANSREG` | AutoML preprocessing (one-hot, impact, flag-miss) or Python (`category_encoders`) | Visual / Code | Most SAS uses are categorical encoding — let AutoML handle it. Spline / Box-Cox transforms need `patsy` or `statsmodels` in a Python recipe |
| `PROC PRINCOMP` | AutoML preprocessing (PCA reduction) or Python (`sklearn.decomposition.PCA`) | Visual / Code | Reach for AutoML when PCA feeds a downstream model; Python when the scores need to feed a downstream recipe (AutoML's PCA is internal to the training pipeline) |
| `LIBNAME` | Connection | Config | `dku connection list` |
| `%LET` | Project variable | Config | `dku project set-variable` |

### Statistical PROCs

Many SAS stats PROCs land in Python — but the regression / classification family (LOGISTIC / REG / GLM-as-regression / HPLOGISTIC / GENMOD-as-GLM) are **Visual ML**, not Python. See § Visual ML below for the canonical `dku ml` chain. The Statistics recipe handles basic univariate/bivariate descriptives (means / medians / correlations) without code — reach for it before Python.

| PROC | Recipe | Python library (when needed) |
|---|---|---|
| `PROC TTEST` | Statistics recipe (paired / independent) | `scipy.stats.ttest_ind` / `ttest_rel` / `ttest_1samp` |
| `PROC CORR` | Statistics recipe (correlation matrix) | `pandas.DataFrame.corr` (methods: pearson/spearman/kendall) |
| `PROC LOGISTIC` / `PROC HPLOGISTIC` | **Visual ML** (`LOGISTIC_REGRESSION`) | — (see § Visual ML) |
| `PROC REG` (linear regression with prediction) | **Visual ML** (`LEASTSQUARE_REGRESSION` / `RIDGE_REGRESSION`) | — |
| `PROC GLM` for regression (`MODEL y = x1 x2;` with `PREDICT`) | **Visual ML** (regression) | — |
| `PROC GLM` for ANOVA / `PROC ANOVA` (no prediction, just F-test) | Python recipe | `statsmodels.formula.api.ols` + `anova_lm` |
| `PROC GENMOD` (binomial link → classification; gaussian link → regression with prediction) | **Visual ML** (classification or regression) | `statsmodels.genmod.GLM` only when the link function isn't supported (Poisson / Gamma) |
| `PROC MIXED` | Python recipe | `statsmodels.MixedLM` |
| `PROC GLIMMIX` | Python recipe | `statsmodels.BinomialBayesMixedGLM` / `GEE` / `MixedLM` with link fn. No one-liner — match the distribution + link + random-effects spec from the SAS call |
| `PROC PHREG` / `PROC LIFETEST` | Python recipe | `lifelines` (Cox, Kaplan-Meier) |
| `PROC SURVEYMEANS` / `SURVEYREG` / `SURVEYLOGISTIC` | Python recipe | `statsmodels.survey` (or bespoke weighted IQR/variance) |
| `PROC FACTOR` | Python recipe | `factor_analyzer` |
| `PROC DISCRIM` | **Visual ML** (classification) or Python | `sklearn.discriminant_analysis.LinearDiscriminantAnalysis` |
| `PROC NPAR1WAY` | Python recipe | `scipy.stats.wilcoxon` / `mannwhitneyu` / `kruskal` |
| `PROC ARIMA` | Time Series Preparation plugin (basic) or Python | `statsmodels.tsa.arima.ARIMA` / `SARIMAX` |
| `PROC ESM` | Time Series Preparation plugin | `statsmodels.tsa.holtwinters` as fallback |

**Rule: ML setup is NEVER a Python recipe in the Flow.** Recipes produce data; ML configuration / training is a *visual* workflow. The Flow representation is `train_*` recipe → Saved Model → Predict (`prediction_scoring`) recipe — produced via the `dku ml` namespace, not by writing Python that calls `dataikuapi`. If you find yourself drafting a Python recipe whose output is `{status: "ok"}` or any non-data row, stop and use § Visual ML below.

Note: Statistics recipe results are a summary object on the dataset, not an output dataset — downstream recipes can't consume them. If the SAS program feeds p-values or coefficients into a later step, write the Python recipe and emit a results dataset.

### PROCs that are NOT recipes

Some PROCs migrate to Dataiku features outside the Flow. Don't force them into a recipe.

| PROC | Dataiku answer | Why it's not a recipe |
|---|---|---|
| `PROC SGPLOT` / `SGPANEL` / `SGSCATTER` | Dataiku **Chart** on the output dataset, or **Dashboard tile** | Plots don't produce data. Migrate to a chart definition (`dku chart create`) or a dashboard insight, not a Python recipe that writes a PNG |
| `PROC TEMPLATE` (ODS graphics templates) | Dashboard styling / shared chart config | Presentation layer, not a pipeline step |
| `PROC REPORT` / `PROC TABULATE` | Dashboard with **pivot-table insight** + cross-tab Group/Pivot recipes for the data | These are reporting, not transformation. Migrate the *data prep* as Group + Pivot; migrate the *layout* as a dashboard |
| `PROC COMPARE` | **Phase 4 verification**, not a migrated step | A parity/QA tool. Replace with `dku --format json dataset head` on both sides during integration test (see SKILL.md § Phase 4) |
| `PROC PRINT` | Implicit (DSS shows data in the Explore tab) | Not a migration target |
| `PROC CONTENTS` | `dku dataset schema DS -P PROJ` | Metadata lookup, not a recipe |

### Display-only `format` is NOT a value assignment

`format var fmt.;` only affects how `PROC PRINT` renders — the stored value is unchanged, safe to skip. `var = put(var, fmt.);` (an assignment) IS a value transformation and must be migrated.

### `PROC FORMAT` range notation

Inline into a nested `if()` formula. Do not create a separate format artifact.

| SAS range | Meaning | GREL |
|---|---|---|
| `low-N` | `≤ N` | `var <= N` |
| `N-high` | `≥ N` | `var >= N` |
| `N<-M` | `(N, M]` | `var > N && var <= M` |
| `N-<M` | `[N, M)` | `var >= N && var < M` |
| `N<-<M` | `(N, M)` | `var > N && var < M` |
| `other` | catch-all | final `else` |

Example:
```sas
proc format;
    value spend_tier
        low-500    = 'Low Spender'
        500<-5000  = 'Medium Spender'
        5000<-high = 'High Spender';
run;
data out; set in; spend_category = put(total_spend, spend_tier.); run;
```
→
```bash
dku recipe add-formula post_join --column spend_category \
    --expr 'if(total_spend <= 500, "Low Spender", if(total_spend <= 5000, "Medium Spender", "High Spender"))' \
    -P PROJ
```

## Canonical patterns

### PROC SQL (filter + group) → visual recipes

```sas
proc sql;
    create table out as
    select key, count(x) as n_x, sum(y) as total_y
    from src
    where cond
    group by key
    order by key;
quit;
```
→
```bash
# 1. Filter (Prepare with FilterOnCustomFormula)
dku recipe create-filter filter_src -i src --output-ds src_filtered \
    -f 'cond_as_grel_expr' -P PROJ && \

# 2. Group — --no-global-count drops the default DSS count column
dku recipe create-group agg_src -i src_filtered --output-ds src_summary \
    -k key --agg 'x:count' --agg 'y:sum' --no-global-count -P PROJ && \

# 3. Rename to match PROC SQL aliases (DSS auto-names them {col}_{func})
dku dataset create src_summary_final --type Filesystem -c filesystem_managed -P PROJ && \
dku recipe create rename_for_parity -t prepare -i src_summary --output-ds src_summary_final -P PROJ && \
dku recipe add-rename rename_for_parity \
    --mappings '{"x_count":"n_x","y_sum":"total_y"}' -P PROJ && \
dku recipe apply-schema rename_for_parity -P PROJ && \

dku recipe run filter_src -P PROJ --wait && \
dku recipe run agg_src -P PROJ --wait && \
dku recipe run rename_for_parity -P PROJ --wait
```

SAS `order by` produces an ordered output; Dataiku Group output is unordered. If downstream relies on order, add a Sort recipe.

### Merge + compute + bin → Join + Prepare (NOT SQL)

This is the most common DATA step in SAS analytics and the most common place agents over-reach for SQL. The pattern is *merge a lookup onto a master, compute a derived column, bin it*. It is **Join + Prepare**, not SQL.

```sas
data appl_tenure (keep=customer_id tenure_cat tenure_y);
    length tenure_cat $35;
    merge appl_reference_table(in=a) extract_contract(in=b);
    by customer_id;
    if a;
    tenure_m = intck('month', account_creation_date, &day_M1.) + 1;
    tenure_y = round(tenure_m / 12, 0.1);
    if      tenure_y < 1  then tenure_cat = "1. Less than 1 year";
    else if tenure_y < 2  then tenure_cat = "2. 1 year";
    else if tenure_y <= 3 then tenure_cat = "3. Between 2 and 3 years";
    else                       tenure_cat = "4. More than 3 years";
run;
```
→
```bash
# 1. Join recipe (LEFT)
dku recipe create-join join_ref_contract \
    -i appl_reference_table -i extract_contract \
    --output-ds appl_tenure_joined --join-key customer_id --join-type LEFT -P PROJ

# 2. Prepare recipe for compute + bin
dku recipe create appl_tenure -t prepare \
    -i appl_tenure_joined --output-ds appl_tenure -P PROJ

dku recipe add-formula appl_tenure --column tenure_m \
    --expr 'diff(asDateOnly(account_creation_date, "yyyy-MM-dd"), asDateOnly("2025-12-31", "yyyy-MM-dd"), "months") + 1' -P PROJ

dku recipe add-formula appl_tenure --column tenure_y \
    --expr 'round(numval(tenure_m) / 12 * 10) / 10' -P PROJ

dku recipe add-formula appl_tenure --column tenure_cat \
    --expr 'if(numval(tenure_y) < 1,  "1. Less than 1 year", if(numval(tenure_y) < 2,  "2. 1 year", if(numval(tenure_y) <= 3, "3. Between 2 and 3 years", "4. More than 3 years")))' -P PROJ

dku recipe add-delete-columns appl_tenure --columns tenure_m -P PROJ
dku recipe apply-schema appl_tenure -P PROJ
dku recipe run appl_tenure -P PROJ --wait
dku dataset info appl_tenure -P PROJ --recompute
```

When the SAS step has `if cond then x = round(x * a / b);` (conditional rescaling), fold it into a single GREL formula: `if(numval(m) < 12, round(numval(n) * 12 / numval(m)), numval(n))`. Still Join + Prepare.

**When this pattern genuinely needs SQL** — rare: the formula calls a function with no GREL equivalent (regex back-references, hyperbolic trig, crypto) or the step needs `LAG`/`LEAD` across rows.

### PROC SQL auto-remerge (`MEAN(col)` per row) → Group(no key) + CROSS Join + Prepare (NOT Window)

SAS PROC SQL silently auto-remerges aggregates back to row level when an unaggregated column is selected alongside an aggregate function:

```sas
proc sql;
    create table out as
    select id, annual_inc,
           MEAN(annual_inc) as mean_inc,
           STD(annual_inc)  as std_inc,
           ABS((annual_inc - MEAN(annual_inc)) / STD(annual_inc)) as std_from_mean
      from src;
quit;
/* NOTE: The query requires remerging summary statistics back with the original data. */
```

This is **not** a Window aggregate. The DSS Window recipe (`create-window`) does not produce a global mean/stddev attached per row even with unbounded frame settings — empirically, with no partition + `enableLimits=true, limitPreceding=false, limitFollowing=false`, each row still gets its own value as the aggregate. Reach for the three-recipe pattern instead:

```bash
# 1. Group with no key → 1-row global stats (drop the auto count column)
dku recipe create-group global_stats -i src --output-ds global_stats \
    --no-global-count \
    --agg 'annual_inc:avg,stddev' \
    --rename 'annual_inc_avg:mean_inc' \
    --rename 'annual_inc_stddev:std_inc' \
    -P PROJ

# 2. CROSS join the original with the 1-row global_stats → mean_inc / std_inc
#    on every row.
dku recipe create-join src_with_stats -i src -i global_stats \
    --output-ds src_with_stats -j CROSS -P PROJ

# 3. Prepare for the row-level derived column (and to drop unwanted carry-overs)
dku recipe create std_from_mean -t prepare -i src_with_stats --output-ds std_from_mean -P PROJ
dku recipe add-formula std_from_mean -c std_from_mean \
    -e 'abs((annual_inc - mean_inc) / std_inc)' -P PROJ
dku recipe apply-schema std_from_mean -P PROJ
dku recipe run std_from_mean -P PROJ --wait
```

**Rule of thumb:** if the SAS PROC SQL log says `NOTE: The query requires remerging summary statistics back with the original data`, the migration is Group + CROSS Join + Prepare. Three recipes, all visual. This is also the right pattern for SAS PROC MEANS output joined back to the input via a manual `proc sql`.

**When Window IS the right call:** the aggregate is per-partition or windowed by ordering (`MEAN(x) OVER (PARTITION BY k ORDER BY date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW)`), not global. Use Window with `--partition-key k --order-key date` and the appropriate frame.

### PROC TRANSPOSE → Pivot + Prepare

```sas
proc transpose data=manip_options_column out=pivoted (drop=_name_);
    by customer_id;
    var active_base_flg;
    id option;
run;
data pivoted; set pivoted; had_option_flg = 1; run;
```
→
```bash
dku recipe create-pivot pivot_options -i manip_options_filtered --output-ds pivoted \
    --row-key customer_id --column-key option --value-column active_base_flg \
    --agg-type MAX -P PROJ

dku recipe create add_had_flg -t prepare -i pivoted --output-ds pivoted_final -P PROJ
dku recipe add-formula add_had_flg --column had_option_flg --expr '1' -P PROJ
```

A constant flag is a one-line Prepare step. Not a reason to reach for `SELECT ..., 1 AS had_option_flg FROM ...`.

### FDA SDTM clinical trial panels

FDA SDTM analytical panels (demographics, liver, disposition, adverse events) follow a recognizable pattern: arm lookup + per-variable cross-tab with counts/percentages + PROC UNIVARIATE summary stats.

Three sub-patterns, in priority order:

| SAS pattern | Target | Fallback |
|---|---|---|
| Filter by arm code (`ARMCD ne 'SCRNFAIL'`) | Prepare (FilterOnCustomFormula) | — |
| `PROC SQL` CASE WHEN cross-tab of one var × arms with percentages | SQL recipe — the CASE WHEN / arm-total pattern is already what SAS generates. Join back to arm totals via a CTE or `COUNT(*) OVER ()` | Python only when the target connection is filesystem and Group + Pivot can't express the cross-tab |
| `PROC UNIVARIATE` with quantiles | SQL recipe using `PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY col)` (Postgres/Oracle/Snowflake/BigQuery/Redshift/SQL Server) | Python when the engine has no percentile function |

Why SQL first: the data is on the database. SQL keeps it there. A Python recipe pulls every row through DSS memory, computes stats, writes them back — on a clinical panel with 50k+ subjects the difference is 10s vs 20min.

```bash
# 1. Filter screen failures
dku recipe create-filter filter_real -i dm --output-ds dm_real \
    -f 'ARMCD != "SCRNFAIL"' -P PROJ

# 2. Arm numbering → SQL recipe with DENSE_RANK
dku dataset create dm_with_arm -P PROJ --type <SQLType> -c <sql_conn> \
    --definition '{"params":{"connection":"<sql_conn>","mode":"table","table":"${projectKey}_dm_with_arm"}}'
dku recipe create add_arm_num -t sql_query -i dm_real --output-ds dm_with_arm -P PROJ
dku recipe set-code add_arm_num -P PROJ --code @sql/arm_num.sql
# SELECT *, DENSE_RANK() OVER (ORDER BY ARM) AS arm_num FROM "${projectKey}_dm_real"
dku recipe apply-schema add_arm_num -P PROJ
dku recipe run add_arm_num -P PROJ --wait

# 3. One SQL recipe per demographic variable (SUM(CASE WHEN arm_num=k THEN 1 ELSE 0 END) AS arm_k_count)
# 4. PERCENTILE_CONT summary stats by arm
```

---

## SAS → SQL recipe translations

The rows below come in two flavours:

- **Portable (standard SQL)** — string ops, `CASE WHEN`, `IS NULL`, `GREATEST`/`LEAST` work as-is on Postgres, Snowflake, BigQuery, Redshift, Oracle, SQL Server, DuckDB.
- **Engine-specific** — date math (`AGE`, `make_interval`), numeric casts (`::numeric`, `::double precision`), and `to_char` format strings are **Postgres-specific**. The Postgres forms are verified on DSS 14.4 + PG. For other engines, swap in the native equivalents — see the `Dates (SQL recipe equivalents)` table above for cross-engine date math.

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

**Rule of thumb**: if you're on a non-Postgres SQL connection, start with the portable rows and substitute the engine-specific ones against the target engine's docs. The Postgres forms are what DSS + PG gives you out of the box and what was verified against a live `rds` connection.

### `PROC UNIVARIATE` → `PERCENTILE_CONT`

Standard SQL — works on Postgres, Oracle, SQL Server, Snowflake, BigQuery, Redshift, DuckDB.

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

**Why the composite marker.** `max(date)` over the partition gives the latest change date, but the Window aggregation can't read `prev_plan` AT that latest-change row directly — `last_value` on a string returns the value at the partition's last row regardless of the change_flag. Encoding `(date, prev_plan)` as a single sortable string lets `max` pick the row chronologically and the post-pivot Prepare splits it back. Same trick applies to any "value of column Y at the row where condition X is last true per partition" SAS pattern.

**`firstLastNotNull` alternative** — DSS Window has a `firstLastNotNull` aggregation that picks the first non-null in ordering. With order DESC and an empty-string-elsewhere marker treated as null, this gives the same answer without the composite. The composite approach is more portable across DSS versions and handles ties deterministically.

---
