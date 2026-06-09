# Alteryx semantics — the "why" of a tool's behavior

Open when a migration produces the wrong result and you need to understand what Alteryx actually does. For *which* recipe to use, see overview.md's reference map.

---

## Data types

Alteryx columns are always typed. Types appear in `AlteryxSelect`'s `type` attribute, propagated through the graph.

| Alteryx | Size | Range | DSS |
|---|---|---|---|
| `Byte` | 1 | 0–255 | `bigint` |
| `Int16` | 2 | ±32k | `bigint` |
| `Int32` | 4 | ±2B | `bigint` |
| `Int64` | 8 | ±9e18 | `bigint` |
| `FixedDecimal` | user | user | `double` (precision best-effort) |
| `Float` | 4 | IEEE single | `float`/`double` |
| `Double` | 8 | IEEE double | `double` |
| `String` | user (bytes) | | `string` |
| `V_String` | user (1–8192 bytes) | variable | `string` |
| `WString` | user (chars × 2) | fixed UTF-16 | `string` |
| `V_WString` | user (1–1e9 chars) | variable UTF-16 | `string` |
| `Bool` | 1 | true/false | `boolean` |
| `Date` | 10 (`yyyy-MM-dd`) | | `date` (parse at ingest) |
| `DateTime` | 19 (`yyyy-MM-dd HH:mm:ss`) | | `date` |
| `Time` | 8 (text) | | `string` (DSS has no Time type) |
| `Blob`/`SpatialObj` | variable | | `string` (WKT) or `binary` |

- **Integer collapse:** all Alteryx integer types → `bigint`. `tinyint`/`smallint`/`int` buy nothing and risk overflow. All string widths → `string`.
- **`size` truncates in `Formula`, not in `AlteryxSelect`.** `<FormulaField type="V_String" size="N">` silently truncates the formula's string result to N chars at write time. DSS `add-formula`/`CreateColumnWithGREL` output is unbounded → diverges on rows where the result exceeds N chars, and downstream split/parse tools (TextToColumns split-to-rows, RegEx ParseComplex) then see different inputs. Default: leave unbounded (most downstream logic is robust). Only emulate with `add-formula --expr 'substring(col, 0, N)'` when ground truth was computed against truncated values and matches exactly. `AlteryxSelect`'s `size` is a declared-width hint — it does NOT truncate.
- **FixedDecimal precision:** `FixedDecimal(19.2)` = SQL `NUMERIC(19,2)`, exact decimal, no FP drift. DSS has no decimal type. Use `double` and accept drift, OR on SQL connections keep the column `decimal` in the SQL schema and never materialize it through pandas (`float64` loses precision past 2^53). For cent-level currency exactness, push arithmetic to SQL.

---

## Null semantics

- Alteryx null = `[Null]` / `Null()`. Numeric nulls propagate: `[a] + [Null]` → null.
- String null ≠ empty: `IsNull("")`→false, `IsEmpty("")`→true, `IsNull(Null())`→true.
- `[a] = Null()` is always null (three-valued logic) — use `IsNull([a])`.
- `IF … THEN … ELSE` with a null condition → null result.

DSS parity:
- GREL treats `""` as row-level null on string columns; numeric columns use SQL `NULL`.
- GREL `isnull(x)` true for both `""` and null.
- Prepare arithmetic propagates null (`null + 3 = null`); pushed to SQL → SQL semantics (identical).

---

## Aggregation null-handling — Alteryx-vs-DSS divergence

Alteryx aggregation tools (`Summarize`, `PearsonCorrelation`, sometimes `RunningTotal`) treat nulls **differently** from DSS/SQL, silently.

### 1. `*No0` Summarize actions (`AvgNo0`, `SumNo0`, `MinNo0`, `MaxNo0`, `CountNo0`)

- **Alteryx:** ignore both NULL **and** zero. `AvgNo0` over 9 rows of `0` + `(40,42,43)` → `(40+42+43)/3 = 41.67`, not `10.42`. The `0` is Alteryx's sentinel for "no value for this stat".
- **DSS/SQL:** `avg/sum/min/max/count` ignore NULL but **include 0**. Diverges whenever source uses 0 as a null-sentinel (common in exported `.yxdb`/`.yxmd` TextInput data).
- **Migration:** coerce sentinel-zero to NULL via a `--computed-col` on the same Group recipe before aggregating:
  ```bash
  dku recipe create-group avgs -P PROJ -i input --output-ds avgs -k partition_key \
      --computed-col 'col_no0=if(val("col")==0||isBlank(val("col")), null, val("col")):double' \
      --agg col_no0:avg --no-global-count --rename col_no0_avg:Avg_Col
  ```
  `avg` already ignores NULL → Alteryx-equivalent answer. **GREL equality is `==`, not `=`** (single `=` is assignment; CLI rejects with `Unexpected '='. Did you mean '=='?`).

### 2. `PearsonCorrelation` treats null as zero (NOT pairwise-complete)

- **Alteryx:** substitutes `0` for null cells before computing correlation. Statistically wrong (correct = pairwise-complete, what SQL `CORR()`/pandas/numpy do), but it's what every solution `.yxmd` ground truth was built against — reproduce it.
- **DSS:** SQL `CORR(x,y)` ignores rows where either arg is NULL. To match Alteryx, wrap nullable columns in `COALESCE(col, 0)`:
  ```sql
  SELECT CORR(COALESCE("col_a", 0), COALESCE("col_b", 0)) AS "Result"
  FROM ${projectKey}_input_db
  ```
  Divergence can be large (different magnitude AND decay, not just rounding). Document the COALESCE in any SQL recipe replacing PearsonCorrelation. See `tools-predictive-ml.md` § PearsonCorrelation.

### 3. General principle (always verify aggregation parity)

When a group/agg/correlation result differs from expected by an obvious factor (not rounding), check:
1. Sentinel zeros treated as values? (Alteryx `*No0` vs DSS `avg`/`sum`)
2. NULL rows included? (Alteryx PearsonCorrelation null→0 vs SQL CORR pairwise-complete)
3. `Concat` truncating? (Snowflake LISTAGG cap — see `../../dku-cli/playbooks/tabular-flow.md`)

These ~90% of "values wrong but row count right" mismatches.

---

## Join semantics

The Alteryx `Join` tool has three outputs:

| Output | Rows | Columns |
|---|---|---|
| `Left` (L) | in left only — no right match | left columns |
| `Join` (J) | matched both sides | left + right (right renamed on collision) |
| `Right` (R) | in right only — no left match | right columns |

- Multiple matches → all combinations (cartesian by match), same as SQL INNER/LEFT.
- Null keys: `Null() ≠ Null()` — null-key rows go to Left or Right, never Join.
- String join keys are case-sensitive by default.

DSS Join recipe parity:
- `inner` → Join output only.
- `left` → Left + Join (matched rows have right columns populated).
- `right` → Right + Join.
- `outer` → Left + Join + Right (unmatched have nulls on the other side).
- **To reproduce Alteryx's 3-output fan-out:** outer join → one output → three downstream Filter recipes (one per side).

---

## MultiRowFormula / RunningTotal semantics

Evaluated **after** sort (`GroupByFields` + input row order). The formula references:
- `[Row-N:Col]` — `Col` N rows prior; null if before start.
- `[Row+N:Col]` — N rows forward.
- `[Row-1:<this formula's output>]` — the previously computed value of this formula (enables running totals).

**Boundary init** (`<OtherRows>` XML, `Values for Rows that Don't Exist`) — choice changes results:

| Setting | Resolves missing ref to |
|---|---|
| `NULL` | null |
| `Empty` | type's empty value — for a **numeric** field this is **`0`, not null** → a first-row `[Row-1:numCol]` reads `0` and DOES contribute to a downstream SUM |
| `Closest valid value` | nearest non-boundary value |

Read the `<OtherRows>` tag: an `Empty` on a numeric column means the boundary row participates (first delta measured from `0`, not skipped). DSS Window/lag port: `Empty` numeric → `coalesce(lag(col,1), 0)` (boundary measured from `0`); `NULL` → plain `lag(col,1)`.

DSS Window recipe parity:
- Partition = `GroupByFields`. Order = input row order (bake `row_idx` at extraction if no sort field — no AddId processor, see tools-state-parsing.md § RecordID).
- `lag(col,1)` (SQL) / `col.shift(1)` (pandas) = `[Row-1:col]`.
- Self-referential running total (`[Row-1:RunTotal] + [Sales]`): Window cumulative-sum mode (`agg-mode: cumulative`, `Sales:sum`). Arbitrary self-referential recurrences → Python only:
  ```python
  df["RunTotal"] = df.groupby("Region")["Sales"].cumsum()
  ```

---

## Formula evaluation order

In one `Formula` tool, fields evaluate **top-to-bottom**; a later field can reference an earlier one (`[Total]=[A]+[B]` then `[Pct]=[Part]/[Total]`). DSS Prepare steps run in order — same behavior.

---

## Truthy, comparison, and typing

- Alteryx `IF [x]` numeric: zero false, non-zero true, **null false** (unlike SQL).
- Mixed-type comparison auto-casts: `"5" = 5` → true. GREL is stricter: `"5" == 5` is false. Cast: `toNumber("5") == 5`.
- String comparisons case-sensitive; `Uppercase()`/`Lowercase()` both sides for case-insensitive.

---

## `[_CurrentField_]` (Multi-Field Formula)

Applies one expression to many selected columns; `[_CurrentField_]` = column under iteration.

```
Expression: Replace([_CurrentField_], ",", "")
Fields:     Price, Qty, Discount
```

DSS options: one Prepare step per column (verbose, explicit); a Prepare `FindReplace` step with `columnNames: [Price, Qty, Discount]`; or Python `df[cols].apply(lambda c: c.str.replace(",", ""))`.

---

## Date/time semantics

- Alteryx `Date` = `yyyy-MM-dd` string; `DateTime` = `yyyy-MM-dd HH:mm:ss`.
- Arithmetic: `DateTimeAdd([d], n, "days")`, `DateTimeDiff([a], [b], "days")`. Units: `seconds`, `minutes`, `hours`, `days`, `months`, `years`.
- Month/year arithmetic is calendar-aware: `DateTimeAdd("2024-01-31", 1, "months")` → `"2024-02-29"` (clamped to month end).
- `DateTimeNow()` = local server time; `DateTimeToday()` = `yyyy-MM-dd`.
- `DateTimeParse([s], "format")` uses Java tokens (`yyyy`, `MM`, `dd`, `HH`, `mm`, `ss`).

### DSS date types

Pick the narrowest type that fits:

| DSS type | Example | Use for |
|---|---|---|
| Datetime with tz | `2025-12-31T23:05:43.123Z` | ISO-8601 sources, explicit offset/Z |
| Datetime no tz | `2025-12-31 23:05:43` | Wall-clock times, no-tz source systems |
| Date only | `2025-12-31` | Calendar days, Excel export targets |

Alteryx `Date` → DSS **Date only**. Alteryx `DateTime` → DSS **Datetime no tz** (unless source carries Z/offset). Use Parse date / Format date with "Output type" set; if overwriting in place, also change the column's DSS type manually.

### DSS Prepare parity

- `DateParser` uses the same Java tokens as Alteryx.
- `computeDate(date, n, "day")` / `diffDate(a, b, "day")` for arithmetic.
- Calendar clamping matches (end-of-month rule).

---

## Parsing notes for `.yxmd` XML

- UTF-8 (unlike SAS `.egp` project.xml UTF-16).
- Whitespace in attributes/text is significant (`<Expression>IF [x]>0 THEN 1 ELSE 0 ENDIF</Expression>`).
- `<Annotation>` = user notes — ignore for migration, useful for inventory.
- `<Properties><MetaInfo>` has description + cached field schema, but the schema can be **stale** (Alteryx doesn't always propagate upstream changes) — use the downstream `AlteryxSelect` as type truth.
- Connections encode data flow — walk them to build the DAG; don't rely on Node order.

---

## Sampling and deterministic row order

- Alteryx guarantees row order through a pipeline (FIFO per tool). Sort/Join/Unique preserve left/first-input order where possible.
- DSS visual recipes on a SQL engine may NOT preserve order (SQL is set-theoretic). If a downstream tool depends on row order (e.g. MultiRowFormula), add an explicit Sort recipe before the order-sensitive step.

---

## Common value-mismatch causes

When migrated output disagrees with Alteryx ground truth, check in this order:

1. **Type coercion at ingest** — DSS stored a numeric as STRING; comparisons silently fail. Fix: `set-schema` with correct types.
2. **Null on a join key** — Alteryx excluded those rows from Join; DSS did too, but downstream queries assuming those rows exist get different counts. Fix: inspect Left/Right output of Join.
3. **Implicit numeric → string cast** — Alteryx `[id] + "_label"` auto-casts; GREL doesn't. Use `concat("", id, "_label")`.
4. **Decimal precision** — Alteryx FixedDecimal vs DSS double. Fix: push arithmetic to SQL, or cast upstream.
5. **Formula evaluation order** — Alteryx Formula tool: later fields see earlier output. DSS Prepare: steps run in order — verify step order if a reference is null.
6. **DateParser produced all nulls** — missing `outCol` param, or format mismatch. Re-check format tokens (Java, not C strftime).
7. **Group added a `count` column you didn't ask for** — pass `--no-global-count`.
8. **Stack produced nulls / dropped columns** — column names disagree, or stack set to `INTERSECT`/`FROM_DATASET`. Use `dku recipe create-stack --mode UNION` to keep the union; add a ColumnRenamer upstream when differently named columns are semantically the same.
9. **Rounding** — Alteryx `Round(1.5)` is half-away-from-zero; GREL `round(1.5)` is half-up; pandas/Python default is banker's. See `../sas/functions-formats.md`.
