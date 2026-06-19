# Alteryx State and Parsing Tools to Dataiku

Row-state, parsing, dynamic rename, dates, generated rows, JSON.

**Contents:** MultiRowFormula · RunningTotal · RecordID · TextToColumns · RegEx · DynamicRename · DateTime · GenerateRows · JSONParse

## MultiRowFormula

**Alteryx:** per-row formula referencing prior/next rows (`[Row-1:Col]`, `[Row+1:Col]`) inside a `GroupByFields` partition, ordered by input row order. Config: `CreateField_Name/_Type`, `OtherRows`, `GroupByFields`, `Expression`, `NumRows`.

### `<OtherRows>` boundary semantics — pick translation by this value

What `[Row-N:Col]` returns when offset N runs off the partition start/end:

| `<OtherRows>` | Alteryx at boundary | DSS translation |
|---|---|---|
| `NULL` (default) | null | DSS Window `Lag(col,k)` also nulls at boundary — semantics match. Use Window directly. |
| `Empty` | "" | Same as NULL for numeric cols. Same Window translation. |
| `Nearest` | first/last value of partition (edge value) | DSS `Lag` nulls at boundary — does NOT match. Add `FirstValue(col)` over partition + a Prepare `if(isBlank(lag_k), first_v, lag_k)` per offset before averaging. |

`Nearest` is the trap: common in moving-average flows (makes leading-edge averages well-defined). DSS Window's *natural partial-window* gives a THIRD answer (avg over available rows). 3-row MA at row 2, input `(218,200,…)`:

| Alteryx `Nearest` | DSS partial-window | DSS Window + lag-coalesce |
|---|---|---|
| `(218+218+200)/3 = 212` | `(218+200)/2 = 209` | `212` ✓ |

A vanilla `--compute 'avg:Value:r3mo' --window-frame -2,0` yields 209, not 212.

### Dataiku translations (by simplicity)

1. **Prior/next-row ref in a Formula** (`OtherRows=NULL/Empty`) → Prepare Formula with `val("col", default, offset)` / `strval(...)` / `numval(...)`; offset negative=prior, positive=next. Requires **"Preserve ordering"** on input (or an upstream Sort). Direct equivalent of `[Row-1:Value]`, no separate Window:
   ```
   val("Value", 50, 1) * ( 1 + (val("Inflation Rate", 0, 1) / 100) )
   ```

2. **"Fill empty with previous/next value"** → Prepare up/down filler processor.

   **Window-based forward-fill** (data already in a Window pipeline): DSS `last(col)` does NOT cumulate up to current row — it returns the current row's own value. Two workarounds:
   - **Monotonic data only:** `--compute 'max:col:'` (cumulative max); empty strings sort before `'07'`,`'08'` so max skips them. FAILS for non-monotonic (`'08'→'09'→'08'` locks at `'09'`).
   - **General:** assign `group_id` via cumulative `sum(is_set)` in one Window, then `--partition-key group_id --compute 'max:col:'` in a second (within each group only one row is set → max = that value). Two recipes, correct for any shape.

3. **`[Row+1:Col]` lookahead** → Window `--compute 'lead:col:'` (default offset 1; further-ahead via `--lead-offsets 'col:1,2,3'`):
   ```bash
   dku recipe create-window lookahead -i in --output-ds out -P PROJ \
       --order-key row_idx --compute 'lead:raw_month:' \
       --rename 'raw_month_lead:next_month'
   # Prepare: if(month=='J' && next_month=='F','Jan', if(month=='J' && next_month=='J','Jun',…))
   ```
   The `--compute 'TYPE:COL:OUTPUT'` third segment is silently ignored — always `--rename SRC:DST`.

   **Trap folding the post-MRF Filter into `--post-filter`:** canonical "MRF flags row, Filter keeps flagged" (`Flag = if [Row+1:col] matches /^[(]/` → `Filter(Flag)`) → ONE Window `--compute 'lead:col:'` + `--post-filter`. But `--post-filter` runs on the **pre-rename** schema — `--post-filter 'startsWith(strval("next_month"),"(")'` after `--rename 'raw_month_lead:next_month'` filters a not-yet-existing column → ZERO rows silently. Use the pre-rename name: `--post-filter 'startsWith(strval("raw_month_lead"),"(")'`. Output still has renamed `next_month`.

4. **Running total / lag with aggregation / partition-aware** (`OtherRows=NULL`) → Window, partition by group, order by explicit column (add one upstream via Window `rowNumber` if absent — Prepare has **no `AddId`** processor, see § RecordID):
   ```bash
   dku recipe create-window win -P PROJ -i in --output-ds windowed \
       --partition-key Region --order-key rec_id --compute 'sum:Sales:'   # → Sales_sum
   ```

5. **Moving average with `OtherRows=Nearest`** → Window with explicit lag aggregations + `FirstValue`, then a Prepare null-coalescing lags against FirstValue, then averaging. CLI `--compute lag:col:` sets only the lag flag; multi-offset lags need a `set-settings` patch (3-row MA, partition `Region`, order `rec_id`):
   ```bash
   dku recipe create-window w3 -P PROJ -i in --output-ds w3_out \
       --partition-key Region --order-key rec_id \
       --compute 'lag:Value:' --compute 'first:Value:'
   # Patch payload.values[] for column "Value": lag=true, lagValues="1,2", first=true
   dku --format json recipe get-settings w3 -P PROJ > /tmp/w3.json
   dku recipe set-settings w3 -P PROJ -s @/tmp/w3.json
   dku recipe apply-schema w3 -P PROJ && dku recipe run w3 -P PROJ --wait
   # → Value_lag1, Value_lag2, Value_first
   dku recipe create-prepare ma_calc -P PROJ -i w3_out --output-ds ma
   dku recipe add-formula ma_calc -P PROJ --column r3mo \
       --expr '(if(isBlank(strval("Value_lag2")), numval("Value_first"), numval("Value_lag2")) + if(isBlank(strval("Value_lag1")), numval("Value_first"), numval("Value_lag1")) + numval("Value")) / 3.0'
   dku recipe add-delete-columns ma_calc -P PROJ --columns 'Value_lag1,Value_lag2,Value_first'
   dku recipe apply-schema ma_calc -P PROJ && dku recipe run ma_calc -P PROJ --wait
   ```
   For window size W: `lagValues="1,2,…,W-1"`. **Two Window recipes needed when one source has TWO MAs with DIFFERENT partition keys** (`r3mo` by `(Region,Metric)`, `r6mo` by `Metric`) — partitioning is per-recipe. Chain them and rename the first's outputs (Window names are `<col>_lag<k>`/`<col>_first`, NOT customizable) so the second's defaults don't collide.

6. **Custom multi-row logic** → Window + lag column + trailing Prepare. When the recurrence references the as-yet-computed prior-row value of the SAME column (conditional-carry running balance), it's NOT a Window — see Conditional-carry below.

### MultiRowFormula → Summarize (de-duped running state)
MRF marks "first in group" → Filter to first-only → Summarize. DSS: **Window with `first_value` aggregation (no Filter)**, or Group with `first` agg.

### Caveats / edge-fill rule (`../../dku-cli/playbooks/tabular-flow.md` links this)
- DSS `Lag(col,k)` returns null at the partition boundary. To match `<OtherRows>Nearest`, ALWAYS add a `FirstValue(col)` aggregation and null-coalesce lags against it in a Prepare (option 5).
- `--compute lag:col:` accepts ONE default offset (1); multi-offset needs a `set-settings` patch on `payload.values[].lagValues` (comma string `"1,2,3"`).
- Window output names are fixed `<col>_lag<k>` / `<col>_first`; two Window recipes on the same source column collide — insert a Prepare `add-rename` between.
- Window engine matters — SQL/DSS/Spark differ on tie row-numbers; add an explicit Sort upstream for determinism.

### Conditional-carry running total → SQL recursive CTE (NOT Window)
`Running = if [Row-1:Running] + x <= CAP then [Row-1:Running]+x else [Row-1:Running]` (capacity-constrained greedy fill / knapsack / "add until budget hit, skip non-fitting items"). NOT the unconditional `RunningTotal → MultiRowFormula` collapse — the Window-algebra trick (`[Row-1:RunTot] == RunTot - x`) only works when EVERY row contributes; here contribution depends on accumulated state, so a plain cumulative Window can't express it.

**Prefer SQL recursive CTE over Python** (visual → SQL → Python). Maps cleanly to `WITH RECURSIVE`:
- `ROW_NUMBER() OVER (PARTITION BY <grp> ORDER BY <Alteryx sort keys, then stable-sort tiebreak>) AS rn` CTE.
- **anchor** member `WHERE rn = 1` seeds state.
- **recursive** member `JOIN`s next row (`j.rn = r.rn + 1`), carries state via `CASE WHEN r.remaining >= j.demand THEN r.remaining - j.demand ELSE r.remaining END`.

If inputs are filesystem/UploadedFiles, `dku recipe create-sync -c <sql_conn>` them onto SQL first → one SQL recipe for the whole MRF chain. **Two SQL gotchas:** PostgreSQL needs the keyword `WITH RECURSIVE` (plain `WITH` → `relation "rec" does not exist`); run `apply-schema` BEFORE first run or the auto-created table has wrong column count (`INSERT has more expressions than target columns`). Reproduce the Alteryx stable-sort tiebreak explicitly (`ORDER BY "Demand" DESC, "OrderID" ASC`) or tied rows diverge. Fall back to a Python `for` loop (~4 lines) ONLY when no SQL connection exists. (Join+Sort+3×MRF+Filter+Select → 1 SQL recipe; Python knapsack example: see `tools-predictive-ml.md` § Optimization.)

### Date-diff-to-previous-row → 3 visual recipes (time-window dedup)
`datetimediff([Col],[Row-1:Col],"seconds")<N → flag` ("duplicate within N seconds"). NO Python:
1. **Prepare** `DateParser` timestamp string → ISO `date` (`outType: datetimenotz`).
2. **Window** `--partition-key <group> --order-key <parsed_date> --compute 'lag:<parsed_date>:<lag_col>'`.
3. **Prepare** `DateDifference` (`compareTo:COLUMN`, `outputUnit:SECONDS`, `input1`=lag, `input2`=current → output = current − lag) then `add-formula flag = if(isBlank(gap), 0, if(abs(gap) < N, 1, 0))`. The `isBlank(gap)` guard reproduces `<OtherRows>Empty/NULL` (first row per group → 0).

**Critical: parse the date to ISO BEFORE the Window.** Ordering a Window by an unparsed `M/d/yyyy H:m:s` string sorts lexicographically (chronologically WRONG across months/years — `"1/30/2016"` sorts before `"11/30/2015"`), so `lag` grabs the wrong predecessor, garbage diffs, no error. (`DateDifference` orientation: output = `input2 − input1`; use `abs()` so sign mistakes can't bite.)

---

## RunningTotal

**Alteryx:** cumulative sum per partition, in input row order. Subset of MultiRowFormula. Config: `GroupByFields`, `RunningTotalFields`.

**Dataiku:** Window with PARTITION BY + ORDER BY + `sum`. With `--order-key` set, DSS Window's default frame is "start of partition → current row" (cumulative, SQL standard) — no `--frame-preceding` needed.
```bash
dku recipe create-window runtot -P PROJ -i in --output-ds out \
    --partition-key Region --order-key sort_key --compute 'sum:Sales:'   # → Sales_sum
```

**Caveats:**
- Output is hardcoded `<src_col>_sum`. If downstream references the Alteryx name (`RunTot_Sales`), chain a Prepare `add-rename`, or just reference `Sales_sum`.
- Alteryx orders by **input row order** (= upstream Sort tool). DSS needs an explicit `--order-key`. No natural order column → add a row id upstream (`create-window … --compute 'rowNumber::rn'` no partition) or fold the Sort tool's keys into `--order-key`.
- **Collapse hint:** `RunningTotal` followed by `MultiRowFormula` referencing `[Row-1:RunTot_X]` with `NumRows=1` (greedy fill / allocate-by-priority) → do NOT add a Lag column; algebra `[Row-1:RunTot_X] == RunTot_X - X`. One Window + one `add-formula` instead of Window+Lag+Prepare. See `ayx/overview.md` § Collapse triggers (`Sort → RunningTotal → MultiRowFormula`).

---

## RecordID

**Alteryx:** adds a sequential integer. Config: `FieldName`, `StartValue`, `FieldType`.

**Dataiku: there is NO Prepare row-counter processor.** `AddId` is NOT a valid step type — `apply-schema` fails at run with `UnavailableTypeException: Type AddId was available in a plugin that is not installed` (same trap as `Enumerator`). Never add `{"type":"AddId",…}`. Three options by preference:

1. **Pre-bake the id at extraction** (cleanest when input is an uploaded file and RecordID just numbers rows 1..N): write the id in the Python `csv.writer` with `enumerate(rows, 1)`, then `set-schema` to `int`/`bigint`. Downstream Prepare needs no counter.
2. **Window `rowNumber`** (input already a managed dataset): `create-window … --compute 'rowNumber::rn'` no partition. ⚠ needs explicit `--order-key`; output is hardcoded lowercase `rownumber` (the `::rn` is advisory/ignored — `--rename 'rownumber:RecordID'`). See `tools-join-reshape.md`.
3. 1-based id from a 0-based source: add `--step '{"type":"CreateColumnWithGREL","params":{"expression":"RecordID + 1","column":"RecordID"}}'`.

**Caveat:** on SQL/Spark a row id has no stable meaning without an explicit Sort/`--order-key` upstream.

---

## TextToColumns

**Alteryx:** split one column into N columns on a delimiter, or into N rows (`Flags`: 0=columns, 1=rows; `ErrorHandling`: Last|Merge|Ignore).

**Dataiku:**
- Split to columns → Prepare `ColumnSplitter`:
  ```json
  {"type":"ColumnSplitter","params":{"inCol":"Range","separator":"-","outColPrefix":"Range","target":"COLUMNS","keepEmptyChunks":false,"limitOutput":false,"limit":0}}
  ```
- Split to rows → Prepare `SplitFold` (one row per chunk).

**Caveats:**
- `ErrorHandling=Last` (remainder into last col when delimiter > `NumFields-1` times): **`ColumnSplitter` with `limitOutput:true, limit:N, startFrom:"beginning"` silently DROPS extras** (`a,b,c,d,e` limit 3 → `a,b,c`; `d,e` lost, no warning). Two "merge tail" fixes:
  - **Regex extractor** (preferred, fixed N): one `ExtractRegex` with `^([^,]*),([^,]*),(.*)$` + `targetColumns:["c1","c2","c3"]` — everything after the (N−1)th delimiter lands in the last group.
  - **No-limit + concat tail**: `ColumnSplitter` `limitOutput:false`, then `CreateColumnWithGREL` re-joining chunks `N-1..` with the separator. Fragile — only when N varies row-to-row.
- When `limitOutput:true`, `startFrom` is required (`"beginning"`/`"end"`, lowercase); omitting it makes `apply-schema` reject the step.
- `ColumnSplitter` infers numeric types when every row is numeric (`2000-2019` → `part0`,`part1` as `bigint`) — free cast vs `CreateColumnWithGREL` + `toNumber(split(…)[i])`.

---

## RegEx

**Alteryx:** four modes — `Replace`, `Tokenize`, `Parse` (named groups → columns), `Match`. Config: `Method`, `Field`, `Pattern`, `Replace`, `CaseInsensitive`.

**Dataiku Prepare steps:**

| Alteryx mode | DSS step |
|---|---|
| `Parse` | `RegexpExtractor` (`column`, `pattern`, `extractAllOccurrences`). Output cols named by capture-group **index** — bare `1`,`2` — NOT `<col>_1`. ALWAYS follow with `ColumnRenamer` (`renamings:[{from:"1",to:"my_name"}]`); a non-existent `from` is a silent no-op, so verify with `dku dataset schema OUTPUT` after `apply-schema`. |
| `Replace` | `FindReplace` with `matchingMode: REGEX` |
| `Tokenize` | `ColumnSplitter` with a regex separator |
| `Match` | `FilterOnCustomFormula` with `matches(s, /pat/)` |

**`Parse` + `SplitToRows=True` (explode ALL matches to rows) — do NOT use `RegexpExtractor`.** Alteryx `ParseSimple` + `<SplitToRows value="True"/>` + no-group pattern (`#\w+` for hashtags) emits **one row per match**. `RegexpExtractor` with `extractAllOccurrences:true` instead makes *per-occurrence columns* (not an array, so `ArrayUnfold` has nothing to unfold) and fails `apply-schema` with `ApplicativeException: Empty column name`. **Collapse (3 steps, one Prepare):**
1. `SplitFold` (`{"column":"text","separator":" "}`) — explode to rows on whitespace, one token/row. (`SplitFold` is the only row-exploder; `ColumnSplitter target:JSON` + `ArrayUnfold` is the 2-step equivalent if the separator must be a regex.)
2. `add-formula` pulling the match per token, guarding no-match: `if(isNull(match(strval("text"), /(#\w+).*/)), "", match(strval("text"), /(#\w+).*/)[0])`. Trailing `.*` for two reasons: GREL `match()` is **whole-string** (`Matcher.matches()`), so `/(#\w+)/` alone returns null on `#EEUU:` (the `:` unmatched) — `.*` absorbs trailing punctuation; and the group keeps the leading `#`. Regex is a `/.../` **literal**, never a `"string"`. No GREL `test()` — guard with `isNull(match(...))`.
3. `add-filter-rows --formula 'hashtag != ""' --action KEEP_ROW` — replicates the downstream `Filter(IsNotNull)`.

**ParseComplex — match Alteryx "first decimal in segment".** `ParseComplex` with `(\d+\.?\d*)` returns the FIRST match anywhere, no anchor. Migrating `TextToColumns(split-to-rows) → RegEx(ParseComplex (\d+\.?\d*))` to `SplitFold + RegexpExtractor`: do NOT add a context anchor (`^([\d.]+)\]`) "to be safe" — it silently drops rows where the value isn't followed by that context (truncated data, alternate layouts). Use `^([\d.]+)` (leading-decimal-only). Rows truncated mid-string by an upstream `Formula(size=N)` can have a trailing delimiter cut, so a context anchor matches neither layout and silently drops them.

### XML-in-cell with N attributes per row (fixed-schema "raw XML field")

**Pattern:** a column holds a multi-line XML doc per row; goal is to flatten N nested attributes into N output columns (one row per input row, no multiplication).

**DSS collapse: ONE Prepare with N `add-formula` regex-extract steps.** Skip long-form decomposition — extract each leaf with one GREL `match()`:
```bash
dku recipe add-formula prep_xml --column "Billing_first_name" \
  --expr 'match(strval("customer_OuterXML"), /(?s).*?<bill_to>.*?<first_name>(.*?)<\/first_name>.*/)[0]' -P PROJ
dku recipe add-formula prep_xml --column "Shipping_State" \
  --expr 'match(strval("customer_OuterXML"), /(?s).*?<ship_to>.*?<province>(.*?)<\/province>.*/)[0]' -P PROJ
# ... one formula per leaf ... then ColumnsSelector to drop customer_OuterXML
```
What makes it work:
- Anchor on the **section-wrapper tag** (`<bill_to>`,`<ship_to>`) BEFORE the **leaf tag** — without it the `.*?` first-match always lands on the first (e.g. Billing) copy.
- `(?s)` (DOTALL) — required; the XML has newlines `.*?` won't cross otherwise.
- Surrounding `.*?`/`.*` make the whole expression match (GREL `match()` is whole-string — `../../dku-cli/references/formulas.md` § Strings); captured group at `[0]`.
- Tags with attributes (`<line sequence="1">…</line>`) need `<line[^>]*>(.*?)</line>`.

The Alteryx `TextToColumns+RegEx+MultiRowFormula+CrossTab+self-join` chain exists because Alteryx Formula tools run regex field-by-field, not against the whole cell; GREL `match()` against `strval("col")` is one-shot whole-cell — that long chain collapses to one Prepare.

**Falls back to Python ONLY when:** (a) variable-cardinality lists (multiple `<line>` per address, no fixed count) — regex first-match drops the rest; or (b) namespaces / attribute-driven branching need true XPath.

### Whole-document nested XML (variable-cardinality, row-multiplying) → ONE Python parse recipe

**Pattern:** a whole XML document with nested repeating elements at multiple depths exploding into many rows (e.g. `programs > program > {concertInfo*, worksInfo > work* > soloists > soloist*}` → one row per (program, work)). Case (a)/(b) above — in-cell regex can't (first-match keeps one child, no fixed column count).

**Alteryx's huge chain is mostly XMLParse plumbing.** `XMLParse` descends ONE level per instance and emits a *separate stream* of `_OuterXML` child blobs, so a 4-level doc needs a CHAIN of `XMLParse → XMLParse → …` then `Join`/`Summarize(Concat)`/`Unique` to **re-assemble** the split streams.

**Almost all of it VANISHES in one Python parse** (`xml.etree.ElementTree`) — a real parser walks the nested tree directly, no stream-split, so no join/concat/unique to re-assemble. Collapses to **1 Python recipe** (parse → flatten → write) + at most **1 Prepare** for the visual tail (date substring, rename, reorder). Legitimate Python per the ladder — XML tree-walking has no DSS visual equivalent.

**Faithful-flatten checklist (Alteryx semantics that bite):**
- **Concat-then-filter placeholders, not per-element.** Alteryx: `Formula([name]+", ("+[inst]+")")` → `Summarize(Concat, sep=", ")` → `Filter([Soloists] != ", ()")`. The filter drops only when the *entire* concat equals `", ()"` — it does NOT strip embedded `", ()"` from a multi-element concat. Python: build full concat, then `"" if full == ", ()" else full`. Filtering per-element diverges when the first soloist is blank.
- **A repeated child key concats across occurrences.** Same `work ID` can appear multiple times within one program; `Summarize(GroupBy=programID,ID)` concats across all, then `Unique` dedups. Group soloist parts by (parentKey, childKey) across the whole doc, not per-occurrence.
- **A parent with no children still emits a row** (Alteryx LEFT-joins parent onto child stream). A `program` with empty `worksInfo` → one blank-work row; don't `continue` past childless parents.
- **First-child reduction.** One row per work but a program has several `concertInfo` → take the FIRST per program (`Unique` on program key): `parent.find("concertInfo")`, don't iterate all.

**Wire with a managed-folder input:** stage the file (`dku folder upload`), `dku recipe create parse_xml -t python --input-folder <folder> --output-ds parsed --connection <conn> -P PROJ`; read via `dataiku.Folder(...).get_download_stream(path)`. If `create` rejects the folder as input, create with the output only and wire the folder via `set-settings` — see `tools-io-apps-ml.md` (QuickDraw counter-example).

---

## DynamicRename

**Alteryx:** renames columns by pattern, expression, or a second input (rename map).

**Dataiku (by complexity):**

1. **`RenameMode=FirstRow` with known header** → static `add-rename --mappings`. Read the source once during inventory, copy the actual header values, bake a static map. Drop noise rows (header marker, `***`, "Data Downloaded" stamps) with `add-filter-rows`, drop the header row with `add-filter-rows --formula 'strval("Field_1") != "<sentinel>"'` (known sentinel value), then `add-rename --mappings '{"Field_1":"<header>",…}'`. ONE Prepare collapses Filter+DynamicRename. Only fall to (2) when header content varies run-to-run.
2. **Mass renamings with a regex** (strip prefix / case convert) → Prepare `RenameColumns` "mass renamings" (add/remove prefix/suffix, case, regex replace).
3. **Variable-position header row** → set on upload (skip N rows, parse next as headers), or Prepare `Use values of row as column names` (deprecated in some versions).
4. **Rename from a second dataset → materialize into STATIC `ColumnRenamer` + `ColumnsSelector`, one Prepare. NOT Python.** When the second input is a *fixed lookup* (code → label, the common case), read it once during inventory and bake the map. Build params programmatically, then one Prepare:
   - `ColumnsSelector` (`{"appliesTo":"COLUMNS","columns":[<mapped codes>],"keep":true}`) — keeps only mapped columns (what the Alteryx `DynamicSelect` after the rename did: drop unmapped row-key/`Name` columns).
   - `ColumnRenamer` (`{"renamings":[{"from":code,"to":newname},…]}`).
   DSS preserves arbitrary names (spaces, `/`, `()`, `+`, `:`) and column order through both. **Name-formula detail:** when the new name concatenates lookup fields (`Category / SubCategory / Description`), Alteryx joins with fixed `" / "` → `Cat /  / Desc` for empty parts, but the canonical output **skips empty parts** (`Cat / Desc`) — build with `" / ".join(p for p in parts if p)`. Python ONLY when the map varies run-to-run (`out = left.rename(columns=dict(zip(right["old"], right["new"])))`).
5. **Conditional per-column rename (`[_CurrentField_]` expression)** → Python recipe — no visual per-column expression evaluation.

### CrossTab → DynamicRename
Pivot recipe + trailing Prepare with static `RenameColumns`. Rename-from-input-table needs Python. (See `tools-join-reshape.md` § CrossTab.)

**Caveat:** dynamic renaming destabilizes downstream schema. If the output column set changes run-to-run, downstream Join/Prepare schemas silently mismatch. Freeze with `set-schema` + explicit map where feasible.

---

## DateTime

### DSS date types
- **Datetime with tz** — full ISO-8601 `2025-12-31T23:05:43.123Z`. Long-established default.
- **Datetime no tz** — `yyyy-MM-dd HH:mm:ss(.SSS)?`, no tz. For "wall clock" source systems.
- **Date only** — `yyyy-MM-dd`, no time. For "export to Excel" targets.

Parsing Alteryx `Date` → **Date only**; `DateTime` → **Datetime no tz** unless source is explicitly ISO-8601 with Z/offset. Convert via Parse/Format date with target type in "Output type"; if converting in place, also change the column type manually.

### Alteryx `DateTime` tool
Parse string→date or format date→string. Config: `IsFrom` (`False`/`String` = parse; `True`/`Date` = format — form varies by Designer version), `InputFieldName`, `OutputFieldName`, `Format`, `Language`.

**Dataiku Prepare:**
- String → Date: `DateParser`:
  ```json
  {"type":"DateParser","params":{"appliesTo":"SINGLE_COLUMN","columns":["ds"],"formats":["yyyy-MM-dd"],"lang":"auto","timezone_id":"UTC","outCol":"ds_parsed","outType":{"name":"out","type":"datetimenotz"}}}
  ```
  ⚠ Param is `columns` (array) + requires `appliesTo:"SINGLE_COLUMN"` — the singular `column` shape silently fails. See `../../dku-cli/references/prepare-processors.md` § DateParser.
- Date → String: `DateFormatter` (`inCol`, `outCol`, `format`).

**Caveats:**
- Alteryx format tokens are Java (`yyyy-MM-dd`), NOT C `strftime` — `%Y-%m-%d` strings appear in `DateTimeFormat` function calls inside a Formula tool, not the DateTime tool. See Formula cheatsheet.
- ISO 8601: `yyyy-MM-dd'T'HH:mm:ss'Z'` (single-quote `T` and `Z`).
- `DateParser` without `outCol` silently nulls all rows — always specify `outCol`.
- Alteryx `DateTime(parse)` tolerates missing seconds (`MM/dd/yyyy HH:mm` against `…:ss` → `:00`). DSS `DateParser` is similarly lenient — list a format matching the *actual* input precision (`M/d/yyyy H:mm` for unpadded); `outType:datetimenotz` carries `:00` automatically.

### Packed-integer dates — `CYYMMDD` (century flag + YYMMDD)
Legacy exports (COBOL/SAS/ERP) store a date as a 7-char packed int: leading digit = century flag (`0`→19xx, `1`→20xx), rest `YYMMDD` — `1040202`→2004-02-02, `0990930`→1999-09-30, `0000101`→1900-01-01. Alteryx: `if Left([date],1)=="0" then DateTimeParse("19"+Right([date],6),"%Y%m%d") else …"20"… endif`.

DSS — ONE `add-formula` building the ISO string:
```
(if(substring(strval("date"),0,1)=="0","19","20") + substring(strval("date"),1,3)) + "-" + substring(strval("date"),3,5) + "-" + substring(strval("date"),5,7)
```
- **Use `strval("date")`, NOT bareword `date`.** Digit-only with a leading zero (`"0990930"`); a bareword auto-coerces to a number, drops the leading zero (`990930`), shifts every `substring` offset — silently wrong, no error. (See `../../dku-cli/references/formulas.md` "Leading zeros disappear → wrap in `strval`".)
- Keep the source column **string** on ingest; remember the single-column-CSV `formatType:"csv"→"line"` header-leak trap (`migration/ayx/overview.md` § Single-column TextInput) — `set-schema` to one column can flip the format so the header is read as data. Verify row count after upload.
- `substring(s, from, to)` is from-inclusive / to-exclusive (Java).

### Manual zero-padding macros (TextToColumns + padleft + concat + DateTime)
Alteryx normalizes date strings by splitting → padleft each part → reconcat → parse:
```
TextToColumns(field=date, delim="\s/:", NumFields=5)   # split MM/DD/YYYY HH:MM
Formula: [1]=padleft([1],2,"0"); [2]=padleft([2],2,"0"); [4]=padleft([4],2,"0"); [date]=[1]+"/"+[2]+"/"+[3]+" "+[4]+":"+[5]
AlteryxSelect (drop the 5 split cols)
DateTime(IsFrom=False, format=MM/dd/yyyy hh:mm:ss)
```

**DSS collapse: `DateParser → DateFormatter → DateFormatter` (one Prepare).** `DateFormatter` zero-pads automatically when the pattern uses `MM/dd/yyyy HH:mm` (vs source's `M/d/yyyy H:mm`) — the padleft dance is redundant.
```bash
dku recipe add-step prep --type DateParser --params '{"appliesTo":"SINGLE_COLUMN","columns":["date_time"],"formats":["M/d/yyyy H:mm"],"lang":"auto","timezone_id":"UTC","outCol":"_parsed","outType":{"name":"out","type":"datetimenotz"}}' -P PROJ
dku recipe add-step prep --type DateFormatter --params '{"inCol":"_parsed","outCol":"date_time","format":"MM/dd/yyyy HH:mm","lang":"auto","timezone_id":"UTC"}' -P PROJ      # zero-padded, overwrite source
dku recipe add-step prep --type DateFormatter --params '{"inCol":"_parsed","outCol":"DateTime_Out","format":"yyyy-MM-dd HH:mm:ss","lang":"auto","timezone_id":"UTC"}' -P PROJ  # ISO variant
dku recipe add-step prep --type ColumnsSelector --params '{"appliesTo":"SINGLE_COLUMN","columns":["_parsed"],"keep":false}' -P PROJ    # drop intermediate
```
**4 Alteryx tools → 1 Prepare (4 steps).** `DateFormatter` overwriting the source column is supported (set `outCol` to the existing name).

---

## GenerateRows

**Alteryx:** emits rows from init/condition/loop expressions. Config: `CreateField_Name`, `Expression_Init`, `Expression_Cond`, `Expression_Loop`.

**Dataiku — pick by shape (first ask WHY rows are generated):**

1. **Range join (integer BETWEEN) on SQL** — most common "GenerateRows then Join". Skip the expansion. **Priority: SQL `BETWEEN` > Prepare `ColumnSplitter`+`forRange`+`ArrayFold` then equi-Join > cross-join+filter > Python.**
   ```sql
   SELECT c.*, r.* FROM customers c JOIN ranges r ON c.postal_area BETWEEN r.start AND r.end
   ```
   Or a visual Join: **`create-join --join-key` accepts inequality operators** — `BETWEEN` is two keys: `-k 'postal_area>=start' -k 'postal_area<=end'` (GTE+LTE conditions, left side = first input's column). Works off-SQL too; no CROSS+filter detour.

2. **Prepare-only expansion (visual, any connection)** — `ColumnSplitter` → `CreateColumnWithGREL` (`forRange`) → `ArrayFold`:
   ```json
   {"type":"ColumnSplitter","params":{"inCol":"Range","separator":"-","outColPrefix":"part","target":"COLUMNS","keepEmptyChunks":false,"limitOutput":false,"limit":0}}
   {"type":"CreateColumnWithGREL","params":{"expression":"forRange(-1, part1 - part0, 1, v, part0 + v + 1)","column":"Area"}}
   {"type":"ArrayFold","params":{"column":"Area"}}
   ```
   Downstream: equi-join `customers.Postal Area = ranges_expanded.Area`, then group. `ColumnSplitter` auto-types `part0`/`part1` `bigint` — no `toNumber`/`set-schema`. For date spines: swap the middle step for `forRange(-1, diff(end,start), 1, v, v+1)` + a trailing `CreateColumnWithGREL` `computeDate(start, offset, "day")`. `ArrayUnfold` is the sibling (expands to columns, not rows) — pick `ArrayFold` for row expansion.

3. **No-Prepare fallback (pure visual)** — Cross-join → Filter → Group. Four recipes:
   1. Prepare: numeric `Start`,`End` via `toNumber(split(Range,"-")[0])` / `[1]` (`add-formula`) — `toNumber()` types output `bigint`; `numval(expr, default)` does NOT work (takes a quoted column name, not an expression).
   2. Join `-j CROSS`: customers × ranges_prep.
   3. `create-filter` on the cross product. Reference space-containing columns with `numval("Postal Area")` / `strval(...)` — backticked `` `Postal Area` `` is rejected (`ParsingException at offset 0`).
   4. `create-group --no-global-count` with `--agg 'Customer ID:count'`.

4. **Expand-then-COUNT (no join)** — loop feeds a `Filter → Summarize(count)` to count days/events in `[start,end]`. **Do not expand** — nothing to join, so `ArrayFold`/`BETWEEN` don't apply. Closed-form arithmetic in one Prepare. Weekday/business-day counts: `DateParser` both ends → `serial(d)=diff(d, asDateOnly("<Monday-before-data>","yyyy-MM-dd"), "days")` (positive serial dodges `datePart(dow)` numbering + negative-mod) → `round(W(serial(end)+1) - W(serial(start)))` with `W(n)=5*floor(n/7)+min(n-7*floor(n/7),5)`. Anchor to a Monday earlier than every date so serials stay positive.

4b. **Expand-then-reduce, NON-additive aggregate** (factorial / cumulative product): cross-join against a small integer-sequence helper dataset, `--pre-filter 'i <= Number'` on the Group, product via log-sum-exp — `ln_i=ln(i)` computed column + `--agg ln_i:sum`, downstream `round(exp(ln_i_sum))`. DSS Group has no `product` aggregate. 3 recipes (CROSS → Group → Prepare), no Python.

5. **Chunk a range into fixed-size batches (box-packing) — `forRange` + `ArrayFold`, NOT a loop.** An iterative/batch macro (`GenerateRows` + `MultiRowFormula` walking a counter) splitting each row's `[Start,End]` into boxes of size `B` is **closed-form, one Prepare** — no Python, no numbers-table join. `num_boxes = ceil((End-Start+1)/B)`; box `k` (0-based) covers `[Start+k·B, min(Start+(k+1)·B-1, End)]`.
   ```bash
   dku recipe add-formula pack -P PROJ --column num_boxes --expr 'ceil((EndingBottleID - StartingBottleID + 1) / ${box_size}.0)'   # float div, else ceil no-op
   dku recipe add-step pack -P PROJ -t CreateColumnWithGREL --params '{"column":"box_idx","expression":"forRange(0, num_boxes, 1, v, v)"}'  # [0..num_boxes-1]
   dku recipe add-step pack -P PROJ -t ArrayFold --params '{"column":"box_idx"}'                                                      # one row per box
   dku recipe add-formula pack -P PROJ --column BoxNumberForOrder --expr 'numval("box_idx") + 1'
   dku recipe add-formula pack -P PROJ --column boxStart --expr 'StartingBottleID + numval("box_idx") * ${box_size}'
   dku recipe add-formula pack -P PROJ --column boxEnd   --expr 'min(StartingBottleID + (numval("box_idx")+1) * ${box_size} - 1, EndingBottleID)'
   dku recipe add-formula pack -P PROJ --column BottlesInThisBatch --expr 'numval("boxEnd") - numval("boxStart") + 1'
   ```
   The batch-size param (macro's `NumericUpDown`) → a **project variable** `${box_size}`; re-running with a different value reproduces each expected output. **Two gotchas:** (a) `forRange(from, to, step, v, expr)` — `to` is EXCLUSIVE, so `forRange(0, num_boxes, …)` emits exactly `num_boxes`. (b) **Reusing an original input-column name inside a Prepare nulls it** — you cannot write box ranges back into `StartingBottleID`/`EndingBottleID` in this recipe; emit new names (`boxStart`/`boxEnd`), rename in a tiny DOWNSTREAM Prepare.

6. **The sequence IS the deliverable (date spine / calendar / number series) — no input, no join, no count** → one small Python recipe (legitimate — pure generation, no visual row-generator exists). Two faithful mappings:
   - **Macro has no input → the recipe needs no input either.** `dku recipe create gen -t python --output-ds OUT --connection filesystem_managed -P PROJ` works with zero `-i` (live-verified: creates, runs, builds). Do NOT wire a 1-row seed dataset — that pattern only generates upload/guard friction.
   - **Macro interface questions → project variables**, read via `dataiku.get_custom_variables()` (e.g. `${start_date}`, `${include_weekends}`). Re-run with different values to reproduce outputs. See `tools-io-apps-ml.md` § Macros.
   - Date spine body: `d = date.fromisoformat(v["start_date"]); while d <= date.today(): … d += timedelta(days=1)`. Day-of-week = `d.strftime("%A")`; weekday-only = `d.weekday() < 5` (Mon=0). **`date.today()`-relative output has no fixed ground truth** — validate by shape: row count = days in range, first = start, last = today, DOW correct, toggle drops Sat/Sun.

7. **Dynamic loop (arbitrary init/cond/loop)** → Python, only when none of 1–6 applies.

8. **Cartesian product across two datasets** → Join `type: CROSS`, or SQL `CROSS JOIN`.

**Caveats:** row expansion can blow up. Check `count(ranges) * max(End - Start)` before option 2, or `count(customers) * count(ranges)` for option 3 — pair with a SQL engine for large tables.

---

## JSONParse

**Alteryx:** parses a JSON column into `JSON_Name` + `JSON_ValueString` tall records, one row per leaf.

**Dataiku Prepare:**
- Flatten-one-level → `UnfoldObject` on the JSON column.
- Tall (one row per leaf) → `UnfoldObject` then a Python recipe to melt, or `JSON to columns` recipe (if plugin installed).
- Deep/irregular → Python with `json.loads` + `pandas.json_normalize`.
