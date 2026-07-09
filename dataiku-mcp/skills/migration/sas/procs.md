# SAS PROC Translation

Translation details for SAS PROCs and canonical visual patterns. SQL-recipe translations (function table, PERCENTILE_CONT, RETAIN state machines, visual-only fallback) live in `sql-translations.md`.

- [PROC → recipe](#proc--recipe) — main table, statistical PROCs, non-recipe PROCs, PROC FORMAT
- [Canonical patterns](#canonical-patterns) — PROC SQL decompose, merge+compute+bin, auto-remerge, transpose, FDA panels

## PROC → recipe

| PROC | Recipe | Type | Notes |
|---|---|---|---|
| `PROC SORT` | Sort | Visual | |
| `PROC SORT NODUPKEY` | Window or Distinct | Visual | **Canonical dedup mapping.** Keep the first FULL row per BY key → `create-window` with `rowNumber` + post-filter `rowNumber == 1` (no pre-Sort — DSS dedup needs no sorted input). Keys-only output acceptable → `create-distinct --on k1,k2` (output projects to the key columns) |
| `PROC SORT NODUP` | Distinct | Visual | Exact whole-row duplicates → `create-distinct` (no `--on`) |
| `PROC SQL` (simple filter/aggregation) | Prepare + Group | Visual | Decompose |
| `PROC SQL` (joins) | Join | Visual | Break into visual steps |
| `PROC SQL` (`where spedis/compged/complev(a,b) le N`) | Fuzzy Join | Visual | Never Python — § PROC SQL fuzzy match |
| `PROC SQL` (window / CTE / complex) | SQL recipe | Code | |
| `PROC SQL` (ODBC passthrough) | SQL recipe on a Dataiku SQL connection | Code | See `flow-patterns.md` § Recognizing enterprise driver scripts |
| `PROC MEANS` / `PROC SUMMARY` | Group | Visual | Only `n/mean/std/min/max/sum/count` — percentile/median → visual Window-rank pattern (`../ayx/tools-join-reshape.md` § Median / percentile); SQL `PERCENTILE_CONT` only when the input is already SQL-backed |
| `PROC UNIVARIATE` | Visual Window-rank pattern | Visual | Median/quantiles → Window-rank (`../ayx/tools-join-reshape.md` § Median / percentile). On SQL-backed input, `PERCENTILE_CONT(p) WITHIN GROUP (ORDER BY col)` keeps push-down (`sql-translations.md`). Never a plain Group, never Python |
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
| `%LET` | Project variable | Config | `dku project set-variables` |

### Statistical PROCs

Many SAS stats PROCs land in Python — but the regression / classification family (LOGISTIC / REG / GLM-as-regression / HPLOGISTIC / GENMOD-as-GLM) are **Visual ML**, not Python. See `ml-scenarios.md` § Visual ML for the canonical `dku ml` chain. The EDA Univariate recipe (`create-eda-univariate`) covers univariate descriptives (means / quantiles / frequencies) without code — reach for it before Python. **Bivariate correlation has no dedicated recipe** (Statistics correlation cards are UI-only): compute it visually via sum-of-products algebra (Group no-key → Prepare) or as a SQL/Python code recipe — and, as in Alteryx, it's often analysis-only, not flow logic (`../ayx/tools-predictive-ml.md` § PearsonCorrelation).

| PROC | Recipe | Python library (when needed) |
|---|---|---|
| `PROC TTEST` | Python — **code, no no-code recipe** (t-test cards are UI worksheet-only; often analysis-only, not flow logic) | `scipy.stats.ttest_ind` / `ttest_rel` / `ttest_1samp` |
| `PROC CORR` | Visual sum-of-products algebra (Group no-key → Prepare), or SQL `CORR()` (**code**) — often analysis-only, not flow logic (`../ayx/tools-predictive-ml.md` § PearsonCorrelation) | `pandas.DataFrame.corr` (methods: pearson/spearman/kendall) |
| `PROC LOGISTIC` / `PROC HPLOGISTIC` | **Visual ML** (classification) | — algorithm names: `ml-scenarios.md` § Visual ML |
| `PROC REG` (linear regression with prediction) | **Visual ML** (regression) | — |
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

**Detector:** a draft Python recipe whose output is `{status: "ok"}` or any non-data row is ML setup leaking into the Flow — stop; ML configuration/training is `ml-scenarios.md` § Visual ML.

Note: Statistics worksheet cards live on the dataset in the Lab, not in the flow — downstream recipes can't consume them. If the SAS program feeds p-values or coefficients into a later step, write the Python recipe and emit a results dataset.

### PROCs that are NOT recipes

Some PROCs migrate to Dataiku features outside the Flow. Don't force them into a recipe.

| PROC | Dataiku answer | Why it's not a recipe |
|---|---|---|
| `PROC SGPLOT` / `SGPANEL` / `SGSCATTER` | Dataiku **Chart** on the output dataset, or **Dashboard tile** | Plots don't produce data. Migrate to a chart insight (`dku insight create NAME --type chart --ds DATASET`) or a dashboard insight, not a Python recipe that writes a PNG |
| `PROC TEMPLATE` (ODS graphics templates) | Dashboard styling / shared chart config | Presentation layer, not a pipeline step |
| `PROC REPORT` / `PROC TABULATE` | Dashboard with **pivot-table insight** + cross-tab Group/Pivot recipes for the data | These are reporting, not transformation. Migrate the *data prep* as Group + Pivot; migrate the *layout* as a dashboard |
| `PROC COMPARE` | **Phase 4 verification**, not a migrated step | One-off parity → `dku --format json dataset head` on both sides during integration test (`../references/workflow.md` § Phase 4 — Integration test). A *scheduled* production compare → dataset checks in a scenario (`ml-scenarios.md` § Checks) |
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

### PROC SQL fuzzy match (`from A, B where spedis(a,b) le N`) → Fuzzy Join (NOT Python)

A cross join filtered by a spelling-distance threshold is a **Fuzzy Join** (`create-fuzzy-join`) — never a Python recipe. A Levenshtein threshold reproduces the keep/reject split without the exact SAS metric (`functions-formats.md` § Fuzzy / approximate string matching).

```sas
proc sql;
    create table fuzzy_match as
    select a.id, a.name as name_a, b.name as name_b
    from left_tbl a, right_tbl b
    where spedis(a.name, b.name) le 25;
quit;
```
→
```bash
# Both sides name the match column 'name' — pre-rename so both survive the join
dku recipe create prep_right -t prepare -i right_tbl --output-ds right_r -P PROJ
dku recipe add-rename prep_right --from name --to name_b -P PROJ
dku recipe apply-schema prep_right -P PROJ && dku recipe run prep_right -P PROJ --wait

dku recipe create-fuzzy-join fuzzy_match_names -i left_tbl -i right_r \
    --output-ds fuzzy_match --fuzzy-key name=name_b --max-distance 2 \
    --join-type INNER -P PROJ
dku recipe run fuzzy_match_names -P PROJ --wait
```

Traps: a SAS threshold `where` is INNER, but `--join-type` defaults to LEFT — unmatched left rows leak through with empty right columns. Same-named columns don't get `create-join`'s `_1`/`_2` suffixes — only one copy survives, so pre-rename one side. `--max-distance` defaults to 1 — single-edit pairs only.

### Merge + compute + bin → Join + Prepare (NOT SQL)

*Merge a lookup onto a master, compute a derived column, bin it* — **Join + Prepare**, not SQL.

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

This is **not** a Window aggregate. The DSS Window recipe (`create-window`) does not produce a global mean/stddev attached per row even with unbounded frame settings: with no partition and `enableLimits=true, limitPreceding=false, limitFollowing=false`, each row still gets its own value as the aggregate. Use the three-recipe pattern:

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

The `NOTE: The query requires remerging summary statistics back with the original data` log line is the detector. The same pattern covers PROC MEANS output joined back to the input via a manual `proc sql`.

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

SQL first — one engine per flow (migration `SKILL.md` permanent rules); a Python recipe pulls every row through DSS memory.

```bash
# 1. Filter screen failures (Prepare filter: ARMCD != "SCRNFAIL")
# 2. Arm numbering → SQL recipe (output must pre-exist in TABLE mode —
#    flow-patterns.md § One SQL recipe per passthrough):
#    SELECT *, DENSE_RANK() OVER (ORDER BY ARM) AS arm_num FROM "${projectKey}_dm_real"
# 3. One SQL recipe per demographic variable (SUM(CASE WHEN arm_num=k THEN 1 ELSE 0 END) AS arm_k_count)
# 4. PERCENTILE_CONT summary stats by arm
```
