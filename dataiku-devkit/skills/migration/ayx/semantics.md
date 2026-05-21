# Alteryx semantics — the "why" of a tool's behavior

Open this when a migration produces the wrong result and you need to understand what Alteryx is actually doing. The translation table in `translation.md` tells you *which* Dataiku recipe to use; this file tells you *why* Alteryx emits the value it does.

---

## Data types

Alteryx columns are always typed. Types appear in `AlteryxSelect`'s `type` attribute and are propagated through the graph.

| Alteryx | Size | Range | DSS |
|---|---|---|---|
| `Byte` | 1 | 0–255 | `bigint` |
| `Int16` | 2 | ±32k | `bigint` |
| `Int32` | 4 | ±2B | `bigint` |
| `Int64` | 8 | ±9e18 | `bigint` |
| `FixedDecimal` | user | user | `double` (precision is best-effort in DSS) |
| `Float` | 4 | IEEE single | `float` or `double` |
| `Double` | 8 | IEEE double | `double` |
| `String` | user (bytes) | | `string` |
| `V_String` | user (1–8192 bytes) | variable | `string` |
| `WString` | user (chars × 2) | fixed UTF-16 | `string` |
| `V_WString` | user (1–1e9 chars) | variable UTF-16 | `string` |
| `Bool` | 1 | true/false | `boolean` |
| `Date` | 10 (text `yyyy-MM-dd`) | | `date` (parse at ingest) |
| `DateTime` | 19 (text `yyyy-MM-dd HH:mm:ss`) | | `date` |
| `Time` | 8 (text) | | `string` (DSS has no Time type) |
| `Blob` / `SpatialObj` | variable | | `string` (WKT) or `binary` |

**DSS mapping rule:** all Alteryx integer types collapse to `bigint` — DSS doesn't distinguish Int16 vs Int32 vs Int64, and using `tinyint`/`smallint`/`int` buys nothing and risks overflow. All string widths collapse to `string`.

**`size` is metadata in `AlteryxSelect` but a HARD TRUNCATION in `Formula` output.** The `size` attribute on a `<FormulaField type="V_String" size="N">` truncates the formula's string result to N characters at write time — silently. DSS Prepare's `add-formula` / `CreateColumnWithGREL` has no equivalent: GREL output is unbounded. A 1:1 migration of a `Formula(size="488")` step that builds a long string (concatenations, regex replacements that expand the string, etc.) will **diverge from Alteryx on rows where the result exceeds N chars** — and downstream tools (TextToColumns split-to-rows, RegEx ParseComplex) will see different inputs in DSS than they did in Alteryx. Two faithful-migration choices: (1) leave it unbounded if the downstream logic is robust to the longer string (most recipes are), or (2) emulate the truncation with `add-formula --expr 'substring(col, 0, 488)'` immediately after the equivalent step. Pick (1) by default; pick (2) only when the ground-truth output was computed against truncated values *and* matches it exactly. `AlteryxSelect`'s `size` is by contrast a declared-width hint — it doesn't truncate.

**FixedDecimal precision:** Alteryx `FixedDecimal(19.2)` behaves like SQL `NUMERIC(19,2)` — exact decimal, no floating-point drift. DSS has no decimal type; use `double` and accept small drift, or — on SQL connections — keep the column as `decimal` in the SQL schema and never let DSS materialize it through pandas (pandas `float64` loses precision past 2^53 digits). For accounting / currency where cent-level exactness matters, push the arithmetic to SQL.

---

## Null semantics

- Alteryx null (`[Null]` in the UI, `Null()` in formulas) displays as `[Null]`.
- Numeric nulls participate in arithmetic by producing null: `[a] + [Null]` → null.
- String nulls are distinct from empty string: `IsNull("")` → false, `IsEmpty("")` → true, `IsNull(Null())` → true.
- Alteryx `=` on nulls: `[a] = Null()` is always null (three-valued logic) — use `IsNull([a])`.
- In an `IF … THEN … ELSE …` where the condition is null, the result is null.

DSS parity:
- GREL treats empty string `""` as the row-level null on string columns. On numeric columns, DSS uses SQL-style `NULL`.
- GREL `isnull(x)` returns true for both empty string and null.
- For arithmetic in a Prepare step, DSS propagates null the same way: `null + 3 = null`. But if the step is pushed to SQL, SQL semantics apply (identical).

---

## Aggregation null-handling — Alteryx-vs-DSS divergence

Alteryx aggregation tools (`Summarize`, `PearsonCorrelation`, sometimes `RunningTotal`) treat nulls **differently** from DSS / standard SQL — and the divergence is silent. Two distinct families of behavior to watch for:

### 1. `*No0` Summarize actions (`AvgNo0`, `SumNo0`, `MinNo0`, `MaxNo0`, `CountNo0`)

- **What Alteryx does:** these variants ignore both NULL **and** zero values when aggregating. So `AvgNo0([Pitcher Rank])` over a fantasy team that has 9 hitters with `Pitcher Rank = 0` and 3 pitchers with values `(40, 42, 43)` returns `(40+42+43)/3 = 41.67`, not `(0×9 + 40+42+43)/12 = 10.42`. The "0" is treated as "not a pitcher" (Alteryx's lossy-numeric-encoding convention for "this player doesn't have a value for this stat").
- **DSS / SQL parity:** standard `avg`, `sum`, `min`, `max`, `count` ignore NULL but include 0. The divergence appears whenever the source data uses 0 as a sentinel-for-null (common in Alteryx-exported `.yxdb` and `.yxmd` `TextInput` data).
- **Migration recipe:** lift the zero-exclusion to a `--computed-col` on the same Group recipe before the aggregate runs:
  ```bash
  dku recipe create-group avgs -P PROJ -i input --output-ds avgs -k partition_key \
      --computed-col 'col_no0=if(val("col")==0||isBlank(val("col")), null, val("col")):double' \
      --agg col_no0:avg --no-global-count --rename col_no0_avg:Avg_Col
  ```
- The `if(val=="0" || isBlank, null, val)` pattern coerces the sentinel-zero to NULL, then `avg` (which already ignores NULL) gives the Alteryx-equivalent answer. **Critical: GREL uses `==` for equality, not `=`** (single `=` is assignment; the CLI rejects this with `Unexpected '='. Did you mean '=='?`).

### 2. `PearsonCorrelation` treats null as zero (NOT pairwise complete)

- **What Alteryx does:** `PearsonCorrelation` substitutes `0` for null cells before computing correlation. This is **statistically wrong** (the correct convention is pairwise-complete-cases or row-wise deletion, used by SQL `CORR()`, pandas `df.corr()`, and numpy). But Alteryx's behavior is what every solution `.yxmd` ground truth was built against, so migrations must reproduce it.
- **DSS parity:** SQL `CORR(x, y)` ignores rows where either argument is NULL (pairwise complete). To match Alteryx, wrap nullable columns in `COALESCE(col, 0)`:
  ```sql
  SELECT CORR(COALESCE("col_a", 0), COALESCE("col_b", 0)) AS "Result"
  FROM ${projectKey}_input_db
  ```
- The divergence is large enough to be obvious — Challenge_030 (253 rows, 104 nulls in one column): pairwise-complete returned `-0.0337`, Alteryx-equivalent (`COALESCE(.,0)`) returned `-0.0181`. Different magnitude AND different decay pattern, not a rounding difference. Tested-and-fixed pattern; document the COALESCE in any SQL recipe replacing a PearsonCorrelation tool. See `ayx/translation.md` § PearsonCorrelation.

### 3. The general principle (always verify aggregation parity)

Whenever a migration's group/aggregation/correlation result differs from the expected `.yxmd` value by an obvious factor (not a rounding error), check first:
1. Are sentinel zeros being treated as values? (Alteryx `*No0` action vs DSS `avg`/`sum`)
2. Are NULL rows being included in the aggregation? (Alteryx PearsonCorrelation null→0 vs SQL CORR pairwise-complete)
3. Is `Concat` truncating? (Snowflake LISTAGG cap, see `dku-cli/references/sql-engines.md`)

These three account for ~90% of "the values are wrong but the row count is right" mismatches in Alteryx → DSS migrations.

---

## Join semantics

The Alteryx `Join` tool has three outputs:

| Output | Rows | Columns |
|---|---|---|
| `Left` (L) | in left only — no match on right | left columns |
| `Join` (J) | matched on both sides | left + right (right-side columns get renamed on collision) |
| `Right` (R) | in right only — no match on left | right columns |

- Multiple rows match → all combinations (cartesian by match). Same as SQL INNER/LEFT.
- Null keys: `Null()` never equals `Null()` — rows with null join keys go to Left or Right, never to Join.
- Case-sensitivity: string join keys are case-sensitive by default.

DSS Join recipe parity:
- `type: inner` → Join output only.
- `type: left` → Left + Join (as one output, matched rows have right-side columns populated).
- `type: right` → Right + Join.
- `type: outer` → Left + Join + Right (matched rows have both, unmatched have nulls on the other side).
- To precisely reproduce Alteryx's 3-output fan-out: use **outer join** → one output dataset → three downstream Filter recipes (one per side).

---

## MultiRowFormula / RunningTotal semantics

Evaluated **after** sort (Alteryx's `GroupByFields` + input row order). The formula can reference:
- `[Row-N:Col]` — value of `Col` in the Nth prior row; null if before the start.
- `[Row+N:Col]` — Nth forward row.
- `[Row-1:<current formula output>]` — refers to the **previously computed value of this formula**, enabling running totals.

Initialization: if the input row has no `[Row-N:…]` (at boundary), Alteryx returns null. The `Values for Rows that Don't Exist` tool option controls this (default null).

DSS Window recipe parity:
- Partition = `GroupByFields`.
- Order = input row order (add `AddId` upstream if no sort field exists).
- `lag(col, 1)` in SQL or `col.shift(1)` in pandas = `[Row-1:col]`.
- For a running total that references its own prior output (`[Row-1:RunTotal] + [Sales]`), use Window's cumulative-sum mode (`agg-mode: cumulative`, `Sales:sum`). For arbitrary self-referential recurrences, only Python works:
  ```python
  df["RunTotal"] = df.groupby("Region")["Sales"].cumsum()
  ```

---

## Formula evaluation order

In a single `Formula` tool, fields are evaluated **top-to-bottom**, and a later formula can reference an earlier formula's output. So `[Total] = [A] + [B]` followed by `[Pct] = [Part] / [Total]` works.

DSS Prepare parity: the steps run in order. A `CreateColumnWithGREL` step that references a column created by the previous step works the same way.

---

## Truthy, comparison, and typing

- Alteryx `IF [x] THEN …` where `[x]` is numeric: zero is false, non-zero is true. Null is false (unlike SQL).
- Comparisons between mixed types auto-cast: `"5" = 5` → true. GREL is stricter: `"5" == 5` is false. Cast explicitly: `toNumber("5") == 5`.
- String comparisons are case-sensitive. Use `Uppercase()` / `Lowercase()` on both sides for case-insensitive comparison.

---

## `[_CurrentField_]` (Multi-Field Formula)

`Multi-Field Formula` applies one expression to many selected columns. `[_CurrentField_]` is a placeholder for the column under iteration.

```
Expression: Replace([_CurrentField_], ",", "")
Fields:     Price, Qty, Discount
```

Produces three identically-structured Formula transforms. In DSS, either:
- Add one Prepare step per column (verbose but explicit), or
- Use a Prepare `FindReplace` step with `columnNames: [Price, Qty, Discount]`, or
- Python: `df[cols].apply(lambda c: c.str.replace(",", ""))`.

---

## Date/time semantics

- Alteryx `Date` is `yyyy-MM-dd` string internally; `DateTime` is `yyyy-MM-dd HH:mm:ss`.
- Arithmetic: `DateTimeAdd([d], n, "days")`, `DateTimeDiff([a], [b], "days")`. Units: `seconds`, `minutes`, `hours`, `days`, `months`, `years`.
- Month/year arithmetic is calendar-aware: `DateTimeAdd("2024-01-31", 1, "months")` → `"2024-02-29"` (clamped to month end).
- `DateTimeNow()` returns local server time; `DateTimeToday()` returns `yyyy-MM-dd`.
- Parsing: `DateTimeParse([s], "format")` uses Java-style tokens (`yyyy`, `MM`, `dd`, `HH`, `mm`, `ss`).

### DSS date types

Recent DSS distinguishes three date types; older DSS exposed only ISO-8601 with tz. Pick the narrowest type that fits:

| DSS type | Example | Use for |
|---|---|---|
| Datetime with tz | `2025-12-31T23:05:43.123Z` | ISO-8601 sources, any data with explicit offset/Z |
| Datetime no tz | `2025-12-31 23:05:43` | Wall-clock times, source systems with no tz |
| Date only | `2025-12-31` | Calendar days, Excel export targets |

Alteryx `Date` → DSS **Date only**. Alteryx `DateTime` → DSS **Datetime no tz** (unless the source explicitly carries Z/offset). Use Parse date or Format date processor with "Output type" set to convert. If overwriting the column in place, also change the column's DSS type manually.

### DSS Prepare parity

- `DateParser` uses the same Java tokens as Alteryx.
- `computeDate(date, n, "day")` / `diffDate(a, b, "day")` for arithmetic.
- Calendar clamping behavior matches (end-of-month rule).

---

## Parsing notes for `.yxmd` XML

- UTF-8 encoding (unlike SAS `.egp` project.xml which is UTF-16).
- Whitespace in XML attributes and text is significant where you'd expect (e.g. `<Expression>IF [x]>0 THEN 1 ELSE 0 ENDIF</Expression>`).
- `<Annotation>` blocks contain user notes — ignore for migration but useful context when inventorying.
- `<Properties><MetaInfo>` has the tool's description and cached field schema. The field schema can be stale (Alteryx doesn't always propagate schema changes upstream), so don't rely on it for types — use the downstream `AlteryxSelect` as truth.
- Connections encode data flow. Walk them to build the DAG; don't rely on Node order in the file.

---

## Sampling and deterministic row order

- Alteryx guarantees row order through a pipeline (first-in, first-out per tool). Sort, Join, and Unique preserve order of the left/first input where possible.
- DSS visual recipes on a SQL engine may NOT preserve order (SQL is set-theoretic). If a downstream tool depends on row order (e.g. MultiRowFormula), always add an explicit Sort recipe before the order-sensitive step.

---

## Common value-mismatch causes

When the migrated output disagrees with the Alteryx ground truth, check in this order:

1. **Type coercion at ingest** — DSS stored a numeric as STRING; comparisons silently fail. Fix: `set-schema` with correct types.
2. **Null on a join key** — Alteryx excluded those rows from Join; DSS did the same, but if your downstream query assumes those rows exist, counts differ. Fix: inspect the Left/Right output of Join.
3. **Implicit numeric → string cast** — Alteryx `[id] + "_label"` auto-casts; GREL doesn't. Use `concat("", id, "_label")`.
4. **Decimal precision** — Alteryx FixedDecimal vs DSS double. Fix: push the arithmetic to SQL, or cast upstream.
5. **Formula evaluation order** — in Alteryx Formula tool, later fields see earlier fields' output. In DSS Prepare, steps run in order — verify your step order if a reference appears null.
6. **DateParser produced all nulls** — the `outCol` param was missing, or the format doesn't match. Re-check format tokens (Java, not C strftime).
7. **Group recipe added a `count` column you didn't ask for** — pass `--no-global-count`.
8. **Stack recipe produced nulls or dropped columns** — column names disagree, or the stack was set to `INTERSECT` / `FROM_DATASET`. Use `dku recipe create-stack --mode UNION` to keep the union of columns, and add a ColumnRenamer upstream when differently named columns are semantically the same.
9. **Rounding** — Alteryx `Round(1.5)` is half-away-from-zero; GREL `round(1.5)` is half-up; pandas/Python default is banker's. See `../sas/translation.md` § Rounding parity.
