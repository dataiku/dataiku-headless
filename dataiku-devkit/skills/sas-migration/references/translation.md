# SAS → Dataiku Translation

Recipe mapping, function/PROC translations, and the enterprise passthrough workflow. Read the `sas-migration` SKILL.md first for the migration phases; read `semantics.md` before translating any DATA step or MERGE that may silently change values.

Priority is always **Visual → SQL → Python**. Python is the last resort, not the default.

**Counter-reflex rule:** before writing a SQL recipe, read the SAS step out loud as *"merge, then compute a column, then bin it"*. If that sentence uses the words "merge/join" + "compute/formula" + "bin/case-when", it is a **Join + Prepare** chain, not a SQL recipe. Save SQL for steps that actually need window functions, percentiles, or multi-CTE logic.

---

## DATA step → recipe

| SAS construct | Recipe | Type | Notes |
|---|---|---|---|
| DATA step (filter/rename/compute) | Prepare | Visual | Processors: filter rows, rename, formula |
| DATA step (merge by key) | Join | Visual | `MERGE ... BY` |
| `merge A(in=a) B(in=b); by k; if a;` | Join (LEFT) | Visual | Keeps all A rows |
| `merge A(in=a) B(in=b); by k; if a and b;` | Join (INNER) | Visual | |
| `merge A(keep=c1 c2)` | Join + post-Prepare `add-delete-columns` | Visual | No `--keep-columns` flag — drop in a post-join Prepare |
| `SET ds1 ds2` (append) | Stack | Visual | |
| Sort + `if first.key` dedup | Sort + Prepare (RemoveDuplicates) | Visual | Keep first per group |
| Sort + count per group | Group | Visual | Not RETAIN — just aggregation |
| RETAIN with row comparison | SQL recipe | Code | `LAG()`/`LEAD()` window |
| Running total / cumulative | SQL recipe | Code | `SUM() OVER (ORDER BY ...)` |
| Hash object lookup | Join | Visual | Hash = in-memory lookup with equality keys |
| Multiple outputs (IF/OUTPUT) | Multiple Prepare filters | Visual | One filter per output |
| DO loop generating rows | Python recipe | Code | Loops that create rows from nothing |
| Array processing | Prepare (formula) | Visual | Column-wise → formula per column |
| UPDATE statement | Prepare + Join | Visual | Applies only non-missing values from transaction |
| MODIFY (in-place) | Python recipe | Code | No Dataiku equivalent — write a new dataset |
| `DATA _NULL_` (compute/log only) | Python recipe (no output) | Code | |
| `SELECT/WHEN` | Prepare (FindReplace or formula) | Visual | Multi-branch conditional |

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
| `PROC FREQ` | Group | Visual | Cross-tabs → Group with count |
| `PROC TRANSPOSE` | Pivot | Visual | `ID` → pivot column, `VAR` → value. Unmatched cells become `.` (missing), not 0 |
| `PROC LOGISTIC` / `PROC REG` / `PROC GLM` | AutoML | Visual | Binary classification / regression |
| `PROC CLUSTER` / `PROC FASTCLUS` | AutoML | Visual | Clustering |
| `PROC IMPORT` | Dataset upload | — | `--type UploadedFiles` |
| `PROC EXPORT` | Dataset download / Sync | — | |
| `PROC SURVEYSELECT` | Sample | Visual | Random/stratified |
| `PROC FORMAT value …` | Prepare (formula with nested `if`) | Visual | Inline into a single formula — don't create a separate format artifact |
| `PROC APPEND` | Stack | Visual | |
| `PROC RANK` | Prepare (formula) or Window | Visual | |
| `PROC STDIZE` | Prepare (rescale) | Visual | |
| `LIBNAME` | Connection | Config | `dku connection list` |
| `%LET` | Project variable | Config | `dku project set-variable` |

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

## RETAIN is usually not Python

Most RETAIN patterns are group aggregations or window functions. Classify before coding.

| SAS pattern | Actually is | Recipe |
|---|---|---|
| Sort + `if last.key then output` with count | Group count | Group |
| Sort + `if first.key then output` | Keep first per group | Sort (desc) + RemoveDuplicates |
| Sort + `if last.key then output` | Keep last per group | Sort + RemoveDuplicates |
| `retain counter; if first.key then counter=0; counter+1;` | Group count | Group |
| `retain max_val; if val > max_val then max_val=val;` | Group max | Group |
| `retain sum_val; sum_val + val; if last.key then output` | Group sum | Group |
| `retain last_plan; if plan ne last_plan then ...` | Row comparison | SQL recipe (`LAG` window) |
| `retain balance; balance + amt;` (all rows) | Running sum | SQL recipe (`SUM() OVER (ORDER BY ...)`) |
| `cumsum + x;` (SUM statement) | Running sum (missing-safe, treats `.` as 0) | SQL recipe |
| `retain prev; diff = val - prev; prev = val;` | Lag difference | SQL recipe (`val - LAG(val) OVER (...)`) |

**SUM statement vs explicit RETAIN+add:**
- `total + x;` (SUM statement) — auto-retains, treats missing `x` as 0. Safe.
- `retain total 0; total = total + x;` — when `x` is missing, `total` becomes `.` permanently. Dangerous.

Migration must check which pattern the SAS code uses. If SUM statement → `COALESCE(val, 0)` in SQL.

---

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
    --expr 'dateDifference(parseDate(account_creation_date, "yyyy-MM-dd"), parseDate("2025-12-31", "yyyy-MM-dd"), "months") + 1' -P PROJ

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

Run the same SAS program against inline `datalines;` blocks of the same synthetic source tables (strip `connect to odbc as remote`, replace `to_date` with SAS date literals). Pull both sides via `dku dataset head -o json` and compare row-by-row. On the first run, expect small mismatches on `.5` boundaries — usually engine rounding semantics. See Rounding below.

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

## Function mapping (SAS → GREL / SQL / processor)

GREL function names are **case-sensitive**. See the `dataiku` skill's `references/formulas.md` for the full GREL reference and `references/prepare-processors.md` for the processor catalog.

### Core

| SAS | GREL | Wrong guess |
|---|---|---|
| `PROPCASE(s)` | `toTitlecase(s)` | ~~`toTitleCase(s)`~~ — lowercase 'c' |
| `LOWCASE(s)` | `toLowercase(s)` | ~~`lower(s)`~~ |
| `UPCASE(s)` | `toUppercase(s)` | ~~`upper(s)`~~ |
| `PUT(n, BEST12.)` | `toString(n)` | ~~`str(n)`~~ |
| `INPUT(s, BEST.)` | `toNumber(s)` | ~~`int(s)`~~ |
| `SUBSTR(s, pos, len)` | `substring(s, pos-1, pos-1+len)` | GREL is 0-based; `to` is exclusive index, NOT length |
| `ROUND(n, .01)` | `round(n * 100) / 100` for non-negative `n`; for any sign see § Rounding parity | ~~`round(n, 2)`~~ — GREL `round()` takes 1 arg. The short form rounds negatives differently from SAS |
| `INTCK('day', d1, d2)` | `diff(d1, d2, 'days')` | ~~`dateDiff()`~~ — doesn't exist |
| `INTCK('month', d1, d2)` | `diff(d1, d2, 'months')` | SAS counts boundary crossings, not elapsed |
| `LOG(n)` | `ln(n)` | SAS `LOG` = natural log; GREL `log` = base-10 |
| `EXP(n)` | `exp(n)` | Both base-e — consistent |

### String

| SAS | GREL | Note |
|---|---|---|
| `TRIM(s)` | `strip(s)` | SAS `trim` removes trailing only; GREL `strip` is both sides |
| `STRIP(s)` | `strip(s)` | Same — both sides |
| `LEFT(s)` | `strip(s)` | SAS left-aligns; closest is `strip` |
| `COMPRESS(s)` | `replace(s, ' ', '')` | Removes all spaces |
| `COMPRESS(s, chars)` | chained `replace(...)` | One per character |
| `COMPRESS(s, , 'kd')` | no direct GREL | Keep only digits — use SQL `REGEXP_REPLACE` |
| `SCAN(s, n)` | `split(s, ' ')[n-1]` | SAS is 1-based; GREL array is 0-based |
| `COUNTW(s)` | `split(s, ' ').length()` | |
| `INDEX(s, sub)` | `indexOf(s, sub)` | SAS returns 0 if not found; GREL returns -1 |
| `FIND(s, sub, 'i')` | `indexOf(toLowercase(s), toLowercase(sub))` | Case-insensitive |
| `TRANWRD(s, old, new)` | `replace(s, old, new)` | |
| `CATS(a, b, c)` | `strip(a) + strip(b) + strip(c)` | |
| `CATX(sep, a, b, c)` | `join([strip(a), strip(b), strip(c)], sep)` | |
| `CAT(a, b)` | `a + b` | Preserves padding (rarely wanted) |
| `LENGTH(s)` | `length(s)` | |
| `IFC(cond, t, f)` | `if(cond, t, f)` | Inline character |
| `IFN(cond, t, f)` | `if(cond, t, f)` | Inline numeric |

`COMPRESS` modifiers: `k` = keep (instead of remove), `d` = digits, `a` = alpha, `s` = spaces, `p` = punct. `compress(s, , 'kd')` = keep only digits.

### Dates (SQL recipe equivalents — engine-specific)

SAS date functions don't have a single portable SQL equivalent. The column below shows the most common shape, but **check your target engine** — the exact function name varies (`DATEDIFF` / `MONTHS_BETWEEN` / `DATE_DIFF`), and so does the argument order. See the Postgres-specific forms in § SAS → SQL recipe translations below.

| SAS | Shape (varies per engine) | Note |
|---|---|---|
| `INTCK('month', d1, d2)` | Oracle: `MONTHS_BETWEEN(d2, d1)`; SQL Server: `DATEDIFF(month, d1, d2)`; BigQuery: `DATE_DIFF(d2, d1, MONTH)` | Counts discrete boundary crossings |
| `INTCK('year', d1, d2)` | `DATEDIFF(year, d1, d2)` — check engine syntax | `intck('year', 15MAR2024, 01JAN2026)` = 2 |
| `INTNX('month', d, n)` | MySQL/BigQuery: `DATE_ADD(d, INTERVAL n MONTH)`; Snowflake: `DATEADD(MONTH, n, d)` | Defaults to BEGINNING of target month |
| `INTNX('month', d, n, 'end')` | Wrap the above in `LAST_DAY(...)` if available | End of target month |
| `INTNX('month', d, n, 'sameday')` | Same base `DATE_ADD` / `DATEADD` | Preserves day-of-month |
| `DATEPART(dt)` | `CAST(dt AS DATE)` | Portable |
| `MDY(m, d, y)` | `MAKE_DATE(y, m, d)` (PG/BigQuery) or `DATE(y, m, d)` | Check engine |
| `TODAY()` | `CURRENT_DATE` | Portable |
| `INPUT(s, DATE9.)` | MySQL: `STR_TO_DATE(s, '%d%b%Y')`; Snowflake: `TO_DATE(s, 'DDMONYYYY')`; PG: `TO_DATE(s, 'DDMonYYYY')` | Parses `'15MAR2024'` |
| `INPUT(s, YYMMDD10.)` | `CAST(s AS DATE)` | Portable for ISO dates |

`INPUT(s, COMMA10.)` strips `$` and `,` — use `toNumber(replace(replace(col, '$', ''), ',', ''))`.

### SAS formats → processors

| SAS | Processor |
|---|---|
| `PUT(var, DATE9.)` | `DateFormatter` |
| `PUT(var, COMMA12.2)` | `NumericalFormatConverter` |
| `INPUT(var, BEST.)` | `TypeSetter` (string → numeric) |
| `VALUE` (discrete) | `ColumnCopier` + `FindReplace` |
| `VALUE` (ranges) | `BinnerProcessor` (or formula) |
| `INFORMAT` (parse) | `DateParser` |
| `ROUND(x, .01)` | `RoundProcessor` |
| `MEAN(OF col1-col3)` | `MeanProcessor` |
| `SUM(OF col1-col3)` | `NumericalCombinator` (op: `ADD`) |
| Missing fill (numeric) | `ImputeWithValue` (method: `MEAN`/`MEDIAN`) |
| Missing fill (string) | `FillEmptyWithValue` |
| `RENAME old=new` | `ColumnRenamer` |
| `LOWCASE` / `UPCASE` | `LowerCaseTransformer` / `UpperCaseTransformer` |

### Prepare-step CLI examples

```bash
# Filter by value (SAS: WHERE status = 'A')
dku recipe add-filter-rows RECIPE --column status --values "A" --action KEEP_ROW -P PROJ

# Filter by formula (SAS: WHERE amount > 0)
dku recipe add-filter-rows RECIPE --formula "amount > 0" --action KEEP_ROW -P PROJ

# Remove empty rows (SAS: IF col=. THEN DELETE)
dku recipe add-step RECIPE -t RemoveRowsOnEmpty --params '{"columns":["col"], "keep":false, "appliesTo":"SINGLE_COLUMN"}' -P PROJ

# Formula column (SAS: LTV = MORTDUE / VALUE)
dku recipe add-formula RECIPE -c LTV -e 'MORTDUE / VALUE' -P PROJ

# Impute missing (SAS: IF var=. THEN var=mean)
dku recipe add-step RECIPE -t ImputeWithValue --params '{"appliesTo":"SINGLE_COLUMN", "columns":["MORTDUE"], "method":"MEAN"}' -P PROJ

# Fill empty string
dku recipe add-fill-empty RECIPE --column JOB --value Unknown -P PROJ

# Copy + recode (SAS: IF BAD=0 THEN OUTCOME='Paid')
dku recipe add-step RECIPE -t ColumnCopier --params '{"inputColumn":"BAD", "outputColumn":"OUTCOME"}' -P PROJ
dku recipe add-find-replace RECIPE -c OUTCOME --find "0" --replace "Paid" -P PROJ

# Rename
dku recipe add-rename RECIPE --from MORTDUE --to mortgage_due -P PROJ

# Bin numeric (SAS: PUT(x, spend_tier.) with VALUE format ranges)
dku recipe add-step RECIPE -t BinnerProcessor --params '{"column":"total_spend", "binnerMode":"CUSTOM", "customBoundaries":[500, 5000], "customBoundariesLabels":["Low","Medium","High"], "outputColumn":"spend_tier"}' -P PROJ

# Date parsing
dku recipe add-step RECIPE -t DateParser --params '{"appliesTo":"SINGLE_COLUMN", "columns":["date_col"], "formats":["M/d/yy"], "lang":"auto", "timezone_id":"UTC", "outCol":"", "outType":{"name":"out", "type":"date"}}' -P PROJ

# Date difference (input2 - input1)
dku recipe add-step RECIPE -t DateDifference --params '{"input1":"start", "compareTo":"COLUMN", "input2":"end", "output":"days_diff", "outputUnit":"DAYS", "timezone_id":"UTC"}' -P PROJ
```

### VisualIfRule operators

| Operator | Value field |
|---|---|
| `== [string]` | `string` |
| `!= [string]` | `string` |
| `>  [number]` (2 spaces) | `num` |
| `<  [number]` (2 spaces) | `num` |
| `>= [number]` | `num` |
| `<= [number]` | `num` |
| `contains` | `string` |
| `is empty` / `not empty` | — |

**Broken via API** (DSS bug): `regex`, `in [string]`, date/geo operators. Use GREL `match()` for regex, `switch()` for is-any-of.

---

## Rounding parity

SAS `ROUND(x, step)` is **half-away-from-zero** for any sign. Not every target matches, and the mismatch produces silent off-by-step parity breaks on `.5` boundaries. All four combinations (positive/negative × integer-multiple/double) matter.

| Path | Mode | Matches SAS? |
|---|---|---|
| SAS `ROUND(x, step)` | half-away-from-zero | ✓ (reference) |
| Oracle / SQL Server / Snowflake / BigQuery / Redshift `ROUND` | half-away-from-zero | ✓ |
| PostgreSQL `ROUND(numeric, int)` | half-away-from-zero | ✓ |
| PostgreSQL `ROUND(double precision)` (1-arg) | banker's (half-to-even) | ✗ |
| DuckDB `ROUND(numeric)` / `ROUND(double)` (v0.8+) | half-away-from-zero | ✓ |
| Python `round()` / `numpy.round` / `pandas.Series.round()` | banker's | ✗ |
| **Dataiku Prepare recipe `round(x)` (in-memory, Java `Math.round`)** | **round half up (toward +∞)** | ✓ for positives, ✗ for negatives |

Sample mismatches on `round(x, 1)`:

| x | SAS (half-away) | PG DOUBLE / Python (banker's) | DSS in-memory GREL `round(x*10)/10` |
|---|---|---|---|
| `1.25` | `1.3` | `1.2` | `1.3` |
| `8.25` | `8.3` | `8.2` | `8.3` |
| `-1.25` | `-1.3` | `-1.2` | **`-1.2`** |
| `-8.25` | `-8.3` | `-8.2` | **`-8.2`** |

**Key point**: the common advice "use GREL `round(x * 10) / 10` for 0.1 rounding" matches SAS only for non-negative inputs. Negative inputs diverge on every `.5` boundary. If the column can take negative values, pick one of the workarounds below.

**SQL recipe rule**: most engines match SAS for any sign — just write `ROUND(col, 1)`. On PostgreSQL with `DOUBLE PRECISION` columns, cast to `NUMERIC` first: `ROUND(val::numeric, 1)`.

**GREL workaround for any sign** (works on both in-memory and SQL push-down, verified on DSS 14.4 + PG):
```
if(x >= 0, floor(x * 10 + 0.5) / 10, 0 - floor(0 - x * 10 + 0.5) / 10)
```
The two-branch form handles the negative side correctly. The shorter `floor(x * 10 + 0.5) / 10` is only correct for non-negatives.

**Verification probe**: run `SELECT ROUND(1.25, 1), ROUND(-1.25, 1), ROUND(2.5, 0), ROUND(-8.25, 1)` on your target. SAS-compatible engines return `1.3, -1.3, 3, -8.3`. Anything else needs a cast or the two-branch workaround.

**Python (last resort)**:
```python
import numpy as np

def sas_round(x, step):
    scaled = x / step
    return np.floor(np.abs(scaled) + 0.5) * np.sign(scaled) * step

sas_round(1.25, 0.1)    # 1.3 ✓
sas_round(-1.25, 0.1)   # -1.3 ✓
```

Symptom of a rounding-mode mismatch in a parity check: off-by-step mismatches in rounded columns, always on values ending in exactly `.5`, often concentrated on rows with negative values when GREL `round(x*10)/10` was used blindly.

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

---

## AutoML

| SAS ML concept | Dataiku | Identify in SAS |
|---|---|---|
| Target variable | AutoML target | `dm_dec_target`, `target=`, `response` |
| Binary target (0/1) | Two-class classification | `BAD`, `CHURN`, `DEFAULT` |
| Continuous target | Regression | `PROC REG`, `PROC GLM` |
| No target | Clustering | `PROC CLUSTER` |
| Imputation, OHE, train/test | AutoML handles automatically | `SimpleImputer`, `OneHotEncoder`, `dm_traindf` |

```bash
dku ml create analysis -d dataset -t TARGET --task-type BINARY_CLASSIFICATION -P PROJ && \
dku ml train analysis -P PROJ --wait && \
dku ml deploy analysis -P PROJ
```

---

## SAS dates in Dataiku

1. **Ingest as STRING** (ISO `YYYY-MM-DD`). Setting `{"type":"date"}` on an uploaded CSV with string dates causes all values to become null without error.
2. **String-based ISO date filtering works** — lexicographic matches chronological:
   ```
   startsWith(txn_date, "2026-02")                     # "month of Feb 2026"
   txn_date >= "2026-02-01" && txn_date <= "2026-02-28" # range
   max(txn_date)                                        # latest per group
   ```
3. **`dateonly` JSON quirk** — `dku dataset head -o json` renders as `"2026-02-06 00:00:00"` (trailing midnight). Cosmetic; strip the time component in parity checks.
4. **SAS missing date (`.`) → Dataiku null.** In LEFT JOINs with no match, SAS emits `.`, Dataiku emits `null`. Normalize both to `None` in parity checks.
5. **Force `yymmdd10` display format in SAS goldens** used for string parity: change `format=date9.` to `format=yymmdd10.` on any SQL alias you'll compare.

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
