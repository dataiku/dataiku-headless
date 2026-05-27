# Prepare Processors: Core Column, String, Numeric, Filter, Formula

Processor details for common row-local Prepare steps. Read `prepare-processors.md` first for selection guidance.

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

> **`keep: true` does NOT reorder.** It filters the schema to the listed columns and preserves their on-disk order, which is the input order — not the order in your `columns` array. To impose a final column order, use `ColumnReorder` below. Verified empirically: a `ColumnsSelector keep:true` step with columns listed in a custom order leaves the output schema in input order.

---

### ColumnReorder

**When:** Force a specific column order in the output schema. Use after a `ColumnsSelector keep:true` if you also want to reorder, or anywhere you need to pin a column to a specific position.
**CLI shortcut:** `dku recipe add-reorder RECIPE -c col1 -c col2 --mode BEFORE_COLUMN --anchor existing_col -P PROJ` (auto-fills `appliesTo` based on column count — see gotcha below).

| Param | Required | Description |
|-------|----------|-------------|
| `appliesTo` | Yes | `SINGLE_COLUMN` (one column) or `COLUMNS` (multiple columns). **Required** — the UI shows "Applies mode not selected" / "Move columns invalid" when missing, and the step renders as a no-op. |
| `columns` | Yes | Array of column names to move (in the order you want) |
| `referenceColumn` | When `reorderAction ∈ {BEFORE_COLUMN, AFTER_COLUMN}` | Anchor column — `columns` are placed relative to this one |
| `reorderAction` | Yes | `AT_THE_BEGINNING` / `AT_THE_END` / `BEFORE_COLUMN` / `AFTER_COLUMN` |

```json
{
  "appliesTo": "COLUMNS",
  "columns": ["customer_id", "order_date", "total"],
  "referenceColumn": "",
  "reorderAction": "AT_THE_BEGINNING"
}
```

For `BEFORE_COLUMN` / `AFTER_COLUMN`, set `referenceColumn` to the anchor; for `AT_THE_BEGINNING` / `AT_THE_END`, leave it empty. The processor moves the listed columns as a group, preserving their relative order. Run `dku recipe apply-schema RECIPE -P PROJ` after adding to propagate the new order downstream.

**`appliesTo` is required.** Without it, the UI shows "Applies mode not selected" / "Move columns invalid" and the step is silently a no-op on save. Set `SINGLE_COLUMN` for one column, `COLUMNS` for multi-column moves. **Multi-column moves work correctly** when `appliesTo: COLUMNS` is set — earlier diagnoses claiming "BEFORE_COLUMN only moves the first column" were caused by missing `appliesTo`, not a server bug. The `dku recipe add-reorder` shortcut auto-fills the right value based on `--column` count, so prefer that over raw `add-step --type ColumnReorder`.

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

**When:** Uppercase, lowercase, trim, normalize, or truncate text. Prefer over GREL `toUppercase()`, `toLowercase()`, `trim()`.

| Param | Required | Description |
|-------|----------|-------------|
| `mode` | Yes | `TO_UPPER`, `TO_LOWER`, `TRIM`, `NORMALIZE`, `TRUNCATE` |
| `appliesTo` | Yes | Scope (see shared params) |
| `columns` | Yes | `["col_name"]` |
| `truncate_limit` | Cond | Integer max length (required when `mode: TRUNCATE`) |

```json
{"mode": "TO_UPPER", "appliesTo": "SINGLE_COLUMN", "columns": ["city"]}
```

**Note on mode names:** use `TO_UPPER`/`TO_LOWER`, NOT `UPPERCASE`/`LOWERCASE`. Wrong values produce a runtime NullPointerException (`this.parameter.mode is null`) at build time, not at step-add time. DSS has no `TITLECASE` mode — for title case, use GREL `toTitlecase(col)`.

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
| `startFrom` | Cond | **Required when `limitOutput: true`.** `"beginning"` or `"end"` (lowercase only — `"BEGINNING"` fails). Set to `null` when `limitOutput: false`. |

```json
{"inCol": "full_name", "separator": " ", "outColPrefix": "name_", "target": "COLUMNS", "keepEmptyChunks": false, "limitOutput": false, "limit": 0, "startFrom": "beginning"}
```

With `limitOutput`:
```json
{"inCol": "notes", "separator": " - ", "outColPrefix": "notes_", "target": "COLUMNS", "keepEmptyChunks": false, "limitOutput": true, "limit": 2, "startFrom": "beginning"}
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

**When:** If/then/else branching logic. For multiple branches, prefer over nested GREL `if()`.

| Param | Required | Description |
|-------|----------|-------------|
| `legacyPositioning` | Yes | Always `false` for new steps |
| `visualIfDesc.ifThen` | Yes | Primary IF branch: `{filter, actions}` |
| `visualIfDesc.elseIfThens` | No | Additional ELSE IF branches (array) |
| `visualIfDesc.elseActions` | No | ELSE actions (array) |

Each branch has a `filter` (visual condition) and `actions` (output assignments):
- **Filter:** `{"uiData": {"mode": "&&", "conditions": [...]}, "distinct": true, "enabled": true}`
- **Condition:** `{"input": "col_name", "col": "", "operator": "...", "string": "", "num": 0.0, "num2": 0.0}`
  - `input` — column being tested (left-hand side)
  - `col` — other-column name for `== [column]` operator (right-hand side). **Use `col`, not `string`** — the string field holds literal values, not column refs.
  - `string` / `num` / `num2` — literal value(s) for the operator
- **Action:** `{"outputColumnName": "result", "column": "", "formula": "", "value": "high", "operator": "ASSIGN_VALUE"}`

#### Condition operators

| Category | Operator string | Value field | Notes |
|----------|----------------|-------------|-------|
| Empty/defined | `is empty` | — | |
| | `not empty` | — | |
| String | `== [string]` | `string` | |
| | `!= [string]` | `string` | |
| | `contains` | `string` | |
| | `not contains` | `string` | |
| Number | `== [number]` | `num` | |
| | `!= [number]` | `num` | |
| | `>  [number]` | `num` | 2 spaces after `>` |
| | `<  [number]` | `num` | 2 spaces after `<` |
| | `>= [number]` | `num` | 1 space after `>=` |
| | `<= [number]` | `num` | 1 space after `<=` |
| Column compare | `== [column]` | `col` (other column name) | Use `col`, NOT `string` |
| Boolean | `true` | — | |
| | `false` | — | |

**Broken via API** (produce silent `False` — DSS bug, verified on stock DSS): `regex`, `in [string]`, `not in [string]`. Date and geo operators also known to fail. Verified-working operators in the table above. Use GREL alternatives for broken ones:
- Regex: `add-formula --expr 'if(length(match(col, /pattern/)) > 0, "YES", "NO")'` — note `/pattern/`, not `"pattern"`
- Is any of: `add-formula --expr 'switch(col, "a", "MATCH", "b", "MATCH", "NO_MATCH")'`

The same `uiData.conditions[]` schema is shared with filter/join/split recipes (see `visual-conditions.md`). The broken-operator bug is specific to VisualIfRule within Prepare; other recipe types may handle these operators differently — verify before relying on them via API.

#### Action operators

| UI label | Operator string | Field used |
|----------|----------------|------------|
| = (Value) | `ASSIGN_VALUE` | `value` |
| = (Column) | `ASSIGN_COLUMN` | `column` |
| = (Formula) | `ASSIGN_FORMULA` | `formula` (GREL expression) |

#### Full example

```json
{
  "legacyPositioning": false,
  "visualIfDesc": {
    "ifThen": {
      "filter": {"uiData": {"mode": "&&", "conditions": [{"input": "amount", "col": "amount", "string": "", "num": 200.0, "items": [], "operator": ">= [number]", "num2": 0.0}]}, "distinct": true, "enabled": true},
      "actions": [{"outputColumnName": "tier", "column": "", "formula": "", "value": "HIGH", "operator": "ASSIGN_VALUE"}]
    },
    "elseIfThens": [
      {
        "filter": {"uiData": {"mode": "&&", "conditions": [{"input": "amount", "col": "amount", "string": "", "num": 100.0, "items": [], "operator": ">  [number]", "num2": 0.0}]}, "distinct": true, "enabled": true},
        "actions": [{"outputColumnName": "tier", "column": "", "formula": "", "value": "MEDIUM", "operator": "ASSIGN_VALUE"}]
      }
    ],
    "elseActions": [{"outputColumnName": "tier", "column": "", "formula": "", "value": "LOW", "operator": "ASSIGN_VALUE"}]
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

For `FLAG` action, add `"flagColumn": "col_name"` to create a boolean flag column instead of filtering rows:

```json
{"appliesTo": "SINGLE_COLUMN", "columns": ["status"], "values": ["active"], "action": "FLAG", "flagColumn": "is_active", "matchingMode": "FULL_STRING", "normalizationMode": "EXACT", "booleanMode": "AND", "exclude": false, "processNullOrEmptyValues": false}
```

**Related Flag processors** (same pattern, different condition types):
- `FlagOnBadType` — flag by column type: `{"appliesTo": "SINGLE_COLUMN", "columns": ["amount"], "type": "Numeric", "action": "FLAG", "flagColumn": "is_valid", "considerEmptyAsInvalid": true, "booleanMode": "AND"}`
- `FlagOnCustomFormula` — flag by formula: `{"expression": "val(\"amount\") > 100", "action": "FLAG", "flagColumn": "high_amount"}` (quoted column name required for `val`/`numval`/`strval`)
- `FlagOnDate` — flag by date range: `{"appliesTo": "SINGLE_COLUMN", "columns": ["date"], "filterType": "RANGE", "min": "2024-01-01T00:00:00.000", "max": "2024-12-31T00:00:00.000", "action": "FLAG", "flagColumn": "in_2024", "timezone_id": "UTC", "booleanMode": "AND", "includeEmptyValues": false}`
- `FlagOnNumericalRange` — flag by numeric range: `{"appliesTo": "SINGLE_COLUMN", "columns": ["amount"], "min": 100.0, "max": 500.0, "action": "FLAG", "flagColumn": "in_range", "booleanMode": "AND", "includeEmptyValues": false}`

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

Note: The CLI shortcut `add-filter-rows --formula` uses `FilterOnCustomFormula` internally. Always use `FilterOnCustomFormula` (not `FilterOnFormula`) — the latter is a plugin type that may not be installed on all DSS instances and will fail with `UnavailableTypeException`.

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
| `useDecimalSeparatorFromLocale` | No | When true, render bin labels using the user's locale decimal separator (e.g. `,` in fr_FR). Display only |

```json
{"input": "age", "output": "age_group", "mode": "WIDTH", "width": 10.0, "bins": [], "useMin": false, "min": 0.0, "useMax": false, "max": 0.0}
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

### DateIncrement

**When:** Add a fixed time delta to a date column (anonymization, projection scenarios).

| Param | Required | Description |
|-------|----------|-------------|
| `inCol` | Yes | Input date column |
| `outCol` | Yes | Output column |
| `datePart` | Yes | `YEAR` / `MONTH` / `DAY` / `HOUR` / `MINUTE` / `SECOND` |
| `incrementBy` | Yes | `STATIC` (constant offset) or `COLUMN` (per-row offset from `incrementCol`) |
| `increment` | If `STATIC` | Integer offset |
| `incrementCol` | If `COLUMN` | Column holding the per-row offset |

```json
{"inCol": "start_date", "outCol": "anon_start", "datePart": "YEAR", "incrementBy": "STATIC", "increment": 5}
```

### FlagOnNumericalRange

**When:** Add a boolean flag column when a numeric value falls in `[min, max]`. Pair with downstream Window/Group: e.g. `uptime_ratio = sum(machine_idle_flag) / count`.

| Param | Required | Description |
|-------|----------|-------------|
| `appliesTo`, `columns` | Yes | Standard scope params |
| `min`, `max` | Yes | Numeric bounds |
| `action` | Yes | `FLAG` (write a boolean column) — distinct from `FilterOnNumericalRange` whose action is `KEEP_ROW` / `REMOVE_ROW` |
| `flagColumn` | Yes | Name of the boolean column to write |
| `booleanMode` | No | `AND` / `OR` when multiple columns are scoped |
| `includeEmptyValues` | No | Whether nulls count as in-range |

```json
{
  "appliesTo": "SINGLE_COLUMN",
  "columns": ["Floatvalue"],
  "min": -5.0,
  "max": 5.0,
  "action": "FLAG",
  "flagColumn": "machine_idle",
  "booleanMode": "AND",
  "includeEmptyValues": false
}
```

### NumericalFormatConverter

**When:** Convert numerals between FR/US locales (decimal `,` ↔ `.`, thousand separator). Common Alteryx Multi-Field Formula replacement.

| Param | Required | Description |
|-------|----------|-------------|
| `appliesTo`, `columns` | Yes | Standard scope params |
| `outCol` | No | Output column (omit to overwrite input column) |
| `inFormat` | Yes | `FR`, `US`, or `RAW` |
| `outFormat` | Yes | `FR`, `US`, or `RAW` |

```json
{"appliesTo": "SINGLE_COLUMN", "columns": ["price_str"], "outCol": "price_us", "inFormat": "FR", "outFormat": "US"}
```

### ExtractNumbers

**When:** Extract numeric values out of free-text columns (e.g. pull every number from a description, optionally normalising "1.2k" → 1200).

| Param | Required | Description |
|-------|----------|-------------|
| `input` | Yes | Source column |
| `output` | Yes | Output column |
| `multipleValues` | No | `true` returns ALL numbers concatenated by `delimiter`; `false` returns the first match only |
| `delimiter` | No | Separator for multiple values. Default `","` |
| `replaceMultipliers` | No | `true` parses `1.2k` → `1200`, `3M` → `3000000` |
| `extractToJson` | No | `true` emits a JSON array string instead of a delimiter-joined string |

```json
{"input": "description", "output": "amounts", "multipleValues": true, "replaceMultipliers": true, "extractToJson": true}
```

### PythonUDF

**When:** Inline a Python row-by-row or cell-by-cell transformation inside a Prepare recipe — instead of creating a separate Python recipe for a one-off transformation. Common case: parse a JSON column into multiple output columns; apply a custom regex; classify a row using arbitrary Python logic.

| Param | Required | Description |
|-------|----------|-------------|
| `mode` | Yes | `ROW` (function takes a row dict, returns a row dict) or `CELL` (function takes a cell, returns a scalar — set `column`) |
| `pythonSourceCode` | Yes | Python source. ROW mode defines `def process(row): ... return row`. CELL mode defines `def process(cell): ... return val`. |
| `column` | CELL only | Column the cell function operates on |
| `sourceColumnsList` | No | Restrict the row dict to these columns (perf optimisation) |
| `useKernel` | No | `true` runs in a fresh Python process per recipe (slower start, full library access). `false` (default) embeds in the in-process interpreter. |
| `vectorize` | No | `true` switches `process()` to receive a pandas `Series`/`DataFrame` chunk. Pair with `vectorSize`. |
| `vectorSize` | No | Chunk size for vectorized mode. Default 256. |
| `envSelection` | No | `{envMode: INHERIT|USE_BUILTIN_MODE|EXPLICIT, envName?}` — code env. Default INHERIT. |
| `stopOnError` | No | `true` (default) raises on first row error; `false` skips and continues. |

```json
{
  "mode": "ROW",
  "pythonSourceCode": "import json\ndef process(row):\n    meta = json.loads(row.get('meta') or '{}')\n    row['distance'] = meta.get('distance')\n    return row",
  "envSelection": {"envMode": "INHERIT"},
  "stopOnError": false
}
```

> **When to prefer this over a separate Python recipe:** PythonUDF runs as one step inside a Prepare recipe — avoids creating a 30-line Python recipe for a row-level transformation. Migration target: SAS DATA-step custom logic, Alteryx Multi-Row Formula, pandas `apply()` chains.

> **When NOT to use:** aggregations, joins, reshapes — those need their own visual recipe (Group/Join/Pivot). PythonUDF is row-local.

### EnrichWithBuildContextProcessor

**When:** Stamp every row with a build-time timestamp so downstream queries can answer "as of when was this data computed?".

| Param | Required | Description |
|-------|----------|-------------|
| `buildDateColumn` | Yes | Output column name for the build timestamp |

```json
{"buildDateColumn": "build_ts"}
```
