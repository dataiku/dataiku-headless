# Prepare Processors Reference

Pick a purpose-built processor over `CreateColumnWithGREL` (GREL is last resort). Insert with
`dku recipe add-step RECIPE --type <Processor> --params '<JSON>' -P PROJ` (`--at N` to insert at
index). Sugar commands exist (`add-rename`, `add-delete-columns`, `add-reorder`, `add-fill-empty`,
`add-find-replace`, `add-filter-rows`, `add-formula`, `add-fold`, `add-geopoint`) — get their flags
from `--help`. Step JSON shape: `{"type":"Processor","params":{…}}`. Prepare does **not** auto-create
its output dataset — create it first.

**Build the whole pipeline at once with `dku recipe apply-spec RECIPE @steps.json -P PROJ`** — a JSON
array where each entry is either an `op` mirroring a sugar command
(`{"op":"formula","column":"total","expr":"price*qty"}`; ops: formula, rename, filter-rows,
fill-empty, delete-columns, reorder, find-replace, fold, geopoint, geodistance) or a raw
`{"type":"Processor","params":{…}}` for the processors below. Entries take optional `"name"` and
`"disabled":true`. Appends by default; `--replace` rebuilds. The batch is validated before any save.
This is the preferred path; use the single `add-*` commands only to iterate one step or `--at`-insert.

## Shared params

- `appliesTo` — `SINGLE_COLUMN` | `COLUMNS` | `ALL` | `PATTERN`. **Required** on scoped processors;
  omitting it silently no-ops several of them (notably `ColumnReorder`).
- `columns` — array of column names. Use this (not GREL refs) for **column names with spaces**.
- `booleanMode` — `AND` | `OR` when multiple columns are scoped.
- DSS **silently ignores unknown param keys** → a wrong field name produces an accepted-but-no-op step.

## Columns: rename / select / reorder / copy / concat / fill

| Processor | When | Params payload |
|---|---|---|
| `ColumnRenamer` | rename cols | `{"renamings":[{"from":"Old","to":"new"}]}` |
| `ColumnsSelector` | keep/drop cols | `{"appliesTo":"COLUMNS","columns":["a","b"],"keep":false}` — `keep:true` does NOT reorder |
| `ColumnReorder` | force col order | `{"appliesTo":"COLUMNS","columns":["a"],"reorderAction":"AT_THE_BEGINNING","referenceColumn":""}` (`AT_THE_END`/`BEFORE_COLUMN`/`AFTER_COLUMN`; set `referenceColumn` for the latter two). `appliesTo` **required** or silent no-op. Run `apply-schema` after. |
| `ColumnCopier` | duplicate a col | `{"inputColumn":"status","outputColumn":"status_bak"}` (GREL-ref based → no spaces) |
| `ColumnsConcat` | join cols w/ delimiter | `{"columns":["first","last"],"join":" ","outputColumn":"full_name"}` |
| `FillEmptyWithValue` | fill nulls only | `{"appliesTo":"SINGLE_COLUMN","columns":["age"],"value":"0"}` |
| `FillColumn` | set EVERY row | `{"column":"c","value":"X"}` — overwrites non-nulls too (use FillEmpty to fill nulls only) |
| `Coalesce` | first non-null | `add-step --type Coalesce` |

## Strings / numbers

| Processor | When | Params payload |
|---|---|---|
| `StringTransformer` | upper/lower/trim/normalize/truncate | `{"mode":"TO_UPPER","appliesTo":"SINGLE_COLUMN","columns":["city"]}` — modes: `TO_UPPER`/`TO_LOWER`/`TRIM`/`NORMALIZE`/`TRUNCATE` (`truncate_limit` int when TRUNCATE). `UPPERCASE`/`TITLECASE` invalid → NPE at build. Title case = GREL `toTitlecase`. |
| `FindReplace` | replace values | `{"appliesTo":"SINGLE_COLUMN","columns":["cat"],"output":"","mapping":[{"from":"X","to":"Y"}],"matching":"FULL_STRING","normalization":"EXACT"}` (matching: `FULL_STRING`/`SUBSTRING`/`PATTERN`) |
| `ColumnSplitter` | split by delimiter | `{"inCol":"name","separator":" ","outColPrefix":"name_","target":"COLUMNS","keepEmptyChunks":false,"limitOutput":false,"limit":0,"startFrom":"beginning"}` — `startFrom` lowercase, required when `limitOutput:true` |
| `RegexpExtractor` | extract by regex | `{"inCol":"desc","output":"out","pattern":"(\\d{3})","groupNum":1,"caseSensitive":false}` (`groupNum` 0=full match). **Multi-group patterns** (`{"column":"line","pattern":"<N groups>","extractAllOccurrences":false}`) name outputs by BARE group index `"1"`…`"N"`, NOT `<col>_1` — renaming `line_1` silently no-ops; rename `"1"`→`name` etc. One anchored pattern with a group per field = a one-step fixed-width/whole-line parser. |
| `RoundProcessor` | round to N decimals | `{"appliesTo":"SINGLE_COLUMN","columns":["price"],"decimalPlaces":2}` (GREL `round()` is integer-only) |
| `BinnerProcessor` | discretize into bins | `{"input":"age","output":"age_group","mode":"WIDTH","width":10.0,"bins":[]}` — `mode:CUSTOM` uses `bins:[{"inf":0,"sup":25}]` |
| `NumericalFormatConverter` | FR↔US numerals | `{"appliesTo":"SINGLE_COLUMN","columns":["p"],"outCol":"p_us","inFormat":"FR","outFormat":"US"}` (`FR`/`US`/`RAW`) |
| `ExtractNumbers` | numbers from text | `{"input":"desc","output":"amts","multipleValues":true,"replaceMultipliers":true,"extractToJson":true}` |
| `TextSimplifierProcessor` | NLP normalize/stem | `{"inCol":"d","outCol":"d_clean","normalize":true,"stem":false,"clearStopWords":true,"sortAlphabetically":false,"language":"english"}` |
| `MinMaxProcessor` | clip range | params `lowerBound`/`upperBound`/`clear` (NOT min/max/action) |

## Dates / time

Parse a string into a real date **before** formatting/truncating/extracting. Java `SimpleDateFormat`
patterns; use `Z`/`z` for ISO-8601 timezone, NOT `XXX`.

| Processor | When | Params payload |
|---|---|---|
| `DateParser` | string → date | `{"appliesTo":"SINGLE_COLUMN","columns":["d"],"formats":["yyyy-MM-dd"],"lang":"auto","timezone_id":"UTC","outCol":"d_parsed","outType":{"name":"out","type":"date"}}` — `outType.type`: `date`/`dateonly`/`datetimenotz`. **Always set `outCol`** — in-place silently yields all nulls. List shortest-year patterns (`yy` before `yyyy`, `d` before `dd`) first. |
| `DateFormatter` | date → custom string | `{"inCol":"parsed","outCol":"label","format":"MMM yyyy","lang":"en_US","timezone_id":"UTC"}` — `inCol`/`outCol`, NOT `column`/`outputColumn` (wrong names → misleading "Empty column name"). Output type STRING. |
| `DateTruncate` | floor to unit | `{"inCol":"parsed","outCol":"month_start","datePart":"MONTH"}` — `datePart` `YEAR`/`MONTH`/`DAY` UPPERCASE. **`HOUR`/`MINUTE`/`SECOND` fail the build** ("Unexpected date part: HOUR"); missing/misspelled → silently defaults `YEAR`. Keeps date type. |
| `UNIXTimestampParser` | epoch → date | `{"inCol":"ts","outCol":"d","milliseconds":false}` — `milliseconds` is a BOOLEAN (`"unit":"SECONDS"` ignored; default seconds) |
| `DateComponentsExtractor` | year/month/day/… | `{"column":"d","timezone_id":"UTC","outYearColumn":"y","outMonthColumn":"m","outDayColumn":"dd"}` — also `outHourColumn`/`outDayOfWeekColumn`/`outWeekOfYearColumn` |
| `DateDifference` | time between dates | `{"input1":"signup","compareTo":"NOW","output":"days","outputUnit":"DAYS","timezone_id":"UTC"}` — `compareTo`: `COLUMN`(+`input2`)/`DATE`(+`refDate`)/`NOW`; unit `DAYS`/`WEEKS`/`MONTHS` |
| `DateIncrement` | add a delta | `{"inCol":"d","outCol":"d2","datePart":"YEAR","incrementBy":"STATIC","increment":5}` — `incrementBy:COLUMN` reads per-row `incrementCol` |
| `FilterOnDate` | keep/remove by range | `{"appliesTo":"SINGLE_COLUMN","columns":["d"],"filterType":"RANGE","min":"2024-01-01T00:00:00.000Z","max":"2024-12-31T23:59:59.000Z","action":"KEEP_ROW","timezone_id":"UTC","includeEmptyValues":false}` |

Timezone-only date: DateParser converts to UTC first; use `timezone_id:"use_preferred_timezone"` to
keep the source-tz calendar date. Timestamp→date-only = `DateParser` with `outType:dateonly` (one step).
GREL `formatDate()`/`toDate()` don't exist; `toString(date,"fmt")` is a no-op — use processors.

## Filters / flags

`FilterOn*` actions remove/keep rows (or clear cells); `FlagOn*` write a boolean column (`action:"FLAG"` + `flagColumn`). Same condition families, different effect.

| Processor | When | Params payload |
|---|---|---|
| `FilterOnCustomFormula` | filter/clear by formula | `{"expression":"age > 65","action":"REMOVE_ROW"}` — `KEEP_ROW`/`REMOVE_ROW`/`CLEAR_CELL`(+`clearColumn`). Use this, NOT `FilterOnFormula` (plugin type → `UnavailableTypeException`) |
| `FilterOnBadType` | drop wrong-type rows | `{"appliesTo":"SINGLE_COLUMN","columns":["price"],"action":"REMOVE_ROW","type":"DoubleMeaning","considerEmptyAsInvalid":false,"booleanMode":"AND"}` — types: `DoubleMeaning`/`LongMeaning`/`Date`/`Boolean`/`Email`/`URL`/`IPAddress` |
| `FilterOnNumericalRange` | keep/remove by range | `{"appliesTo":"SINGLE_COLUMN","columns":["age"],"action":"KEEP_ROW","min":18.0,"max":65.0,"booleanMode":"AND"}` |
| `RemoveRowsOnEmpty` | drop empty rows | `{"appliesTo":"ALL","columns":[],"keep":false}` (`keep:true` keeps only empty) |
| `FlagOnValue` | flag/filter by value set | `{"appliesTo":"SINGLE_COLUMN","columns":["status"],"values":["active"],"action":"FLAG","flagColumn":"is_active","matchingMode":"FULL_STRING","normalizationMode":"EXACT","booleanMode":"AND"}` (`action` also `KEEP_ROW`/`REMOVE_ROW`) |
| `FlagOnNumericalRange` | flag in [min,max] | `{"appliesTo":"SINGLE_COLUMN","columns":["v"],"min":-5.0,"max":5.0,"action":"FLAG","flagColumn":"idle","booleanMode":"AND","includeEmptyValues":false}` |
| `FlagOnDate` | flag in date range | `{"appliesTo":"SINGLE_COLUMN","columns":["d"],"filterType":"RANGE","min":"2024-01-01T00:00:00.000","max":"2024-12-31T00:00:00.000","action":"FLAG","flagColumn":"in_2024","timezone_id":"UTC","booleanMode":"AND","includeEmptyValues":false}` |
| `FlagOnBadType` / `FlagOnCustomFormula` | flag by type / formula | type: like FilterOnBadType + `action:"FLAG"`. formula: `{"expression":"val(\"amount\") > 100","action":"FLAG","flagColumn":"high"}` (quote col in `val`/`numval`/`strval`) |
| `VisualIfRule` | if/then/else branches | see below |
| `UpDownFiller` | LOCF/NOCB impute | `{"appliesTo":"SINGLE_COLUMN","columns":["v"],"direction":"DOWN"}` (`UP`) |

### VisualIfRule

`{"legacyPositioning":false,"visualIfDesc":{"ifThen":{filter,actions},"elseIfThens":[…],"elseActions":[…]}}`
- **filter**: `{"uiData":{"mode":"&&","conditions":[…]},"distinct":true,"enabled":true}`
- **condition**: `{"input":"col","col":"","operator":"…","string":"","num":0.0,"num2":0.0}` — `input`=tested col; `col`=other-column name for `== [column]`; `string`/`num` = literals.
- **action**: `{"outputColumnName":"tier","column":"","formula":"","value":"HIGH","operator":"ASSIGN_VALUE"}` (`ASSIGN_COLUMN`→`column`, `ASSIGN_FORMULA`→`formula`).
- Operators (exact strings, note spacing): `is empty`, `not empty`, `== [string]`, `!= [string]`, `contains`, `not contains`, `== [number]`, `!= [number]`, `>  [number]`, `<  [number]`, `>= [number]`, `<= [number]`, `== [column]`, `true`, `false`.
- **Broken via API (silent False)**: `regex`, `in [string]`, `not in [string]`, date/geo operators → use GREL: regex `if(length(match(c, /pat/)) > 0,…)`, set-membership `switch(c,"a","M","b","M","NO")`.

## Reshape / JSON / arrays / geo (stock processors — avoid same-named plugin variants)

| Processor | When | Params payload |
|---|---|---|
| `MultiColumnFold` | wide→long (melt) | `{"columns":["jan","feb"],"foldNameColumn":"month","foldValueColumn":"sales","foldRemoveFoldedColumns":true}` |
| `MultiColumnByPrefixFold` | fold by name regex | `{"columnNamePattern":"score_.*","columnNameColumn":"metric","columnContentColumn":"value","foldRemoveFoldedColumns":true}` |
| `Unfold` | long→wide spread | `{"column":"trucks","prefix":"truck_","limit":10,"overflowAction":"ERROR"}` (`TRUNCATE` drops overflow) |
| `JSONFlattener` | flatten JSON col | `{"inCol":"meta","flattenArrays":false,"maxDepth":10,"nullAsEmpty":true,"prefixOutputs":true,"separator":"_"}` |
| `ArrayUnfold` | explode array→rows | `{"column":"tags","keepEmptyArrays":false,"delete":true,"countVal":true}` (`countVal` emits `<col>_count`; legacy `appendCount` ignored) |
| `ArraySortProcessor` | sort array | `{"input":"arr","sortingType":"NUM","descending":true}` (NOT `column`/`order`) |
| `MemoryEquiJoiner` | in-Prepare lookup join | `{"leftCol":"code","rightCol":"iso2","rightInput":"lookup_ds","copyColumns":["name"],"copyPrefix":"l_"}` (`fuzzy:true`+`maxLevenshtein` for fuzzy) |
| `GeoPointCreator` | lat/lon → GeoPoint | `{"lat_column":"lat","lon_column":"lon","out_column":"geopoint"}` (WKT POINT, EPSG:4326) |
| `GeometryInfoExtractor` | centroid/area | `{"inputCol":"the_geom","centroidCol":"centroid","areaCol":"area"}` |
| `CityLevelReverseGeocoder` | point → admin levels | `{"inputCol":"centroid","l4OutCol":"country","l6OutCol":"region","l8OutCol":"city"}` |
| `ZipCodeGeocoder` | (country,zip) → point | `{"countryCol":"country","zipCodeCol":"zip","outputCol":"centroid"}` |
| `GeoIPResolver` | IP → location | `inCol`/`outColPrefix` + boolean `extract_*` toggles (NOT `inputColumn`/`outputColumn`) |

## Inline code (last resorts inside Prepare)

| Processor | When | Params payload |
|---|---|---|
| `CreateColumnWithGREL` | formula (no processor fits) | `{"expression":"if(price>100,'premium','standard')","column":"tier"}` — check a dedicated processor first. New cols default STRING → run `apply-schema`. |
| `PythonUDF` | inline row/cell Python | `{"mode":"ROW","pythonSourceCode":"def process(row):\n    …\n    return row","envSelection":{"envMode":"INHERIT"},"stopOnError":false}` — CELL mode needs `column`; missing `mode` = no-op. Row-local only (no joins/aggregations). |
| `EnrichWithBuildContextProcessor` | stamp build timestamp | `{"buildDateColumn":"build_ts"}` |

**In-place cast doesn't retype.** A GREL formula overwriting an EXISTING column (e.g. `price = price * 1.0`) keeps the column's declared storage type (stays `string`) — DSS only re-infers types for **new** output columns. A manual `dku dataset set-schema` fix is reverted by the next `--auto-update-schema` rebuild. The only clean route is writing to a **new** output column (which infers the type).

**Writing back under an original input-column name silently NULLs it.** Inside one Prepare, deleting/renaming a temp column TO a name the INPUT schema already owns — or overwriting an input column via a GREL step — produces an all-null column, no error (the engine binds the name to the input column, which the earlier step removed). Emit computed values under NEW names; rename to the final names in a tiny downstream Prepare. (`DateParser` without `outCol` is the same trap, called out in its row.)

## Engine-bound processors — succeed but do nothing on the DSS engine

These need an in-database (SQL) or Spark engine. On the default DSS streaming
engine (any Filesystem/Upload-backed flow) the build **exits 0 with wrong
output** — no warning anywhere. Always `head` the output.

| Processor | Params payload | On DSS engine |
|---|---|---|
| `ComputeNTile` | `{"appliesTo":"SINGLE_COLUMN","columns":["amount"],"n":4,"outCol":"amount_q"}` — `outCol` honored only under `SINGLE_COLUMN` | output column **all null** |
| `MergeLongTailValues` | `{"appliesTo":"SINGLE_COLUMN","columns":["cat"],"thresholdMode":"COUNT","countThreshold":2,"replacementValue":"OTHER"}` — `thresholdMode` `COUNT`(+`countThreshold`) or `CUM_RATIO`(+`cumRatioThreshold` 0–1) | rows pass through **unchanged** |

## Column names with spaces

Processors taking column names in `columns[]`/`inCol` work with spaces (`DateParser`, `StringTransformer`,
`FindReplace`, `ColumnsSelector`, `ColumnRenamer`, `ColumnsConcat`, filters/flags, …). GREL-ref-based
processors (`CreateColumnWithGREL`, `ColumnCopier`, `VisualIfRule`, `FilterOnCustomFormula`) silently
return null on spaced names — rename to remove spaces first, or use a Python recipe.

## GREL gotchas (when a formula is unavoidable)

- `round(x,2)` → silent empty (1-arg only); use `round(x*100)/100`.
- `log()` is base-10; natural log = `ln()`.
- `numval(col)` bareword → empty; use `numval("col")` or bare `col` arithmetic.
- `asDateOnly()` on a STRING col silently fails — parse with `DateParser` first.
