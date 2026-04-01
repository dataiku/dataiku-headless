# Prepare Recipe Processors

## Golden Rule

**ALWAYS prefer a purpose-built processor over `CreateColumnWithGREL`.** GREL formulas are the last resort — use only when no dedicated processor handles the operation.

Purpose-built processors are faster (native Java), produce cleaner step lists, and don't require GREL syntax knowledge. When chaining prepare steps, mix shortcuts and `add-step` freely.

## Processor Decision Table

Before writing a GREL formula, check this table:

| Need to... | Processor | CLI |
|------------|-----------|-----|
| Rename columns | `ColumnRenamer` | `add-rename --from old --to new` |
| Delete/keep columns | `ColumnsSelector` | `add-delete-columns --columns "c1,c2"` |
| Copy a column | `ColumnCopier` | `add-step --type ColumnCopier` |
| Fill nulls/blanks | `FillEmptyWithValue` | `add-fill-empty --column col --value "0"` |
| Concatenate columns | `ColumnsConcat` | `add-step --type ColumnsConcat` |
| Uppercase/lowercase/trim | `StringTransformer` | `add-step --type StringTransformer` |
| Find & replace text | `FindReplace` | `add-find-replace --column col --find X --replace Y` |
| Split column by delimiter | `ColumnSplitter` | `add-step --type ColumnSplitter` |
| Normalize/stem/stop-words | `TextSimplifierProcessor` | `add-step --type TextSimplifierProcessor` |
| If/then/else branching | `VisualIfRule` | `add-step --type VisualIfRule` |
| Filter rows by value | `FlagOnValue` | `add-filter-rows --column col --values "a,b"` |
| Filter rows by formula | `FilterOnCustomFormula` | `add-filter-rows --formula "price > 100"` |
| Remove invalid-type rows | `FilterOnBadType` | `add-step --type FilterOnBadType` |
| Filter by numeric range | `FilterOnNumericalRange` | `add-step --type FilterOnNumericalRange` |
| Remove empty rows | `RemoveRowsOnEmpty` | `add-step --type RemoveRowsOnEmpty` |
| Parse date strings | `DateParser` | `add-step --type DateParser` |
| Extract year/month/day | `DateComponentsExtractor` | `add-step --type DateComponentsExtractor` |
| Compute date difference | `DateDifference` | `add-step --type DateDifference` |
| Bin/discretize numbers | `BinnerProcessor` | `add-step --type BinnerProcessor` |
| Clip numeric range | `MinMaxProcessor` | `add-step --type MinMaxProcessor` |
| Fold wide→long | `FoldColumnsByName` | `add-fold --columns "c1,c2" --key-column k --value-column v` |
| Flatten JSON column | `JSONFlattener` | `add-step --type JSONFlattener` |
| Extract from JSON array | `ArrayExtractProcessor` | `add-step --type ArrayExtractProcessor` |
| Create geopoint | `GeoPointCreator` | `add-geopoint --lat-column lat --lon-column lon` |
| Compute geo distance | `GeoDistanceProcessor` | `add-geodistance --from-column A --to-column B` |
| Custom expression (LAST RESORT) | `CreateColumnWithGREL` | `add-formula --expr "..." --column col` |

## Shared Param Patterns

Many processors share these param groups. Learn them once, apply everywhere.

### Scope Params (`appliesTo` / `columns`)

Controls which columns a processor targets:

| Param | Values | Notes |
|-------|--------|-------|
| `appliesTo` | `SINGLE_COLUMN`, `COLUMNS`, `ALL`, `PATTERN` | How to select target columns |
| `columns` | `["col1", "col2"]` | Always an array, even for single column |
| `appliesToPattern` | `".*_date"` | Required when `appliesTo = PATTERN` |

Used by: DateParser, FilterOnBadType, FlagOnValue, FillEmptyWithValue, ColumnsSelector, RemoveRowsOnEmpty, StringTransformer, FindReplace.

### Action Param

Controls what happens to matching rows:

| Value | Effect |
|-------|--------|
| `KEEP_ROW` | Keep matching rows, remove others |
| `REMOVE_ROW` | Remove matching rows |
| `CLEAR_CELL` | Clear cell value (requires `clearColumn`) |
| `FLAG` | Create a flag column with 1 for matches |

Used by: FlagOnValue, FilterOnCustomFormula, FilterOnBadType, FilterOnNumericalRange.

### Timezone Params

| Param | Values |
|-------|--------|
| `timezone_id` | `"UTC"`, `"Europe/Paris"`, any IANA timezone, or `"use_preferred_timezone"` |
| `timezone_src` | Column name (required when `timezone_id = "extract_from_column"`) |

Used by: DateParser, DateComponentsExtractor, DateDifference, FlagOnDate.

---

## Processor Reference

Each entry: type ID, when to use, key params, canonical JSON for `add-step --params`.

---

### ColumnRenamer

**When:** Rename one or more columns. Prefer over GREL workarounds.
**CLI shortcut:** `dku recipe add-rename RECIPE --from old --to new -P PROJ` or `--mappings '{"old":"new"}'`

| Param | Required | Description |
|-------|----------|-------------|
| `renamings` | Yes | Array of `{"from": "old", "to": "new"}` objects |

```json
{"renamings": [{"from": "CustomerName", "to": "customer_name"}, {"from": "OrderDate", "to": "order_date"}]}
```

---

### ColumnsSelector

**When:** Delete or keep specific columns. Prefer over GREL.
**CLI shortcut:** `dku recipe add-delete-columns RECIPE --columns "tmp1,tmp2" -P PROJ`

| Param | Required | Description |
|-------|----------|-------------|
| `appliesTo` | Yes | `COLUMNS` |
| `columns` | Yes | Array of column names |
| `keep` | Yes | `false` = delete listed, `true` = keep only listed |

```json
{"appliesTo": "COLUMNS", "columns": ["debug_col", "temp_id"], "keep": false}
```

---

### ColumnCopier

**When:** Copy a column's values to a new column. Prefer over GREL `column_name` identity expression.

| Param | Required | Description |
|-------|----------|-------------|
| `inputColumn` | Yes | Source column |
| `outputColumn` | Yes | New column name |

```json
{"inputColumn": "status", "outputColumn": "status_backup"}
```

---

### FillEmptyWithValue

**When:** Fill null/blank cells with a default value. Prefer over GREL `if(isBlank(x), "0", x)`.
**CLI shortcut:** `dku recipe add-fill-empty RECIPE --column age --value "0" -P PROJ`

| Param | Required | Description |
|-------|----------|-------------|
| `appliesTo` | Yes | `SINGLE_COLUMN` |
| `columns` | Yes | `["col_name"]` |
| `value` | Yes | Fill value (string) |

```json
{"appliesTo": "SINGLE_COLUMN", "columns": ["age"], "value": "0"}
```

---

### ColumnsConcat

**When:** Concatenate multiple columns with a delimiter. Prefer over GREL `col1 + " " + col2`.

| Param | Required | Description |
|-------|----------|-------------|
| `columns` | Yes | Input columns in order |
| `join` | Yes | Delimiter string (can be empty) |
| `outputColumn` | Yes | Output column name |

```json
{"outputColumn": "full_address", "columns": ["street", "city", "state"], "join": ", "}
```

---

### StringTransformer

**When:** Uppercase, lowercase, or trim text. Prefer over GREL `upper()`, `lower()`, `trim()`.

| Param | Required | Description |
|-------|----------|-------------|
| `mode` | Yes | `UPPERCASE`, `LOWERCASE`, `TITLECASE`, `TRIM`, `NORMALIZE` |
| `appliesTo` | Yes | Scope (see shared params) |
| `columns` | Yes | `["col_name"]` |

```json
{"mode": "UPPERCASE", "appliesTo": "SINGLE_COLUMN", "columns": ["city"]}
```

---

### FindReplace

**When:** Find and replace values in a column. Prefer over GREL `replace()`.
**CLI shortcut:** `dku recipe add-find-replace RECIPE --column city --find "NYC" --replace "New York" -P PROJ`

| Param | Required | Description |
|-------|----------|-------------|
| `appliesTo` | Yes | `SINGLE_COLUMN` |
| `columns` | Yes | `["col_name"]` |
| `mapping` | Yes | Array of `{"from": "old", "to": "new"}` |
| `matching` | Yes | `FULL_STRING`, `SUBSTRING`, `PATTERN` (regex) |
| `normalization` | Yes | `EXACT`, `LOWERCASE`, `NORMALIZED` |
| `output` | Yes | `""` (in-place) or output column name |

```json
{"appliesTo": "SINGLE_COLUMN", "columns": ["category"], "output": "", "mapping": [{"from": "Electronics", "to": "Tech"}], "matching": "FULL_STRING", "normalization": "EXACT"}
```

---

### ColumnSplitter

**When:** Split a column by delimiter into multiple columns. Prefer over GREL `split()`.

| Param | Required | Description |
|-------|----------|-------------|
| `inCol` | Yes | Input column |
| `separator` | Yes | Delimiter string |
| `outColPrefix` | Yes | Prefix for generated columns (e.g. `name_0`, `name_1`) |
| `target` | Yes | `COLUMNS` (separate cols) or `JSON` (JSON array) |
| `keepEmptyChunks` | Yes | `false` = skip empty |
| `limitOutput` | Yes | `true` = limit to N chunks |
| `limit` | Yes | Max chunks (0 = unlimited) |

```json
{"inCol": "full_name", "separator": " ", "outColPrefix": "name_", "target": "COLUMNS", "keepEmptyChunks": false, "limitOutput": false, "limit": 0}
```

---

### TextSimplifierProcessor

**When:** Normalize text with stemming, stop-word removal, and sorting. For NLP preprocessing.

| Param | Required | Description |
|-------|----------|-------------|
| `inCol` | Yes | Input text column |
| `outCol` | No | Output column (empty = in-place) |
| `normalize` | Yes | Lowercase + remove punctuation/accents |
| `stem` | Yes | Language-specific stemming |
| `clearStopWords` | Yes | Remove stop words |
| `sortAlphabetically` | Yes | Sort tokens alphabetically |
| `language` | Yes | `english`, `french`, `german`, `spanish`, etc. |

```json
{"inCol": "description", "outCol": "description_clean", "normalize": true, "stem": false, "clearStopWords": true, "sortAlphabetically": false, "language": "english"}
```

---

### VisualIfRule

**When:** If/then/else branching logic. Prefer over GREL `if(condition, then, else)` — especially for multiple branches.

| Param | Required | Description |
|-------|----------|-------------|
| `legacyPositioning` | Yes | Always `false` for new steps |
| `visualIfDesc.ifThen` | Yes | Primary IF branch: `{filter, actions}` |
| `visualIfDesc.elseIfThens` | No | Additional ELSE IF branches (array) |
| `visualIfDesc.elseActions` | No | ELSE actions (array) |

Each branch has a `filter` (visual condition) and `actions` (output assignments):
- **Filter:** `{"uiData": {"mode": "&&", "conditions": [{"input": "col", "operator": ">  [number]", "num": 30}]}, "distinct": true, "enabled": true}`
- **Action:** `{"outputColumnName": "result", "value": "high", "operator": "ASSIGN_VALUE"}`

Common operators: `== [string]`, `!= [string]`, `>  [number]`, `<  [number]`, `contains`, `is empty`, `not empty`.

```json
{
  "legacyPositioning": false,
  "visualIfDesc": {
    "ifThen": {
      "filter": {"uiData": {"mode": "&&", "conditions": [{"input": "age", "operator": ">  [number]", "num": 65}]}, "distinct": true, "enabled": true},
      "actions": [{"outputColumnName": "age_group", "value": "senior", "operator": "ASSIGN_VALUE"}]
    },
    "elseIfThens": [
      {
        "filter": {"uiData": {"mode": "&&", "conditions": [{"input": "age", "operator": ">  [number]", "num": 18}]}, "distinct": true, "enabled": true},
        "actions": [{"outputColumnName": "age_group", "value": "adult", "operator": "ASSIGN_VALUE"}]
      }
    ],
    "elseActions": [{"outputColumnName": "age_group", "value": "minor", "operator": "ASSIGN_VALUE"}]
  }
}
```

---

### FlagOnValue

**When:** Filter/flag rows matching specific values. Prefer over GREL `if(col == "x", ...)`.
**CLI shortcut:** `dku recipe add-filter-rows RECIPE --column status --values "active,pending" --action KEEP_ROW -P PROJ`

| Param | Required | Description |
|-------|----------|-------------|
| `appliesTo` | Yes | `SINGLE_COLUMN` |
| `columns` | Yes | `["col_name"]` |
| `values` | Yes | Array of values to match |
| `action` | Yes | `KEEP_ROW`, `REMOVE_ROW`, `FLAG` |
| `matchingMode` | Yes | `FULL_STRING`, `SUBSTRING`, `PATTERN` |
| `normalizationMode` | Yes | `EXACT`, `LOWERCASE`, `NORMALIZED` |
| `booleanMode` | Yes | `AND` or `OR` |

```json
{"appliesTo": "SINGLE_COLUMN", "columns": ["status"], "values": ["active", "pending"], "action": "KEEP_ROW", "matchingMode": "FULL_STRING", "normalizationMode": "EXACT", "booleanMode": "AND"}
```

---

### FilterOnCustomFormula

**When:** Filter rows or clear cells based on a formula expression. Prefer over Python filtering.
**CLI shortcut:** `dku recipe add-filter-rows RECIPE --formula "price > 100" --action REMOVE_ROW -P PROJ`

| Param | Required | Description |
|-------|----------|-------------|
| `expression` | Yes | DSS formula expression |
| `action` | Yes | `KEEP_ROW`, `REMOVE_ROW`, `CLEAR_CELL`, `DONTCLEAR_CELL` |
| `clearColumn` | Cond | Required for `CLEAR_CELL` / `DONTCLEAR_CELL` |

```json
{"expression": "age > 65", "action": "REMOVE_ROW"}
```

Note: Our CLI shortcut uses `FilterOnFormula` internally. Both `FilterOnFormula` and `FilterOnCustomFormula` are valid DSS type names — use `FilterOnCustomFormula` with `add-step` for consistency with DSS UI.

---

### FilterOnBadType

**When:** Remove rows where values don't match expected type (e.g. non-numeric in a number column).

| Param | Required | Description |
|-------|----------|-------------|
| `appliesTo` | Yes | Scope (see shared params) |
| `columns` | Yes | `["col_name"]` |
| `action` | Yes | `REMOVE_ROW`, `KEEP_ROW`, `CLEAR_CELL` |
| `type` | Yes | `DoubleMeaning`, `LongMeaning`, `Date`, `Boolean`, `Email`, `URL`, `IPAddress` |
| `considerEmptyAsInvalid` | Yes | `true`/`false` |
| `booleanMode` | Yes | `AND` |

```json
{"appliesTo": "SINGLE_COLUMN", "columns": ["price"], "action": "REMOVE_ROW", "type": "DoubleMeaning", "considerEmptyAsInvalid": false, "booleanMode": "AND"}
```

---

### FilterOnNumericalRange

**When:** Keep/remove rows where a numeric column is within a range.

| Param | Required | Description |
|-------|----------|-------------|
| `appliesTo` | Yes | `SINGLE_COLUMN` |
| `columns` | Yes | `["col_name"]` |
| `action` | Yes | `KEEP_ROW`, `REMOVE_ROW` |
| `min` | Yes | Lower bound (inclusive) |
| `max` | Yes | Upper bound (inclusive) |
| `booleanMode` | Yes | `AND` |

```json
{"appliesTo": "SINGLE_COLUMN", "columns": ["age"], "action": "KEEP_ROW", "min": 18.0, "max": 65.0, "booleanMode": "AND"}
```

---

### RemoveRowsOnEmpty

**When:** Remove rows with empty/null values.

| Param | Required | Description |
|-------|----------|-------------|
| `appliesTo` | Yes | `SINGLE_COLUMN`, `COLUMNS`, or `ALL` |
| `columns` | Yes | Column(s) to check |
| `keep` | Yes | `false` = remove empty rows, `true` = keep only empty |

```json
{"appliesTo": "ALL", "columns": [], "keep": false}
```

---

### DateParser

**When:** Parse date strings to ISO 8601. Prefer over GREL `toDate()`.

| Param | Required | Description |
|-------|----------|-------------|
| `appliesTo` | Yes | `SINGLE_COLUMN` |
| `columns` | Yes | `["date_col"]` |
| `formats` | Yes | Java date patterns: `["yyyy-MM-dd", "MM/dd/yyyy"]` |
| `lang` | Yes | `"auto"` or locale code (`en_US`, `fr_FR`) |
| `timezone_id` | Yes | `"UTC"`, IANA timezone, etc. |
| `outCol` | No | Output column (omit/empty = parse in-place) |
| `outType` | Yes | `{"name":"out","type":"date"}`, `"dateonly"`, or `"datetimenotz"` |

```json
{"appliesTo": "SINGLE_COLUMN", "columns": ["signup_date"], "formats": ["yyyy-MM-dd"], "lang": "auto", "outType": {"name": "out", "type": "date"}, "timezone_id": "UTC"}
```

---

### DateComponentsExtractor

**When:** Extract year, month, day, hour, etc. from a parsed date column. Prefer over GREL `year()`, `month()`.

| Param | Required | Description |
|-------|----------|-------------|
| `column` | Yes | Input date column (must be parsed ISO-8601) |
| `timezone_id` | Yes | `"UTC"` or IANA timezone |
| `outYearColumn` | No | Output column for year (empty = skip) |
| `outMonthColumn` | No | Output column for month |
| `outDayColumn` | No | Output column for day-of-month |
| `outHourColumn` | No | Output column for hour |
| `outDayOfWeekColumn` | No | Output column for day-of-week |
| `outWeekOfYearColumn` | No | Output column for week-of-year |

```json
{"column": "order_date", "timezone_id": "UTC", "outYearColumn": "order_year", "outMonthColumn": "order_month", "outDayColumn": "order_day"}
```

---

### DateDifference

**When:** Compute time between dates. Prefer over GREL `dateDiff()`.

| Param | Required | Description |
|-------|----------|-------------|
| `input1` | Yes | Primary date column |
| `compareTo` | Yes | `COLUMN`, `DATE`, or `NOW` |
| `input2` | Cond | Second date column (when `compareTo = COLUMN`) |
| `refDate` | Cond | Fixed ISO-8601 date (when `compareTo = DATE`) |
| `output` | Yes | Output column name |
| `outputUnit` | Yes | `DAYS`, `WEEKS`, `MONTHS` |
| `timezone_id` | Yes | `"UTC"` or `"use_preferred_timezone"` |

```json
{"output": "days_since_signup", "input1": "signup_date", "compareTo": "NOW", "outputUnit": "DAYS", "timezone_id": "UTC"}
```

---

### BinnerProcessor

**When:** Discretize numbers into bins (age groups, price ranges). Prefer over GREL `if` chains.

| Param | Required | Description |
|-------|----------|-------------|
| `input` | Yes | Source numeric column |
| `output` | Yes | Output column (empty = in-place) |
| `mode` | Yes | `WIDTH` (fixed width) or `CUSTOM` (manual ranges) |
| `width` | Cond | Bin width (for `WIDTH` mode) |
| `bins` | Cond | Array of `{"inf": 0, "sup": 25}` (for `CUSTOM` mode) |
| `useMin`/`min` | No | Enforce minimum bound |
| `useMax`/`max` | No | Enforce maximum bound |

```json
{"input": "age", "output": "age_group", "mode": "WIDTH", "width": 10.0, "bins": [], "useMin": false, "min": 0.0, "useMax": false, "max": 0.0}
```

---

### FoldColumnsByName / FoldColumnsByPattern

**When:** Unpivot wide-to-long. Prefer over `pd.melt()`.
**CLI shortcut:** `dku recipe add-fold RECIPE --columns "jan,feb,mar" --key-column month --value-column sales -P PROJ`

**FoldColumnsByName:**

| Param | Required | Description |
|-------|----------|-------------|
| `columns` | Yes | Array of column names to fold |
| `keyColumn` | Yes | Output column for original column names |
| `valueColumn` | Yes | Output column for values |

```json
{"columns": ["jan", "feb", "mar"], "keyColumn": "month", "valueColumn": "sales"}
```

**FoldColumnsByPattern** (use `--pattern` flag):

| Param | Required | Description |
|-------|----------|-------------|
| `columnNamePattern` | Yes | Regex matching column names |
| `columnNameColumn` | Yes | Output column for matched names |
| `columnContentColumn` | Yes | Output column for values |

```json
{"columnNamePattern": ".*_2024", "columnNameColumn": "metric", "columnContentColumn": "value"}
```

---

### JSONFlattener

**When:** Flatten JSON object/array columns into separate columns.

| Param | Required | Description |
|-------|----------|-------------|
| `inCol` | Yes | Column containing JSON |
| `flattenArrays` | Yes | Also flatten arrays |
| `maxDepth` | Yes | Max nesting depth to flatten |
| `nullAsEmpty` | Yes | Treat null as empty string |
| `prefixOutputs` | Yes | Prefix output columns with path |
| `separator` | Yes | Separator between nested keys (e.g. `"_"`) |

```json
{"inCol": "metadata", "flattenArrays": false, "maxDepth": 10, "nullAsEmpty": true, "prefixOutputs": true, "separator": "_"}
```

---

### CreateColumnWithGREL

**When:** Custom expressions that no dedicated processor handles. **THIS IS THE LAST RESORT.**
**CLI shortcut:** `dku recipe add-formula RECIPE --expr "upper(city)" --column city_upper -P PROJ`

| Param | Required | Description |
|-------|----------|-------------|
| `expression` | Yes | GREL expression |
| `column` | Yes | Output column name |

```json
{"expression": "if(price > 100, 'premium', 'standard')", "column": "tier"}
```

**Before using this, check:** Could `VisualIfRule`, `StringTransformer`, `DateParser`, `ColumnsConcat`, `BinnerProcessor`, or another processor do this instead?

---

## Full Processor Catalog (Quick Reference)

For processors not covered in detail above, use `add-step --type TYPE --params JSON`. Key params are listed for orientation — verify exact params via `dku recipe get-step` on an existing recipe or DSS documentation.

### Column Operations

| Processor | Type ID | Key Params |
|-----------|---------|------------|
| Reorder columns | `ColumnReorder` | `columns`, `referenceColumn`, `reorderAction` |
| Fill with prev/next | `UpDownFiller` | `column`, `direction` |
| Coalesce (first non-null) | `Coalesce` | `columns`, `outputColumn`, `defaultValue` |

### Numeric

| Processor | Type ID | Key Params |
|-----------|---------|------------|
| Round numbers | `RoundProcessor` | `column`, `precision`, `mode` |
| Force range (clip) | `MinMaxProcessor` | `columns`, `min`, `max`, `action` |
| Convert number format | `NumericalFormatConverter` | `inCol`, `outCol`, `inLocale`, `outLocale` |

### String/Text

| Processor | Type ID | Key Params |
|-----------|---------|------------|
| Extract with regex | `RegexpExtractor` | `column`, `pattern`, `extractAllOccurrences` |
| Tokenize text | `Tokenizer` | `column`, `outputColumn`, `operation` |
| Count occurrences | `MatchCounter` | `input`, `output`, `pattern` |

### Date/Time

| Processor | Type ID | Key Params |
|-----------|---------|------------|
| Format date | `DateFormatter` | `column`, `outputColumn`, `format` |
| Date increment | `DateIncrement` | `column`, `incrementValue`, `incrementUnit` |
| Unix timestamp | `UNIXTimestampParser` | `column`, `unit` (`SECONDS`/`MILLISECONDS`) |
| Flag holidays | `HolidaysComputer` | `column`, `calendar_id`, `flagColumn` |

### Split & Reshape

| Processor | Type ID | Key Params |
|-----------|---------|------------|
| Unfold (long→wide) | `Unfold` | `column` |
| Split and fold | `SplitAndFold` | `column`, `separator` |
| Pivot (in prepare) | `Pivot` | `indexColumn`, `labelsColumn`, `valuesColumn` |
| Transpose | `Transpose` | (no params) |

### JSON & Array

| Processor | Type ID | Key Params |
|-----------|---------|------------|
| Extract from array | `ArrayExtractProcessor` | `column`, `index` |
| Fold array to rows | `ArrayFold` | `column` |
| Sort array | `ArraySortProcessor` | `column`, `order` |
| JSONPath extract | `JSONPathExtractor` | `column`, `expression`, `outputColumn` |
| Nest columns to JSON | `NestColumns` | `columns`, `outputColumn`, `outputType` |
| Zip arrays | `ZipArrays` | `columns`, `outputColumn` |
| Concat arrays | `ConcatArrays` | `columns`, `outputColumn` |

### Joins & Enrichment (in Prepare)

| Processor | Type ID | Key Params |
|-----------|---------|------------|
| Join with dataset | `MemoryEquiJoiner` | `leftCol`, `rightCol`, `rightInput`, `copyColumns` |
| Fuzzy join | `FuzzyJoiner` | `leftCol`, `rightCol`, `rightInput`, `maxLevenshtein` |

### Geo

| Processor | Type ID | Key Params |
|-----------|---------|------------|
| Geo point buffer | `GeoPointBufferProcessor` | `column`, `radius`, `unit` |
| Reverse geocode | `ReverseGeocoder` | `column`, `outputColumn` |
| Change CRS | `ChangeCRSProcessor` | `column`, `inputCRS`, `outputCRS` |

### Web & Misc

| Processor | Type ID | Key Params |
|-----------|---------|------------|
| Split URL | `URLSplitter` | `column` |
| User agent parser | `UserAgentClassifier` | `column` |
| Currency converter | `CurrencyConverterProcessor` | `column`, `fromCurrency`, `toCurrency` |
| Pseudonymize | `ColumnPseudonymization` | `columns`, `hashFunction` |

## Step JSON Structure

Every step follows this format:
```json
{
  "metaType": "PROCESSOR",
  "type": "DateParser",
  "params": { ... }
}
```

Steps can be disabled with `"disabled": true` and named with `"name": "My step"`. Use `"metaType": "GROUP"` with a nested `"steps": [...]` for step folders.
