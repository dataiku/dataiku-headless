# SAS Semantics

How SAS actually works — what a program computes is often different from what the code appears to say. Read the relevant section before migrating any DATA step, MERGE, RETAIN pattern, or macro.

- [Data types](#data-types) / [Missing value semantics](#missing-value-semantics) / [Character comparison](#character-comparison) / [Numeric precision](#numeric-precision)
- [DATA step execution model (PDV)](#data-step-execution-model-pdv)
- [MERGE semantics](#merge-semantics) — incl. many-to-many, common-variable overwrite, FIRST./LAST., visual-join caveat
- [LAG function trap](#lag-function-trap) / [PROC UNIVARIATE defaults](#proc-univariate-defaults)
- [PROC SQL SAS-specific extensions](#proc-sql-sas-specific-extensions) / [`<>` operator trap](#the--operator-context-trap) / [WHERE-only operators](#where-only-operators) / [PROC SORT deduplication](#proc-sort-deduplication)
- [Macro patterns](#macro-patterns)

## Data types

SAS has exactly **two** types: **CHARACTER** (fixed-length, right-padded with blanks) and **NUMERIC** (8-byte IEEE 754 double). Dates, times, booleans — all stored as numerics with display formats applied.

- Dates = integer days since 01JAN1960
- Times = seconds since midnight
- Datetimes = seconds since midnight 01JAN1960
- Literals: `'15MAR2024'd`, `'10:30:00't`, `'15MAR2024:10:30:00'dt`

Display formats (`DATE9.`, `MMDDYY10.`, `YYMMDD10.`) only change rendering, not the stored value. Two date variables with different formats compare equal if their integers match.

### Character length is set by first assignment

Character length is locked by the first assignment or `LENGTH` statement. `a='Tom';` then later `a='Christopher';` → truncated to `'Chr'` (length 3). A `LENGTH` statement must appear **before** the first use to override. Check for LENGTH statements before SET/MERGE when migrating.

## Missing value semantics

| SAS behavior | Result | Migration impact |
|---|---|---|
| `. < 0` | **TRUE** | Missing is negative infinity for numeric comparisons. `WHERE amount > 0` excludes missing. In Dataiku, NULL compares to NULL (falsy) — same result for filters, different for sorts. |
| `. + 5` | `.` | Missing propagates in arithmetic. Use `COALESCE` or impute. |
| `missing(0)` | 0 (false) | Zero is NOT missing. |
| `missing(" ")` | 1 (true) | Blank string IS missing in SAS. Dataiku treats empty string ≠ null. |
| `coalesce(., 0, 5)` | 0 | First non-missing. Same as SQL/GREL. |
| `if cost then ...` | FALSE when cost is 0 OR missing | Python `float('nan')` is truthy (opposite). Add explicit `IS NOT NULL AND col != 0` checks. |
| Division by zero | missing (`.`), NOTE, `_ERROR_` = 1, continues | Python raises `ZeroDivisionError`; pandas produces `inf`. Use `NULLIF(denom, 0)` in SQL. |

### Special missing values (.A–.Z)

SAS supports 28 distinct missing types with sort order `._ < .A < .B < ... < .Z < . < negatives < 0 < positives`. The `MISSING A R;` statement declares characters to read as `.A` / `.R`. If the program uses these to encode categories of missingness (absent, refused, …), create a separate categorical column in Dataiku — standard NULL has no subtypes.

### `OPTIONS MISSING='0'`

Changes missing display to "0". Downstream logic may treat missing as zero. Check for this option and add `fillna(0)` if needed.

## Character comparison

| SAS behavior | Result | Note |
|---|---|---|
| `"ABC" = "ABC   "` (trailing blanks) | Equal | SAS ignores trailing blanks. Dataiku is exact — use `trim()` if needed. |
| `"abc" = "ABC"` | Not equal | Case-sensitive (same as Dataiku). |
| `"ABC" =: "AB"` (prefix) | TRUE | No GREL equivalent. Use `startsWith()`. |

## Numeric precision

- `0.1 + 0.2 = 0.3` is FALSE in both SAS and Dataiku. If SAS code compares floats without `round()`, results may already be wrong.
- SAS `round()` is half-away-from-zero for any sign; GREL `round()` is 1-arg, Java half-up — matches SAS for positives only. Full per-engine parity table + any-sign workaround: `functions-formats.md` § Rounding parity.

## DATA step execution model (PDV)

The PDV (Program Data Vector) is SAS's row-processing buffer. At the top of each iteration:

- Variables from **INPUT or assignment** → reset to missing
- Variables from **SET, MERGE, UPDATE** → **retained**
- Variables with **RETAIN** or **SUM statement** → retained
- `_N_` and `_ERROR_` → retained, never written to output

**Why this matters:** `if cond then x = value;` will carry forward the previous row's `x` when the condition is false **if** `x` comes from a SET. If `x` is computed, it resets to missing. This distinction is invisible in the code but changes results. When migrating conditional assignments, check whether the variable is from SET (retained) or computed (reset) — retained variables need `LAG()` or forward-fill.

### Implicit OUTPUT

- **No explicit OUTPUT** → one observation written per iteration automatically.
- **Any explicit OUTPUT** → implicit output is suppressed entirely; only explicit OUTPUT calls produce rows.
- `DELETE` = skip current row, continue
- `STOP` = end DATA step, write pending output
- `RETURN` = skip to next iteration

When explicit OUTPUT appears inside an IF block, rows NOT satisfying the condition are silently dropped — equivalent to a filter, not just a write.

## MERGE semantics

| Pattern | Behavior | Dataiku |
|---|---|---|
| `merge A(in=a) B(in=b); by k; if a;` | Left join | Join recipe (LEFT) |
| `merge A(in=a) B(in=b); by k; if a and b;` | Inner join | Join (INNER) |
| `merge A B; by k;` (no filter) | Full outer join | Join (full outer) |
| `merge master(in=a) appl:; by k;` | Prefix wildcard — merges ALL datasets starting with "appl" | Multiple Join recipes |
| `update master transaction; by k;` | Only non-missing values from transaction overwrite master | Prepare: per-column null-check + conditional formula |
| `merge A B;` (no BY) | Positional — pairs by row number | No SQL equivalent. Output = LARGEST dataset |
| `set A; set B;` (multi-SET, no BY) | Positional — pairs by row number | Output = SMALLEST dataset |

### Many-to-many MERGE is NOT a Cartesian product

When both datasets have duplicate BY values, SAS walks them in parallel within each group (1st pairs with 1st, 2nd with 2nd, …) and carries the shorter side's last value forward. Output rows per group = `max(count_A, count_B)`, not `count_A × count_B`. SAS emits `WARNING: MERGE statement has more than one data set with repeats of BY values.`

A standard SQL `JOIN` on duplicate keys produces a Cartesian product — different result. For many-to-many MERGE, deduplicate first or pair by row number within groups.

### Common variable overwrite

When both datasets in MERGE have a non-BY variable with the same name, the **last-listed** dataset wins silently. SAS programmers use `DROP=` / `RENAME=` to work around this. In SQL/Pandas joins, duplicate column names get `_x`/`_y` suffixes. A `DROP=` on a common variable before MERGE is working around this overwrite.

### FIRST./LAST. cascade

With `BY x y z`:
- When `x` changes → `FIRST.x=1`, `FIRST.y=1`, `FIRST.z=1` (all reset)
- When only `z` changes → `FIRST.z=1`, but `FIRST.x=0`, `FIRST.y=0`

SQL `PARTITION BY z` alone won't replicate the cascade. Partition by the full BY list and track boundaries hierarchically.

### Visual-join caveat: `AUTO_NON_CONFLICTING` is first-wins

Dataiku's visual Join recipe default (`outputColumnsSelectionMode: AUTO_NON_CONFLICTING`) keeps the column from the **lowest-index** `virtualInputs` entry when two inputs share a column name — the opposite of SAS `merge a b;` which gives `b` the win. Fix: rename upstream, or insert a thin Prepare that drops the conflicting column from the driver side. This bites the merge+compute+bin pattern — `procs.md` § Merge + compute + bin.

## LAG function trap

```sas
/* WRONG — LAG inside IF skips the queue for filtered rows */
if not first.group then prev = lag(value);

/* RIGHT — call LAG unconditionally, then filter */
prev = lag(value);
if not first.group then diff = value - prev;
```

`LAG()` in SAS is a **queue** — every call pushes a value. Wrapped in `IF`, calls are skipped for false rows and the queue falls out of sync. SQL `LAG() OVER()` is declarative and doesn't have this trap — but document the intended behavior before migrating.

## PROC UNIVARIATE defaults

Defaults differ silently from Python/pandas.

| Setting | SAS | Python equivalent |
|---|---|---|
| Variance / std denominator | `n-1` (sample std) | `numpy.std(x, ddof=1)` or `pd.Series(x).std()`. **Not** `numpy.std(x)` which is ddof=0 (population). |
| Quantile method | `QNTLDEF=5` ("empirical distribution function with averaging") | `numpy.percentile(x, p, method="averaged_inverted_cdf")` or R `quantile(type=2)`. **Not** pandas `interpolation="linear"` (type 7). |
| Missing handling | Excluded from all stats | pandas excludes NaN by default — matches |
| Mode | Returns smallest mode if multiple | `scipy.stats.mode` returns smallest — matches |

When migrating `PROC UNIVARIATE mean= median= std= q1= q3= ...` to Python, specify the quantile method explicitly — the default `linear` / type 7 differs from SAS by a fraction of a step on non-integer positions.

```python
import numpy as np
q1     = np.percentile(x, 25, method="averaged_inverted_cdf")
median = np.percentile(x, 50, method="averaged_inverted_cdf")
q3     = np.percentile(x, 75, method="averaged_inverted_cdf")
std    = np.std(x, ddof=1)
```

`QNTLDEF` mapping: 1→`interpolated_inverted_cdf`, 2→`averaged_inverted_cdf`, 3→`closest_observation`, 4→`hazen`, **5 (default)**→`averaged_inverted_cdf`. Pre-v9 SAS defaulted to 4; modern is 5. Both map to `averaged_inverted_cdf` for integer-valued data — the difference only shows up on fractional positions.

## PROC SQL SAS-specific extensions

| Feature | Behavior | Standard SQL? |
|---|---|---|
| `calculated col_alias` | Reference a computed column in the same SELECT | No — use subquery or repeat expression |
| `GROUP BY` with detail columns | SAS "remerges" group totals back to each row | No — `SUM() OVER()` in SQL; in visual recipes this is Group(no key) + CROSS Join, NOT Window — `procs.md` § PROC SQL auto-remerge |
| `SELECT DISTINCT INTO :macro_var SEPARATED BY` | Populates macro variable from query | No equivalent — use project variables |
| `HAVING col = max(col)` without GROUP BY | Filters to max-value rows | Differs in standard SQL — use `QUALIFY` or subquery |
| `NULLIF()` | Does NOT exist in SAS PROC SQL | Standard has it; SAS uses `CASE WHEN` |

## The `<>` operator context trap

- **DATA step expressions**: `<>` = MAX (`a <> b` returns the larger value). Similarly `><` = MIN.
- **WHERE expressions**: `<>` = NOT EQUAL TO
- **PROC SQL**: `<>` = NOT EQUAL TO

In DATA step code, `<>` means MAX, not inequality. Use `GREATEST(a, b)` in SQL, `max(a, b)` in Python.

## WHERE-only operators

| Operator | Meaning | Equivalent |
|---|---|---|
| `CONTAINS 'abc'` / `? 'abc'` | Case-sensitive substring | `LIKE '%abc%'` |
| `LIKE 'N%'` | Pattern match | Same in SQL |
| `=*` (sounds-like) | SOUNDEX comparison | `SOUNDEX(col) = SOUNDEX('value')` |
| `IS MISSING` / `IS NULL` | Tests for missing | `IS NULL` |
| `BETWEEN x AND y` | Inclusive range | Same |
| `=:` (prefix) | Truncate to shorter length | `LIKE 'prefix%'` or `startsWith()` |

`CONTAINS`, `=*`, `=:`, `SAME-AND` are NOT available in subsetting `IF` — only in `WHERE`.

## PROC SORT deduplication

`NODUPKEY` dedups on the BY keys, keeping the first row per combo; `NODUP` removes exact whole-row duplicates; no option = sort only. Recipe mapping: `procs.md` § PROC → recipe.

---

## Macro patterns

Migrate what the macros **generate**, not the macros themselves.

### How to read macro code for migration

1. A `%macro counts(liver, uln)` called as `%counts(ALT, x3)` generates a specific block of DATA/PROC steps. Migrate the generated block, not the macro definition.
2. Resolve `%DO` loops mentally: `%do i = 1 %to &num` with `&num=3` generates 3 copies of the body with `&i` = 1, 2, 3.
3. Resolve `&&var&i` in two passes: first `&&` → `&` giving `&var1`, then `&var1` → its value.

### Macro pattern → Dataiku

| SAS macro pattern | Generates | Dataiku |
|---|---|---|
| `%macro process(ds); ... %mend; %process(sales);` | One DATA/PROC step for "sales" | One recipe (no parameterization) |
| `%do i = 1 %to &num; ... %end;` | N copies of the body | N recipes, or one recipe processing all groups |
| `CALL SYMPUT("arm&i", value)` | Creates macro vars at runtime | Project variables or Python loop |
| `CALL SYMPUTX("var", value, 'g')` | Global macro var | Project variable |
| `SELECT DISTINCT INTO :list SEPARATED BY " "` | Space-separated list for `%SCAN` iteration | Python list or project variable |
| `%SCAN(&list, &i)` / `%COUNTW(&list)` | Iterate over space-separated values | Python `for item in list.split()` |
| `%IF &num_obs = 0 %then %do; ... %end;` | Conditional step generation | Python `if df.empty:` |
| `data work.&lab.arm&i;` | Dynamic dataset name (ALTarm1, ALTarm2) | Keep data in one dataset with group columns — don't replicate N datasets |
| `CALL EXECUTE("data " \|\| name \|\| "; ...")` | DATA steps generated from data values | Python recipe with dynamic logic |
| `%EVAL(&HEADER_CT + &h_ct)` | Macro arithmetic (integers only) | Python arithmetic |

### Scoping trap

`CALL SYMPUT` creates macro variables in the **enclosing macro's local scope**, not globally. Use `CALL SYMPUTX("x", "1", 'g')` for global. When analyzing SAS code, check whether CALL SYMPUT values are used outside the macro that created them — if so, the code either uses `%GLOBAL` declarations or the `'g'` flag, or has a latent bug. `SELECT INTO :var` in PROC SQL is also local by default.

### Function-style macros (SASjs/core etc.)

Utility macro libraries define macros that return values via `%SYSFUNC` — no datasets, no side effects.

| Pattern | Does | Dataiku equivalent |
|---|---|---|
| `%mf_getattrn(ds, NLOBS)` | Obs count via `%SYSFUNC(open/attrn/close)` | `dku dataset info DS -P PROJ --recompute` |
| `%mf_getvarlist(ds)` | Space-separated variable list | `dku dataset schema DS -P PROJ` |
| `%mf_existvar(ds, var)` | Variable position (0 if not found) | Schema lookup |
| `%mf_getvartype(ds, var)` | C or N | Schema column type |
| `%mf_isblank(param)` | Blank test via `%SYSEVALF(%SUPERQ(...)=, boolean)` | Python `if not var:` |
| `%mf_getquotedstr(list)` | Builds `'a','b','c'` from `a b c` | Python `"','".join(items)` |

These are metadata helpers — don't port the macro itself; replace the call site with the CLI/Python equivalent.

### `%DO` loop → Dataiku flow mapping

A `%DO` loop generating N datasets typically maps to one of:

1. **N separate recipes** — if each group needs different processing.
2. **One recipe with GROUP BY** — if the work is aggregation.
3. **One Python recipe** — if the loop generates complex, state-dependent datasets.
4. **Scenario with loop step** — if the loop runs the same pipeline for different parameters.

If the `%DO` body is only filter + aggregate + rename, use visual recipes. If it contains RETAIN, running totals, or cross-group references, use a Python or SQL recipe.

### Dynamic dataset naming

SAS code like `data work.ALTarm&i work.ASTarm&i ...; set work.labdata; if arm = "&&arm&i" then ...` creates `ALTarm1/2/3`, `ASTarm1/2/3`, etc. Real programs can generate 90+ datasets this way. **Don't replicate N×M datasets** — keep the data in one dataset with group columns (`arm`, `lab_test`) and use Group/Pivot recipes to produce the summary tables.

### Code-generating-code

`filename temp; data _null_; file fref; put ...; %inc fref;` is SAS's metaprogramming pattern. In Dataiku, the equivalent is a Python recipe that dynamically builds and executes operations, or a Prepare recipe with computed steps.
