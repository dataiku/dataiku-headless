# Alteryx State and Parsing Tools to Dataiku

Translation details for row-state, parsing, dynamic rename, dates, generated rows, and JSON parsing.

## MultiRowFormula

**Alteryx:** per-row formula with access to prior/next rows (`[Row-1:Col]`, `[Row+1:Col]`) inside a `GroupByFields` partition, ordered by input row order.

```xml
<Configuration>
  <UpdateField value="False"/>
  <CreateField_Name>RunTotal</CreateField_Name>
  <CreateField_Type>Double</CreateField_Type>
  <OtherRows>Nearest</OtherRows>           <!-- ← boundary semantics; matters! -->
  <GroupByFields><Field field="Region"/></GroupByFields>
  <Expression>[Row-1:RunTotal] + [Sales]</Expression>
  <NumRows value="1"/>
</Configuration>
```

**`<OtherRows>` (boundary semantics) — read this BEFORE picking a translation.** Alteryx's `OtherRows` controls what `[Row-N:Col]` returns when offset N runs off the start (or end) of the partition. Three values, three translations:

| `<OtherRows>` | Alteryx behavior at boundary | DSS visual translation |
|---|---|---|
| `NULL` (default) | Off-partition refs return null | DSS Window's natural `Lag(col, k)` returns null at boundary too — semantics match. Just use Window directly. |
| `Empty` | Off-partition refs return empty string ("") | Same as NULL for numeric columns. Same Window translation. |
| `Nearest` | Off-partition refs return the **first/last value of the partition** (the "edge" value) | DSS Window's `Lag(col, k)` returns null at boundary — does NOT match. **Add a `FirstValue(col)` aggregation over the partition AND a Prepare formula `if(isBlank(lag_k), first_v, lag_k)` for each offset before computing the average/sum.** Example below. |

**Why `Nearest` is the trap:** Alteryx defaults to `NULL`, but `Nearest` is common in moving-average workflows because it makes the leading-edge averages well-defined (instead of producing nulls for the first N-1 rows). DSS Window's natural partial-window behavior at the boundary computes the average over the AVAILABLE rows (`avg(V[1])` for row 1, `avg(V[1], V[2])` for row 2, …), which is yet a third semantic. So a 3-row moving average at row 2 with input `(218, 200, …)`:

| Alteryx `Nearest` | DSS partial-window Window | DSS Window + lag-coalesce |
|---|---|---|
| `(218 + 218 + 200)/3 = 212` | `(218 + 200)/2 = 209` | `(218 + 218 + 200)/3 = 212` ✓ |

If you use a vanilla `create-window --compute 'avg:Value:r3mo' --window-frame -2,0` you'll get the partial-window answer (209), not Alteryx's (212). That's what to watch for.

**Dataiku (ordered by simplicity):**

1. **Simple prior/next-row reference in a Formula** (`OtherRows=NULL/Empty`) → Prepare recipe, Formula processor with `val("col", default, offset)`, `strval(...)`, or `numval(...)`. The `offset` argument is negative for prior rows, positive for next rows. Requires enabling **"Preserve ordering"** on the input dataset (or an explicit upstream Sort). Example — compounding inflation:
   ```
   val("Value", 50, 1) * ( 1 + (val("Inflation Rate", 0, 1) / 100) )
   ```
   This is the direct equivalent of `[Row-1:Value]` in Alteryx. It's a Formula Processor step — no separate Window recipe.

2. **"Fill empty with previous/next value"** → Prepare recipe, **up/down filler processor**. Dedicated processor for the most common Alteryx MultiRowFormula pattern.

   **For Window-based forward-fill** (when the data is already in a Window pipeline and you'd rather not branch out to a Prepare): DSS Window's `last(col)` aggregation does **NOT** do cumulative-up-to-current-row by default — it returns the current row's own value (frame is "current row only" even with `enableLimits: false`). Two workarounds:
   - **Monotonic data only:** use `--compute 'max:col:'` (cumulative max). Empty strings sort lexicographically before `'07'`, `'08'`, …, so `max` skips empty cells and the cumulative max picks up the latest non-empty value seen. Works for Year (`'07' < '08'`) but FAILS for non-monotonic data (e.g., `'08' → '09' → '08'` would lock at `'09'`).
   - **General-purpose forward-fill:** assign a `group_id` via cumulative `sum(is_set)` in one Window, then `--partition-key group_id --compute 'max:col:'` in a second Window (within each group only one row has the value set, so max = that value). Two recipes, but correct for any data shape. See `../../dku-cli/playbooks/tabular-flow.md` § Window aggregation framing.

3. **`[Row+1:Col]` lookahead** (next-row reference inside MultiRowFormula) → Window recipe with `--compute 'lead:col:'`. Default offset is 1; for further-ahead, use `--lead-offsets 'col:1,2,3'` (multi-offset in one Window). Example (date disambiguation where the current-row month letter is ambiguous and the next-row letter resolves it):
   ```bash
   dku recipe create-window lookahead -i in --output-ds out -P PROJ \
       --order-key row_idx \
       --compute 'lead:raw_month:' \
       --rename 'raw_month_lead:next_month'
   # Then a Prepare with: if(month=='J' && next_month=='F', 'Jan', if(month=='J' && next_month=='J', 'Jun', …))
   ```
   The `--compute 'TYPE:COL:OUTPUT'` third segment is silently ignored by DSS — always rename via `--rename SRC:DST` instead.

   **Trap when folding the post-MRF Filter into `--post-filter`:** the canonical "MRF detects flag row, Filter keeps flagged" Alteryx pattern (`MultiRowFormula(Flag = if [Row+1:col] matches /^[(]/) → Filter(Flag IsTrue)`) folds to ONE Window with `--compute 'lead:col:'` + `--post-filter`. But `--post-filter` runs on the pre-rename schema — `--post-filter 'startsWith(strval("next_month"), "(")'` after `--rename 'raw_month_lead:next_month'` filters on a column that doesn't exist yet and silently emits ZERO rows. Reference the pre-rename name in the filter: `--post-filter 'startsWith(strval("raw_month_lead"), "(")'`. The output dataset still has the renamed `next_month` column. See `../../dku-cli/playbooks/tabular-flow.md` § Window `--rename` ordering.

3. **Running total / lag with aggregation / partition-aware (`OtherRows=NULL`)** → Window recipe. Partition by group, order by an explicit column (add one with a Window `RowNumber` aggregation upstream if absent — Prepare has no `AddId` processor; use a Window with no partition + `RowNumber` instead).
   ```bash
   dku recipe create-window win -P PROJ -i in --output-ds windowed \
       --partition-key Region --order-key rec_id \
       --compute 'sum:Sales:'   # produces 'Sales_sum'
   ```

4. **Moving average with `OtherRows=Nearest` (boundary fill with edge value)** → Window with explicit lag aggregations + `FirstValue` aggregation, then a Prepare that null-coalesces lags against the FirstValue, then computes the average. The CLI's `--compute lag:col:` only sets the lag flag; multi-offset lags require a `set-settings` patch. Recipe (3-row MA, partition `Region`, order `rec_id`):

   ```bash
   # 1. Create window with lag + first
   dku recipe create-window w3 -P PROJ -i in --output-ds w3_out \
       --partition-key Region --order-key rec_id \
       --compute 'lag:Value:' --compute 'first:Value:'

   # 2. Patch the payload to enable lag offsets 1 AND 2 (CLI exposes only one default offset).
   dku recipe get-settings w3 -P PROJ -o json > /tmp/w3.json
   # In /tmp/w3.json, find payload.values[] entry where column == "Value":
   #   set lag=true, lagValues="1,2", first=true
   dku recipe set-settings w3 -P PROJ -s @/tmp/w3.json
   dku recipe apply-schema w3 -P PROJ && dku recipe run w3 -P PROJ --wait
   # → adds columns Value_lag1, Value_lag2, Value_first

   # 3. Prepare with null-coalesce + average
   dku recipe create-prepare ma_calc -P PROJ -i w3_out --output-ds ma
   dku recipe add-formula ma_calc -P PROJ --column r3mo \
       --expr '(if(isBlank(strval("Value_lag2")), numval("Value_first"), numval("Value_lag2")) + if(isBlank(strval("Value_lag1")), numval("Value_first"), numval("Value_lag1")) + numval("Value")) / 3.0'
   dku recipe add-delete-columns ma_calc -P PROJ --columns 'Value_lag1,Value_lag2,Value_first'
   dku recipe apply-schema ma_calc -P PROJ && dku recipe run ma_calc -P PROJ --wait
   ```

   Generalize: for window size W, request `lagValues="1,2,…,W-1"` and a 6+ formula null-coalesces. **Two Window recipes are needed when the same source has TWO moving averages with DIFFERENT partition keys** (e.g., `r3mo` partitioned by `(Region, Metric)` AND `r6mo` partitioned by `Metric` only) — partitioning is per-recipe in DSS Window. Chain them: rename the first window's output columns (Window's output names are `<col>_lag<k>` / `<col>_first` and DSS does NOT support custom names), then run the second window so its default names don't collide.

5. **Custom multi-row logic** → Window with a lag column + a trailing Prepare that references the lag column. **Reach for Python only when the recurrence references an as-yet-computed prior-row value of the SAME computed column** (rare).

**Caveats:**
- DSS Window's `Lag(col, k)` returns null at the boundary. To match Alteryx `<OtherRows>Nearest`, ALWAYS add a `FirstValue(col)` aggregation over the partition and null-coalesce the lags against it in a Prepare step (per option 4).
- `--compute lag:col:` accepts ONE default offset (1). Multi-offset windows need a `set-settings` patch on `payload.values[].lagValues` (comma-separated string like `"1,2,3,4,5"`).
- DSS Window output column names are NOT customizable — they default to `<src_col>_lag<k>` / `<src_col>_first`. Two Window recipes on the same source column will produce colliding names; insert a Prepare `add-rename` between them.
- For non-trivial recurrences (`Row-1` of the same output column), Python is the escape hatch.
- Window engine matters — SQL, DSS, and Spark differ in how they emit row numbers for ties; always add an explicit Sort upstream if determinism matters.

---

## RunningTotal

**Alteryx:** cumulative sum per partition, in input row order. Subset case of MultiRowFormula.

```xml
<Configuration>
  <GroupByFields><Field field="Region"/></GroupByFields>
  <RunningTotalFields><Field field="Sales"/></RunningTotalFields>
</Configuration>
```

**Dataiku:** Window recipe with PARTITION BY + ORDER BY + `sum`. With an `--order-key` set, DSS Window's default frame is "from start of partition to current row" — i.e. cumulative sum, matching SQL standard. No `--frame-preceding` flag needed.

```bash
# Alteryx RunningTotal needs an explicit row-order column. If the upstream pipeline
# already has one (e.g. Priority, date, sort key), pass it here. Otherwise add a
# RecordID upstream first.
dku recipe create-window runtot -P PROJ -i in --output-ds out \
    --partition-key Region --order-key sort_key \
    --compute 'sum:Sales:'   # produces 'Sales_sum' (column name not configurable)
```

**Caveats:**
- DSS Window output column is hardcoded to `<src_col>_sum` (NOT customizable at create time). If the downstream step references the Alteryx name like `RunTot_Sales`, either chain a Prepare `add-rename`, or just reference `Sales_sum` directly — usually simpler.
- Alteryx `RunningTotal` orders by **input row order** (which usually = the upstream Sort tool). DSS Window must have an explicit `--order-key`. If the input has no natural order column, either add a `RecordID`-equivalent upstream (`create-window … --compute 'rowNumber::rn'` with no partition) or fold the Sort tool's keys into the cumulative Window's `--order-key`.
- **Collapse hint:** when an Alteryx `RunningTotal` is followed by a `MultiRowFormula` that references `[Row-1:RunTot_X]` and `NumRows=1` (the typical "greedy fill" / "allocate by priority" pattern), do NOT add a separate Lag column — algebra: `[Row-1:RunTot_X] == RunTot_X - X`. The current cumulative minus the current row's value is exactly the previous cumulative. One Window + one `add-formula` instead of Window + Lag + Prepare. See `ayx/overview.md` § Collapse triggers — the `Sort → RunningTotal → MultiRowFormula` row.

---

## RecordID

**Alteryx:** adds a sequential integer.

```xml
<Configuration>
  <FieldName>RecordID</FieldName>
  <StartValue>1</StartValue>
  <FieldType>Int32</FieldType>
</Configuration>
```

**Dataiku:** Prepare `AddId` step (global row id, starts at 0; adjust with a `CreateColumnWithGREL: id + 1`).

```bash
--step '{"type":"AddId","params":{"outColumn":"RecordID"}}'
--step '{"type":"CreateColumnWithGREL","params":{"expression":"RecordID + 1","column":"RecordID"}}'
```

**Caveats:** if the data is partitioned across an engine (SQL / Spark), `AddId` is non-deterministic ordering unless an explicit Sort precedes it.

---

## TextToColumns

**Alteryx:** split one column into N new columns on a delimiter, or into N rows.

```xml
<Configuration>
  <Field>Range</Field>
  <NumFields value="2"/>
  <RootName>Range</RootName>
  <Delimeters value="-"/>
  <ErrorHandling>Last|Merge|Ignore</ErrorHandling>
  <Flags value="0"/>   <!-- 0 = split to columns; 1 = split to rows -->
</Configuration>
```

**Dataiku:**

Split to columns → Prepare `ColumnSplitter`:

```json
{
  "type": "ColumnSplitter",
  "params": {
    "inCol": "Range",
    "separator": "-",
    "outColPrefix": "Range",
    "target": "COLUMNS",
    "keepEmptyChunks": false,
    "limitOutput": false,
    "limit": 0
  }
}
```

Split to rows → Prepare `SplitFold` (split a column on a delimiter and emit one row per chunk).

**Caveats:**
- Alteryx `ErrorHandling=Last` puts the remainder in the last column if the delimiter appears more than `NumFields-1` times. **`ColumnSplitter` with `limitOutput: true, limit: N, startFrom: "beginning"` silently DROPS extras** (verified on `a,b,c,d,e` with `limit: 3` → `a, b, c` — `d,e` lost, no warning). Two fixes for "merge tail" parity:
  - **Regex extractor** (preferred for fixed N): one `ExtractRegex` step with `^([^,]*),([^,]*),(.*)$` + `targetColumns: ["c1","c2","c3"]` puts everything after the (N−1)-th delimiter into the last group.
  - **No-limit + concat tail**: `ColumnSplitter` with `limitOutput: false`, then a `CreateColumnWithGREL` that re-joins chunks `N-1..` with the original separator. Fragile — only use when N varies row-to-row.
- When `limitOutput: true`, `startFrom` is required (`"beginning"` or `"end"`, lowercase). Omitting it makes `apply-schema` reject the step.
- `ColumnSplitter` infers numeric types on its output columns when every row is numeric (e.g. `2000-2019` → `part0`,`part1` typed as `bigint`). You get the cast for free compared to a `CreateColumnWithGREL` + `toNumber(split(…)[i])` pair.

---

## RegEx

**Alteryx:** four modes — `Replace`, `Tokenize`, `Parse` (named capture groups → columns), `Match`.

```xml
<Configuration>
  <Method>Parse|Replace|Tokenize|Match</Method>
  <Field>Text</Field>
  <Pattern>(\d{3})-(\d{4})</Pattern>
  <Replace>$1$2</Replace>
  <CaseInsensitive value="False"/>
</Configuration>
```

**Dataiku Prepare steps:**
- `Parse` → `RegexpExtractor` (`column`, `pattern`, `extractAllOccurrences`). Output cols are named after the capture-group index — bare `1`, `2`, etc. — NOT `<col>_1`. Always follow with a `ColumnRenamer` step (`renamings:[{from:"1",to:"my_name"}]`); without it, downstream steps reference the cryptic numeric names. ColumnRenamer with a non-existent `from` is a silent no-op, so verify the index name with `dku dataset schema OUTPUT` after `apply-schema`.
- `Replace` → `FindReplace` with `matchingMode: REGEX`.
- `Tokenize` → `ColumnSplitter` with a regex separator.
- `Match` → `FilterOnCustomFormula` with `matches(s, /pat/)`.

**ParseComplex semantics — match Alteryx's "first decimal in segment" behavior.** Alteryx's `Method=ParseComplex` with a pattern like `(\d+\.?\d*)` returns the FIRST regex match anywhere in the field — there is no anchor. When migrating a `TextToColumns(split-to-rows) → RegEx(ParseComplex (\d+\.?\d*))` chain to DSS `SplitFold + RegexpExtractor`, do NOT add a closing-bracket / context anchor (e.g. `^([\d.]+)\]`) "to be safe" — it will silently drop rows where the value isn't followed by that context (truncated data, alternate group layouts where the bracket is positioned differently). Use `^([\d.]+)` (leading-decimal-only) for parity with Alteryx ParseComplex. Discovered in Challenge_022: input had two layouts — `[atm1.1/atm2.X]/atc1...` and `[atm1.1/atm2.X/atc1...]` — and rows truncated mid-string by a `Formula(size=N)` upstream had the trailing `]` cut off. The `]`-anchored regex matched neither, producing missing groups in the Group output (367 → 366 rows).

### XML-in-cell with N attributes per row (canonical "raw XML field" pattern)

**Pattern:** A column holds a multi-line XML document per row (e.g. `customer_OuterXML` containing `<customer><reference>X</reference><bill_to>...<contact><first_name>...</first_name>...</contact><address><city>...</city>...</address></bill_to><ship_to>...</ship_to></customer>`), and the goal is to flatten N nested attributes into N output columns of a wide table — one row per input row, no row multiplication.

**Alteryx solution (canonical 17-tool decomposition):** `RecordID + TextToColumns(split-to-rows on "<") + RegEx(ParseComplex "(.*?)>(.*)" → tag, value) + Filter(\w+) + MultiRowFormula(BillingShipping context = forward-fill on tag matching "bill"/"ship") + CrossTab(GroupBy=(RecordID,BS), Header=tag, Data=value, Concat) + AlteryxSelect(rename) + Filter(BS=="Bill") + DynamicRename(Billing_*) + Filter(BS=="Ship") + DynamicRename(Shipping_*) + Join(Bill,Ship on RecordID) + Filter(tag=="reference") on the original branch + Join(parent,wide on RecordID) + 2× Cleanse macro`. Decomposes into long form, pivots back, then self-joins.

**DSS collapse: ONE Prepare recipe with N `add-formula` regex-extract steps.** Skip the long-form decomposition entirely — extract each leaf value directly with one GREL `match()` call:

```bash
# Per-attribute extract (one add-formula per output column):
dku recipe add-formula prep_xml --column "Billing_first_name" \
  --expr 'match(strval("customer_OuterXML"), /(?s).*?<bill_to>.*?<first_name>(.*?)<\/first_name>.*/)[0]' -P PROJ
dku recipe add-formula prep_xml --column "Shipping_State" \
  --expr 'match(strval("customer_OuterXML"), /(?s).*?<ship_to>.*?<province>(.*?)<\/province>.*/)[0]' -P PROJ
# ... one formula per Billing_* and Shipping_* leaf ...
# Then: ColumnsSelector to drop customer_OuterXML.
```

**The pattern shape that makes this work**:
- The regex anchors on the **section-wrapper tag** (`<bill_to>`, `<ship_to>`, etc.) before the **leaf tag** (`<first_name>`, etc.). Without the section anchor, the `.*?` first-occurrence match would always land on the Billing copy of the leaf, even when extracting Shipping.
- `(?s)` inline flag enables DOTALL — required because the XML payload has newlines and `.*?` would not cross them otherwise.
- Surrounding `.*?` and `.*` make the whole expression match the entire input (GREL `match()` requires whole-string match — see `../../dku-cli/references/formulas.md` § Regex). The captured group is at index `[0]`.
- Tags with attributes (`<line sequence="1">525 pemberton ave</line>`) need `<line[^>]*>(.*?)</line>` instead of `<line>...</line>`.

**Mapping ratio: 17:1.** Verified on Challenge_037 (10 input rows × 27 output cols, exact value match with all 21 nested attributes extracted in one Prepare). The Alteryx solution's TextToColumns+RegEx+MultiRowFormula+CrossTab+self-join chain exists because Alteryx Formula tools can't run regex against the *whole* XML cell — they're field-by-field. DSS GREL `match()` against `strval("col")` is a one-shot regex against the whole cell, eliminating the need to decompose-then-recompose.

**Falls back to a Python recipe ONLY when:** (a) the XML has variable-cardinality lists (e.g. multiple `<line>` entries per address with no fixed count) — regex first-match drops the rest; or (b) namespaces / attribute-driven branching require true XPath. For fixed-schema XML-in-cell (the typical e-commerce export shape), the visual approach is enough.

---

## DynamicRename

**Alteryx:** renames columns based on a pattern, an expression, or a second input (rename map).

**Dataiku (ordered by complexity):**

1. **`RenameMode=FirstRow` with known header content (most common Grand-Prix-style pattern)** → static `add-rename --mappings`. The Alteryx flow promotes row N's values as column names; in DSS, you read the source file once during inventory, copy the actual header values, and bake them into a static rename map. Drop the noise rows (header marker, decorative `***`, "Data Downloaded" stamps) with `add-filter-rows`, drop the header row itself with `add-filter-rows --formula 'strval("Field_1") != "Surf Site"'` (using the known header-row sentinel), then `add-rename --mappings '{"Field_1":"Surf Site","Field_2":"Swell Direction",…}'`. ONE Prepare collapses Filter+DynamicRename — no plugin, no Python. Tested on Challenge_031: 5 noise rows + header → 18 clean rows with proper column names, all in one Prepare recipe. Only fall back to (2) below when the header content is variable run-to-run.
2. **Mass renamings with a regex** (e.g. strip prefix / case conversion across many cols) → Prepare `RenameColumns` processor with the "mass renamings" option. Supports add/remove prefix/suffix, case conversion, and regex replace across many columns in one step.
3. **Variable-position header row** → either set on upload (formatting tab: skip N rows, parse next as headers), or — if the header position is variable — a Prepare recipe `Use values of row as column names` (check availability; this processor has been deprecated in some versions).
4. **Rename from a second dataset (dynamic rename map)** → Prepare's `fold multiple columns by pattern` + find/replace regex + pivot back (roundabout, unstable schema). Generally prefer a Python recipe:
   ```python
   rename_map = dict(zip(right["old_name"], right["new_name"]))
   out = left.rename(columns=rename_map)
   ```
5. **Conditional per-column rename (`[_CurrentField_]` expression)** → Python recipe — no visual equivalent for per-column expression evaluation.

**Caveats:** dynamic renaming destabilizes downstream schema. If the output column set changes run-to-run, downstream Join/Prepare schemas will silently mismatch. Consider freezing the schema with a `set-schema` + explicit rename map where feasible.

---

## DateTime

### DSS date types

Recent DSS distinguishes three date types (older DSS had only one, ISO-8601 datetime with timezone):

- **Datetime with tz** — full ISO-8601, e.g. `2025-12-31T23:05:43.123Z`. The long-established DSS default.
- **Datetime no tz** — `yyyy-MM-dd HH:mm:ss(.SSS)?`, no timezone. Good for source systems that report "wall clock" times.
- **Date only** — `yyyy-MM-dd`, no time component. Common for "export to Excel" targets that shouldn't carry a time.

When parsing an Alteryx `Date` column, pick **Date only**; for `DateTime`, pick **Datetime no tz** unless the source is explicitly ISO-8601 with Z/offset. To convert across types, use a Parse date or Format date processor with the target type selected in "Output type". If converting in place (same column), also change the column's type manually.

### Alteryx `DateTime` tool

**Alteryx:** parse string→date or format date→string.

```xml
<Configuration>
  <IsFrom value="False"/>   <!-- "False" / "True" boolean form, OR "String" / "Date" enum form depending on Designer version. False/String = parse string→date; True/Date = format date→string -->
  <InputFieldName>ds</InputFieldName>
  <OutputFieldName>ds_parsed</OutputFieldName>
  <Format>yyyy-MM-dd</Format>
  <Language>English</Language>
</Configuration>
```

**Dataiku Prepare:**
- String → Date: `DateParser` step (params: `appliesTo`, `columns` (LIST), `outCol`, `formats`, `outType`, `lang`, `timezone_id`).
  ```json
  {"type":"DateParser","params":{"appliesTo":"SINGLE_COLUMN","columns":["ds"],"formats":["yyyy-MM-dd"],"lang":"auto","timezone_id":"UTC","outCol":"ds_parsed","outType":{"name":"out","type":"datetimenotz"}}}
  ```
  ⚠ Param is `columns` (array) and requires `appliesTo: "SINGLE_COLUMN"` — the singular `column` shape silently fails. See `../../dku-cli/references/prepare-processors.md` § DateParser.
- Date → String: `DateFormatter` (params: `inCol`, `outCol`, `format`).

**Caveats:**
- Alteryx format tokens match Java (`yyyy-MM-dd`), **not** C `strftime` — so `%Y-%m-%d` strings in Alteryx source are usually found in `DateTimeFormat` function calls inside a Formula tool, not in the DateTime tool itself. See Formula cheatsheet.
- ISO 8601: use `yyyy-MM-dd'T'HH:mm:ss'Z'` (single-quote the `T` and `Z` literals).
- `DateParser` without `outCol` silently nulls all rows — always specify `outCol`.
- Alteryx `DateTime(parse)` tolerates missing seconds (input `MM/dd/yyyy HH:mm` against format `MM/dd/yyyy hh:mm:ss` produces `:00` seconds). DSS `DateParser` is similarly lenient — list a format that matches the *actual* input precision (e.g. `M/d/yyyy H:mm` for unpadded inputs); the output `outType: datetimenotz` carries `:00` seconds automatically when the parse format omits them.

### Manual zero-padding macros (TextToColumns + padleft + concat + DateTime)

Alteryx workflows occasionally normalize date strings by **splitting → padleft each part → reconcatenating → parsing** — a 4-tool macro of the shape:

```
TextToColumns(field=date, delim="\s/:", NumFields=5)   # split MM/DD/YYYY HH:MM into 5 cols
Formula:                                               # padleft each numeric component
  [1] = padleft([1], 2, "0")
  [2] = padleft([2], 2, "0")
  [4] = padleft([4], 2, "0")
  [date] = [1]+"/"+[2]+"/"+[3]+" "+[4]+":"+[5]
AlteryxSelect (drop the 5 split cols)
DateTime(IsFrom=False, format=MM/dd/yyyy hh:mm:ss)     # parse to DateTime_Out
```

**DSS collapse: `DateParser → DateFormatter → DateFormatter` (one Prepare recipe).** The manual padleft dance is unnecessary — DSS `DateFormatter` zero-pads automatically when the format pattern uses `MM/dd/yyyy HH:mm` (vs the source's `M/d/yyyy H:mm`). Output column is just the formatted string.

```bash
# Step 1: parse the un-padded source
dku recipe add-step prep --type DateParser --params '{
  "appliesTo":"SINGLE_COLUMN","columns":["date_time"],
  "formats":["M/d/yyyy H:mm"],"lang":"auto","timezone_id":"UTC",
  "outCol":"_parsed","outType":{"name":"out","type":"datetimenotz"}}' -P PROJ

# Step 2: re-emit zero-padded version (overwrite source col)
dku recipe add-step prep --type DateFormatter --params '{
  "inCol":"_parsed","outCol":"date_time","format":"MM/dd/yyyy HH:mm",
  "lang":"auto","timezone_id":"UTC"}' -P PROJ

# Step 3: emit the ISO datetime variant
dku recipe add-step prep --type DateFormatter --params '{
  "inCol":"_parsed","outCol":"DateTime_Out","format":"yyyy-MM-dd HH:mm:ss",
  "lang":"auto","timezone_id":"UTC"}' -P PROJ

# Step 4: drop the parse intermediate
dku recipe add-step prep --type ColumnsSelector --params '{
  "appliesTo":"SINGLE_COLUMN","columns":["_parsed"],"keep":false}' -P PROJ
```

**4 Alteryx tools → 1 Prepare recipe (4 steps).** Verified Challenge_034. `DateFormatter` overwriting the source column is supported (set `outCol` to the existing column name).

---

## GenerateRows

**Alteryx:** repeats/emits rows based on an init/condition/loop expression.

```xml
<Configuration>
  <CreateField_Name>Area</CreateField_Name>
  <Expression_Init>[Start]</Expression_Init>
  <Expression_Cond>[Area]&lt;=[End]</Expression_Cond>
  <Expression_Loop>[Area] + 1</Expression_Loop>
</Configuration>
```

**Dataiku — pick by shape:**

1. **Range join (integer BETWEEN) on SQL** — the most common "GenerateRows then Join" pattern. Skip the row expansion entirely. SQL recipe:
   ```sql
   SELECT c.*, r.*
   FROM customers c
   JOIN ranges r ON c.postal_area BETWEEN r.start AND r.end
   ```
   Or Join recipe with a `CUSTOM` condition if the connection supports it.

2. **Prepare-only expansion (visual, filesystem or SQL)** — `ColumnSplitter` → `CreateColumnWithGREL` (`forRange`) → `ArrayFold`. This is the pattern the skill has always advocated; confirmed working on stock DSS:
   ```json
   {"type":"ColumnSplitter","params":{"inCol":"Range","separator":"-","outColPrefix":"part","target":"COLUMNS","keepEmptyChunks":false,"limitOutput":false,"limit":0}}
   {"type":"CreateColumnWithGREL","params":{"expression":"forRange(-1, part1 - part0, 1, v, part0 + v + 1)","column":"Area"}}
   {"type":"ArrayFold","params":{"column":"Area"}}
   ```
   Downstream: equi-join `customers.Postal Area = ranges_expanded.Area`, then group. `ColumnSplitter` auto-types `part0`/`part1` as `bigint` when every value is numeric, so no `toNumber`/`set-schema` is needed.

   For date spines, swap the middle step for `forRange(-1, diff(end,start), 1, v, v+1)` and add a trailing `CreateColumnWithGREL` with `computeDate(start, offset, "day")` to compute the date.

   `ArrayUnfold` is the sibling processor — it expands an array into columns, not rows. Pick `ArrayFold` for GenerateRows-style row expansion.

3. **No-Prepare fallback (pure visual, every recipe is a shortcut)** — "Cross-join → Filter → Group". Useful when the target team has no Prepare users or when the expanded row count would explode. Four recipes:
   1. Prepare: compute numeric `Start`, `End` from the range string. `toNumber(split(Range,"-")[0])` / `toNumber(split(Range,"-")[1])` via `add-formula` — `toNumber()` makes the output correctly typed as `bigint`; `numval(expr, default)` does NOT work here because `numval` takes a quoted column name, not an expression.
   2. Join with `-j CROSS`: customers × ranges_prep.
   3. `create-filter` on the cross product. Reference space-containing columns with `numval("Postal Area")` / `strval(...)` — backticked `` `Postal Area` `` is rejected by the GREL filter parser (`ParsingException at offset 0`).
   4. `create-group --no-global-count` with `--agg 'Customer ID:count'`.

4. **Dynamic loop (arbitrary init/cond/loop)** → Python recipe, only when neither option 1/2/3 applies.

5. **Cartesian product across two datasets** → Join recipe with `type: CROSS`, or SQL `CROSS JOIN`.

**Caveats:** row expansion can blow up. Check `count(ranges) * max(End - Start)` before running option 2, or `count(customers) * count(ranges)` for option 3 — pair with a SQL engine for large tables.

---

## JSONParse

**Alteryx:** parses a JSON column into `JSON_Name` + `JSON_ValueString` tall records, one row per leaf.

**Dataiku Prepare:**
- Flatten-one-level JSON → `UnfoldObject` step on the JSON column.
- Tall (one row per leaf) → `UnfoldObject` then a Python recipe to melt, or `JSON to columns` recipe (if plugin installed).
- Deep/irregular JSON → Python recipe with `json.loads` + `pandas.json_normalize`.

---
