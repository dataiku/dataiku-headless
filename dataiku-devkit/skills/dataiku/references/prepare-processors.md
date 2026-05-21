# Prepare Recipe Processors

## Golden Rule

**ALWAYS prefer a purpose-built processor over `CreateColumnWithGREL`.** GREL formulas are the last resort — use only when no dedicated processor handles the operation.

Purpose-built processors are faster (native Java), produce cleaner step lists, and don't require GREL syntax knowledge. When chaining prepare steps, mix shortcuts and `add-step` freely.

## Critical: Column Names with Spaces

**Columns with spaces in their names (e.g. `Return Reason`, `Order Date`) cannot be referenced by GREL formulas, ColumnCopier, or VisualIfRule in prepare recipes.** GREL variable references replace spaces with underscores (`Return_Reason`), but the column lookup silently returns null — it does NOT match the actual column.

Workarounds (pick one):
1. **Rename first** — add a `ColumnRenamer` step to remove spaces BEFORE any GREL/VisualIfRule step, then rename back after
2. **Use a Python recipe** — `df["col with spaces"]` works correctly in pandas
3. **Use processors that take column names as params** (not GREL variables) — `DateParser`, `DateDifference`, `DateComponentsExtractor`, `StringTransformer`, `FillEmptyWithValue`, `RemoveRowsOnEmpty`, `FindReplace`, `ColumnsSelector` all accept `"columns": ["Return Reason"]` and work correctly with spaces

Processors that **DO** work with spaces (they take column names in `columns[]` params):
`DateParser`, `DateDifference`, `DateComponentsExtractor`, `StringTransformer`, `FillEmptyWithValue`, `RemoveRowsOnEmpty`, `FindReplace`, `FlagOnValue`, `FilterOnBadType`, `ColumnsSelector`, `ColumnRenamer`, `ColumnsConcat`

Processors that **DO NOT** work with spaces (they use GREL variable references):
`CreateColumnWithGREL` (`add-formula`), `ColumnCopier`, `VisualIfRule`, `FilterOnCustomFormula`

## Processor Decision Table

Before writing a GREL formula, check this table. The processors below are stock DSS unless flagged otherwise (`FoldColumnsByName` is a plugin — see its section).

| Need to... | Processor | CLI |
|------------|-----------|-----|
| Rename columns | `ColumnRenamer` | `add-rename --from old --to new` |
| Delete/keep columns | `ColumnsSelector` | `add-delete-columns --columns "c1,c2"` |
| Copy a column | `ColumnCopier` | `add-step --type ColumnCopier` |
| Reorder columns | `ColumnReorder` | `add-step --type ColumnReorder` |
| Coalesce (first non-null) | `Coalesce` | `add-step --type Coalesce` |
| Fill nulls/blanks (fixed value) | `FillEmptyWithValue` | `add-fill-empty --column col --value "0"` |
| Set every row to a constant | `FillColumn` | `add-step --type FillColumn --params '{"column":"col","value":"X"}'` — `{column, value}` shape; sets EVERY row of `column` to `value` (overwrites non-null AND fills nulls). Verified against localhost. Omit `value` (or pass empty string) to clear the column. For "fill nulls only, leave existing values" use `FillEmptyWithValue` instead. |
| Fill down/up | `UpDownFiller` | `add-step --type UpDownFiller` |
| Concatenate columns | `ColumnsConcat` | `add-step --type ColumnsConcat` |
| Uppercase/lowercase/trim | `StringTransformer` | `add-step --type StringTransformer` |
| Find & replace text | `FindReplace` | `add-find-replace --column col --find X --replace Y` |
| Split column by delimiter | `ColumnSplitter` | `add-step --type ColumnSplitter` |
| Split email into parts | `EmailSplitter` | `add-step --type EmailSplitter` |
| Split URL into parts | `URLSplitter` | `add-step --type URLSplitter` |
| Extract with regex | `RegexpExtractor` | `add-step --type RegexpExtractor` |
| Extract with Grok pattern | `GrokProcessor` | `add-step --type GrokProcessor` |
| Normalize/stem/stop-words | `TextSimplifierProcessor` | `add-step --type TextSimplifierProcessor` |
| Tokenize text | `Tokenizer` | `add-step --type Tokenizer` |
| If/then/else branching | GREL `if()` | `add-formula --expr 'if(cond, "a", "b")'` |
| Switch/case mapping | `SwitchCase` | `add-step --type SwitchCase` |
| Filter rows by value | `FlagOnValue` | `add-filter-rows --column col --values "a,b"` |
| Filter rows by formula | `FilterOnCustomFormula` | `add-filter-rows --formula "price > 100"` |
| Remove invalid-type rows | `FilterOnBadType` | `add-step --type FilterOnBadType` |
| Filter by numeric range | `FilterOnNumericalRange` | `add-step --type FilterOnNumericalRange` |
| Filter by date range | `FilterOnDate` | `add-step --type FilterOnDate` |
| Remove empty rows | `RemoveRowsOnEmpty` | `add-step --type RemoveRowsOnEmpty` |
| Flag invalid types | `SplitInvalidCells` | `add-step --type SplitInvalidCells` |
| Parse date strings | `DateParser` | `add-step --type DateParser` |
| Extract year/month/day | `DateComponentsExtractor` | `add-step --type DateComponentsExtractor` |
| Compute date difference | `DateDifference` | `add-step --type DateDifference` |
| Timestamp → date-only | `DateParser` (outType: dateonly) | `add-step --type DateParser` |
| Format dates (custom pattern) | `DateFormatter` | `add-step --type DateFormatter` |
| Truncate dates to unit | `DateTruncate` | `add-step --type DateTruncate` |
| Increment dates | `DateIncrement` | `add-step --type DateIncrement` |
| Parse UNIX timestamps | `UNIXTimestampParser` | `add-step --type UNIXTimestampParser` |
| Detect holidays | `HolidaysComputer` | `add-step --type HolidaysComputer` |
| Bin/discretize numbers | `BinnerProcessor` | `add-step --type BinnerProcessor` |
| Clip numeric range | `MinMaxProcessor` | `add-step --type MinMaxProcessor` |
| Round numbers | `RoundProcessor` | `add-step --type RoundProcessor` |
| Combine numeric columns | `NumericalCombinator` | `add-step --type NumericalCombinator` |
| Compute mean of columns | `MeanProcessor` | `add-step --type MeanProcessor` |
| Negate boolean | `BooleanNot` | `add-step --type BooleanNot` |
| Change column type/meaning | `TypeSetter` | `add-step --type TypeSetter` |
| Fold wide→long | `MultiColumnFold` | `add-fold --columns "c1,c2" --key-column k --value-column v` |
| Fold by column prefix | `MultiColumnByPrefixFold` | `add-step --type MultiColumnByPrefixFold` |
| Split & fold | `SplitFold` | `add-step --type SplitFold` |
| Unfold (long→wide) | `Unfold` | `add-step --type Unfold` |
| Split & unfold | `SplitUnfold` | `add-step --type SplitUnfold` |
| Pivot | `Pivot` | `add-step --type Pivot` |
| Transpose | `Transpose` | `add-step --type Transpose` |
| Flatten JSON column | `JSONFlattener` | `add-step --type JSONFlattener` |
| Extract JSON path | `JSONPathExtractor` | `add-step --type JSONPathExtractor` |
| Nest columns into JSON | `NestProcessor` | `add-step --type NestProcessor` |
| Extract from array | `ArrayExtractProcessor` | `add-step --type ArrayExtractProcessor` |
| Sort array | `ArraySortProcessor` | `add-step --type ArraySortProcessor` |
| Unfold array to columns | `ArrayUnfold` | `add-step --type ArrayUnfold` |
| Fold array to rows | `ArrayFold` | `add-step --type ArrayFold` |
| Create geopoint | `GeoPointCreator` | `add-geopoint --lat-column lat --lon-column lon` |
| Compute geo distance | GREL `geoDistance()` | `add-geodistance --from A --to B` |
| Extract lat/lon from geopoint | `GeoPointExtractor` | `add-step --type GeoPointExtractor` |
| Group long-tail values | `LongTailGrouper` | `add-step --type LongTailGrouper` |
| Count pattern matches | `MatchCounter` | `add-step --type MatchCounter` |
| Pseudonymize column | `ColumnPseudonymization` | `add-step --type ColumnPseudonymization` |
| Normalize/scale values | `MeasureNormalize` | `add-step --type MeasureNormalize` |
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

### DateParser

**When:** Parse date strings to ISO 8601. Also used for timestamp→dateonly conversion (the only working approach on DSS 14.5).

| Param | Required | Description |
|-------|----------|-------------|
| `appliesTo` | Yes | `SINGLE_COLUMN` |
| `columns` | Yes | `["date_col"]` |
| `formats` | Yes | Java date patterns: `["yyyy-MM-dd", "MM/dd/yyyy"]`. For ISO 8601 with timezone, use `Z`/`z` NOT `XXX` |
| `lang` | Yes | `"auto"` or locale code (`en_US`, `fr_FR`) |
| `timezone_id` | Yes | `"UTC"`, IANA timezone, etc. |
| `outCol` | **Yes** | Output column name. **CRITICAL: omitting outCol (in-place) silently produces all nulls** |
| `outType` | Yes | `{"name":"out","type":"date"}`, `"dateonly"`, or `"datetimenotz"` |

```json
{"appliesTo": "SINGLE_COLUMN", "columns": ["signup_date"], "formats": ["yyyy-MM-dd"], "lang": "auto", "outCol": "signup_parsed", "outType": {"name": "out", "type": "date"}, "timezone_id": "UTC"}
```

**Format ordering — `yy` MUST precede `yyyy` when both apply.** DateParser tries formats in list order and uses the first one that consumes the input. `yyyy` is permissive: it matches any digit run, so against `27-JUN-70` the pattern `dd-MMM-yyyy` will succeed and produce year `0070` instead of letting `dd-MMM-yy` (with the SimpleDateFormat 80-year pivot) fire. Symptom: dates with 2-digit years come out as years `0006`, `0070`, `0007` etc. Fix: list 2-digit-year patterns first — `["dd-MMM-yy", "d-MMM-yy", "dd-MMM-yyyy", "d-MMM-yyyy", ...]`. Same trap with `M` vs `MM`, `d` vs `dd`: most-restrictive (or shortest-year) variant first.

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

### DateFormatter

**When:** Format an ISO-8601 date column into a custom string format (e.g. `MMM yyyy`, `yyyy-MM-dd`, `EEEE d MMMM`). Input must be a parsed date column (type `date`, `datetimenotz`, or `dateonly`) — run `DateParser` first if the source is a string.

**⚠ Param naming trap:** DSS expects `inCol`/`outCol`. Agents often guess `column`/`outputColumn` from older docs — DSS rejects with a misleading `Empty column name` error. The `dku recipe add-step` CLI catches this and exits early.

| Param | Required | Description |
|-------|----------|-------------|
| `inCol` | Yes | Input column name (must be a parsed date/datetime column) |
| `outCol` | No | Output column name (omit or empty = in-place) |
| `format` | Yes | Java `SimpleDateFormat` pattern (`yyyy`, `MM`, `dd`, `HH`, `mm`, `ss`, `EEEE`, `MMM`, etc.) |
| `lang` | No | Locale code (`en_US`, `fr_FR`, …). Default `auto` |
| `timezone_id` | No | `"UTC"`, IANA timezone, `"use_preferred_timezone"`, `"extract_from_column"`. Default `"UTC"` |
| `timezone_src` | Cond | Column name when `timezone_id = "extract_from_column"` |

```json
{"inCol": "parsed_date", "outCol": "month_label", "format": "MMM yyyy", "lang": "en_US", "timezone_id": "UTC"}
```

**Output type:** `STRING`. DSS warns that non-ISO-8601 output will be treated as an unparsed date — that's fine if you only need the string representation.

---

### DateTruncate

**When:** Truncate a parsed date to a unit (year / month / day / hour / minute / second). Output keeps the date type (not a string) — good for subsequent grouping or aggregation. Prefer over GREL `trunc()`.

| Param | Required | Description |
|-------|----------|-------------|
| `inCol` | Yes | Input column name (parsed date) |
| `outCol` | No | Output column name (empty = in-place) |
| `datePart` | No | `YEAR`, `MONTH`, `DAY`, `HOUR`, `MINUTE`, `SECOND` (UPPERCASE). Default `YEAR` if omitted — **silent trap if you forget it** |

```json
{"inCol": "parsed_date", "outCol": "month_start", "datePart": "MONTH"}
```

**Gotcha:** Unknown fields (e.g., `unit`, `truncate`, `precision`) are silently ignored, and `datePart` defaults to `YEAR`. Always spell `datePart` correctly and supply one of the enum values above.

---

### UNIXTimestampParser

**When:** Convert an integer UNIX epoch column (seconds or milliseconds) to an ISO-8601 date column.

| Param | Required | Description |
|-------|----------|-------------|
| `inCol` | Yes | Input column (integer or string epoch) |
| `outCol` | No | Output column name (empty = in-place) |
| `milliseconds` | No | `true` = interpret as ms, `false` = interpret as seconds. **Default `false`** (seconds). Note: this is a BOOLEAN, not a string enum — `"unit":"SECONDS"` is ignored |

```json
{"inCol": "event_ts", "outCol": "event_date", "milliseconds": false}
```

Output column type is `date` (ISO-8601). Use downstream `DateFormatter` / `DateTruncate` / `DateParser(outType: dateonly)` for further shaping.

---

### Timestamp → date-only (common recipe)

**For timestamp string → date-only column:** Use `DateParser` with `outType: dateonly`. Always provide `outCol` — in-place DateParser **silently produces all nulls**.

```json
{"appliesTo": "SINGLE_COLUMN", "columns": ["timestamp_col"], "formats": ["yyyy-MM-dd HH:mm:ss"], "lang": "auto", "timezone_id": "UTC", "outCol": "date_only", "outType": {"name": "out", "type": "dateonly"}}
```

**DateParser format patterns (Java SimpleDateFormat):**
- `yyyy-MM-dd HH:mm:ss` — standard timestamp
- `MM/dd/yyyy h:mm a` — US format with AM/PM
- `yyyy-MM-dd'T'HH:mm:ssZ` — ISO 8601 (use `Z`/`z`, NOT `XXX` — `XXX` causes "Illegal pattern component")
- `yyyy-MM-dd` — date-only string
- Works on both string AND already-typed date columns (e.g., `datetimenotz`)

**Timezone gotcha:** DateParser converts to UTC before extracting date. `2024-01-01 23:59:59-05:00` → `2024-01-02` in UTC dateonly. Use `"timezone_id":"use_preferred_timezone"` if you want to preserve the source timezone's date.

**For UNIX epoch → date-only:** `UNIXTimestampParser` → `DateParser(outType: dateonly)` in two steps.

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

### MultiColumnFold

**When:** Unpivot wide-to-long. Prefer over `pd.melt()`. Stock DSS — works on every instance.
**CLI shortcut:** `dku recipe add-fold RECIPE --columns "jan,feb,mar" --key-column month --value-column sales -P PROJ` (emits this type with `foldRemoveFoldedColumns: true`)

| Param | Required | Description |
|-------|----------|-------------|
| `columns` | Yes | Array of column names to fold |
| `foldNameColumn` | Yes | Output column for original column names |
| `foldValueColumn` | Yes | Output column for values |
| `foldRemoveFoldedColumns` | No | `true` to drop the folded source columns (pd.melt semantic); `false`/omit to keep them |

```json
{"columns": ["jan", "feb", "mar"], "foldNameColumn": "month", "foldValueColumn": "sales", "foldRemoveFoldedColumns": true}
```

### MultiColumnByPrefixFold

**When:** Same as `MultiColumnFold`, but the columns to fold are selected by a regex on the column name. Stock DSS.
**CLI shortcut:** `dku recipe add-fold RECIPE --pattern ".*_2025" --key-column year --value-column value -P PROJ`

| Param | Required | Description |
|-------|----------|-------------|
| `columnNamePattern` | Yes | Regex matching source column names |
| `columnNameColumn` | Yes | Output column for original column names |
| `columnContentColumn` | Yes | Output column for values |
| `foldRemoveFoldedColumns` | No | `true` to drop matched source columns |

```json
{"columnNamePattern": "score_.*", "columnNameColumn": "metric", "columnContentColumn": "value", "foldRemoveFoldedColumns": true}
```

> **Plugin variants:** `FoldColumnsByName` and `FoldColumnsByPattern` exist as plugin processors with similar semantics but different param names (`keyColumn`/`valueColumn` instead of `foldNameColumn`/`foldValueColumn`). Prefer the stock processors above — the plugin versions fail with `UnavailableTypeException` when the plugin is not installed.

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

### MemoryEquiJoiner

**When:** Lookup-style equi-join inside a Prepare recipe — pulls a small `rightInput` dataset into memory and joins on `leftCol = rightCol`. Replaces a separate Join recipe when the right side is < ~100K rows. Optional Levenshtein-based fuzziness.

| Param | Required | Description |
|-------|----------|-------------|
| `leftCol` | Yes | Column from the Prepare-recipe input |
| `rightCol` | Yes | Column from `rightInput` |
| `rightInput` | Yes | Name of the small lookup dataset (must already exist) |
| `copyColumns` | Yes | Array of column names from `rightInput` to copy into the output |
| `copyPrefix` | No | Prefix added to copied column names (avoids collisions) |
| `fuzzy` | No | `true` enables Levenshtein matching |
| `maxLevenshtein` | No | Max edit distance when `fuzzy: true` |
| `normalize`, `stem`, `clearStopWords`, `sortAlphabetically`, `language`, `forceRawLevenshteinEngine` | No | Fuzzy-mode tuning (text normalization, language model) |

```json
{
  "leftCol": "country_code",
  "rightCol": "iso2",
  "rightInput": "country_lookup",
  "copyColumns": ["country_name", "region"],
  "copyPrefix": "lookup_"
}
```

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

### Unfold

**When:** Long → wide spread of a repeated value into N suffixed columns. Distinct from `Pivot` (no aggregation, no key column) and `SplitUnfold` (no separator splitting).

| Param | Required | Description |
|-------|----------|-------------|
| `column` | Yes | Source column to unfold |
| `prefix` | No | Output column prefix (defaults to `<column>_`) |
| `limit` | No | Max number of output columns. Required guard against unbounded fan-out |
| `overflowAction` | No | `ERROR` (default — fail at build) or `TRUNCATE` (silently drop overflow values) |

```json
{"column": "trucks_needed", "prefix": "truck_", "limit": 10, "overflowAction": "ERROR"}
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

### GeometryInfoExtractor

**When:** Extract geometry metadata (centroid GeoPoint, area) from a WKT or `the_geom` column. Pairs with `GeoPointCreator` / `GeoDistanceProcessor` / `CityLevelReverseGeocoder`.

| Param | Required | Description |
|-------|----------|-------------|
| `inputCol` | Yes | Geometry column (WKT or DSS `geometry` type) |
| `centroidCol` | No | Output column name for the centroid GeoPoint |
| `areaCol` | No | Output column name for the area (square units of the geometry's CRS) |

```json
{"inputCol": "the_geom", "centroidCol": "centroid", "areaCol": "area_m2"}
```

### CityLevelReverseGeocoder

**When:** Resolve admin-hierarchy levels (country / region / city / …) from a GeoPoint without hitting an external geocoding service. Distinct from forward `Geocoder` (address → point) and from the `forward_geocoding` plugin recipe.

| Param | Required | Description |
|-------|----------|-------------|
| `inputCol` | Yes | GeoPoint column |
| `l1OutCol` … `l8OutCol` | No | Output columns for admin levels 1–8. Common bindings: `l4OutCol="country"`, `l8OutCol="city"`. Omit unwanted levels |

```json
{"inputCol": "centroid", "l4OutCol": "country", "l6OutCol": "region", "l8OutCol": "city"}
```

### ZipCodeGeocoder

**When:** Cheap geocoding for postal-code-only data — emits a GeoPoint from a `(country, ZIP)` pair without hitting the full address geocoder.

| Param | Required | Description |
|-------|----------|-------------|
| `countryCol` | Yes | ISO country code column |
| `zipCodeCol` | Yes | Postal code column |
| `outputCol` | Yes | Output GeoPoint column |

```json
{"countryCol": "country", "zipCodeCol": "postal_code", "outputCol": "centroid"}
```

### ArraySortProcessor

**When:** Sort the contents of an array column.

| Param | Required | Description |
|-------|----------|-------------|
| `input` | Yes | Array column to sort |
| `sortingType` | No | `NUM` (numeric) or `ALPHANUM` (string). Default: ALPHANUM |
| `descending` | No | `true` for descending order |

```json
{"input": "proba_array", "sortingType": "NUM", "descending": true}
```

> **Wrong-param trap:** Older docs claim `column` / `order` — those names are silently dropped. Use `input` / `sortingType` / `descending`.

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

### ArrayUnfold

**When:** Explode an array column into one row per element (like `df.explode()`).

| Param | Required | Description |
|-------|----------|-------------|
| `column` | Yes | Array column to unfold |
| `keepEmptyArrays` | No | If `true`, keep rows whose array was empty (with null in the unfolded column) |
| `delete` | No | If `true`, drop the original array column from the output |
| `countVal` | No | If `true`, emit a `<column>_count` column with the original array length (fifth param, observed in live recipes; legacy `appendCount` is silently ignored) |

```json
{"column": "tags", "keepEmptyArrays": false, "delete": true, "countVal": true}
```

### GREL Critical Gotchas

| Trap | What happens | Fix |
|------|-------------|-----|
| `round(x, 2)` | Silent empty output — `round()` takes exactly 1 arg (nearest integer) | `round(x * 100) / 100` for 2 decimals, `round(x * 10) / 10` for 1 decimal |
| `toString(date, "yyyy-MM-dd")` | **No-op** — format argument silently ignored, returns original ISO date | Use the `DateFormatter` processor (`inCol`/`outCol`/`format`) for custom string formats |
| `formatDate()` / `toDate()` | **Do not exist in GREL** — "Unknown function" error | Use processors: `DateFormatter` for formatting, `DateParser` or `UNIXTimestampParser` for parsing — never these GREL functions |
| DateParser without `outCol` | **Silently produces all nulls** — in-place parsing is broken | Always specify `outCol` to write to a new column |
| Date processor `Empty column name` error | Legacy param names `column`/`outputColumn` instead of `inCol`/`outCol` | `DateFormatter`, `DateTruncate`, `UNIXTimestampParser` all use `inCol`/`outCol`. The `dku recipe add-step` CLI catches this and exits early |
| `DateTruncate` silently truncates to year | `datePart` param missing or misspelled (e.g. `unit`, `truncate`) — unknown fields are ignored and it defaults to `YEAR` | Always spell `datePart` exactly; valid values are `YEAR`/`MONTH`/`DAY`/`HOUR`/`MINUTE`/`SECOND` (UPPERCASE) |
| `UNIXTimestampParser` dates at `1970-01-21` | Default `milliseconds` is `false`; passing `"unit":"SECONDS"` does nothing because `unit` isn't a valid key | Use boolean `"milliseconds": true` for ms input, `false` (or omit) for seconds |
| `asDateOnly()` on STRING column | Silently fails in some recipe contexts | Run `DateParser` step first, then use the parsed column in date functions |
| `log()` | Returns base-10, not natural log | Use `ln()` for natural log |
| `numval(col)` / `val(col)` bareword | Silent empty output — accessor needs a quoted column name | Use `numval("col")` / `val("col")` with quotes, OR drop the wrapper and use bareword `col` (arithmetic auto-coerces) |
| Formula column type | New columns default to STRING | Always run `apply-schema` after adding formula steps |

---

## Full Processor Catalog (Quick Reference)

For processors not covered in detail above, use `add-step --type TYPE --params JSON`. Key params are listed for orientation — verify exact params via `dku recipe get-step` on an existing recipe or DSS documentation.

### Column Operations

| Processor | Type ID | Key Params |
|-----------|---------|------------|
| Reorder columns | `ColumnReorder` | `columns`, `referenceColumn`, `reorderAction` |
| Fill with prev/next | `UpDownFiller` | `columns: List<String>`, `up: bool` (`true`=fill from next, `false`=fill from previous). Only NULL triggers fill — empty string `""` is treated as a value. To trigger a fill from a formula, return `null`, not `""` |
| Coalesce (first non-null) | `Coalesce` | `appliesTo`, `columns`, `outputColumn`, `defaultValue`, `useDefaultValue` |

### Numeric

| Processor | Type ID | Key Params |
|-----------|---------|------------|
| Round numbers | `RoundProcessor` | **`columns`** (PLURAL array — NOT `column`), `appliesTo` (`COLUMNS`/`PATTERN`/`ALL` — REQUIRED), `mode` (`ROUND`/`CEILING`/`FLOOR`/`TRUNCATE`), `precision` (decimal places, 0 = integer rounding), `places` (round to nearest 10/100; only meaningful with CEILING/FLOOR), `useDecimalSeparatorFromLocale` (bool). Singular `column` + missing `appliesTo` silently produces a no-op step (DSS skips processors with bad param names) |
| Force range (clip) | `MinMaxProcessor` | `columns`, **`lowerBound`**, **`upperBound`**, **`clear`** (boolean — `true` empties out-of-range cells, `false` clamps them). NOT `min`/`max`/`action` — those names are silently ignored. |
| Convert number format | `NumericalFormatConverter` | `appliesTo`, `columns`, `outCol`, `inFormat`, `outFormat` |
| Combine columns (add/sub/mul) | `NumericalCombinator` | `columns`, `output`, `operation` |
| Compute mean of columns | `MeanProcessor` | `appliesTo`, `columns`, `outputColumn` |
| Compute percentile | `ComputeNTile` | `appliesTo`, `columns`, `outCol`, `n` |
| Group rare values | `MergeLongTailValues` | `appliesTo`, `columns`, `thresholdMode`, `countThreshold`, `replacementValue` |

### String/Text

| Processor | Type ID | Key Params |
|-----------|---------|------------|
| Extract with regex | `RegexpExtractor` | `column` (SINGULAR — NOT `columns: [list]` + `appliesTo: SINGLE_COLUMN` like DateParser; that shape errors with the misleading `Empty column name`), `pattern`, `extractAllOccurrences`. **Output cols are named after capture-group index (`1`, `2`, …)** — rename with `ColumnRenamer` (`{"renamings":[{"from":"1","to":"Name"}, …]}`) immediately after, or downstream steps will reference the cryptic numeric name |
| Tokenize text | `Tokenizer` | `column`, `outputColumn`, `operation` |
| Count occurrences | `MatchCounter` | `input`, `output`, `pattern` |

### Date/Time

| Processor | Type ID | Key Params |
|-----------|---------|------------|
| Timestamp → date-only | `DateParser` | Use `outType: dateonly` + `outCol` (MUST have outCol — in-place = all nulls) |
| Format date (custom pattern) | `DateFormatter` | `inCol`, `outCol`, `format` (SimpleDateFormat), `lang`, `timezone_id` — NOT `column`/`outputColumn` |
| Truncate date | `DateTruncate` | `inCol`, `outCol`, `datePart` (`YEAR`/`MONTH`/`DAY`/`HOUR`/`MINUTE`/`SECOND`) — defaults to `YEAR` if `datePart` missing |
| Date increment | `DateIncrement` | `column`, `incrementValue`, `incrementUnit` |
| Unix timestamp | `UNIXTimestampParser` | `inCol`, `outCol`, `milliseconds` (BOOLEAN: `true`=ms, `false`=sec). NOT `unit`/`"SECONDS"` |
| Flag holidays | `HolidaysComputer` | `column`, `calendar_id`, `flagColumn` |

### Split & Reshape

| Processor | Type ID | Key Params |
|-----------|---------|------------|
| Unfold (long→wide) | `Unfold` | `column` |
| Split and fold | `SplitFold` | `column`, `separator`, `foldedColumn` |
| Pivot (in prepare) | `Pivot` | `indexColumn`, `labelsColumn`, `valuesColumn` |
| Transpose | `Transpose` | (no params) |

### JSON & Array

| Processor | Type ID | Key Params |
|-----------|---------|------------|
| Extract from array | `ArrayExtractProcessor` | `column`, `index` |
| Fold array to rows | `ArrayFold` | `column` |
| Sort array | `ArraySortProcessor` | `input`, `sortingType` (NUM/ALPHANUM), `descending` |
| JSONPath extract | `JSONPathExtractor` | `column`, `expression`, `output` |
| Nest columns to JSON | `NestProcessor` | `columns`, `output` |
| Zip arrays | `ZipArrays` | `inputColumns`, `outputColumn` |
| Concat arrays | `ConcatArrays` | `inputColumns`, `outputColumn` |

### Joins & Enrichment (in Prepare)

| Processor | Type ID | Key Params |
|-----------|---------|------------|
| Join with dataset | `MemoryEquiJoiner` | `leftCol`, `rightCol`, `rightInput`, `copyColumns` |
| Fuzzy join | `FuzzyJoiner` | `leftCol`, `rightCol`, `rightInput`, `maxLevenshtein` |

### Geo

| Processor | Type ID | Key Params |
|-----------|---------|------------|
| Geo point buffer | `GeoPointBufferProcessor` | **`inputColumn`** (NOT `column`), `outputColumn`, `shapeMode` (`CIRCLE` uses `radius`; `RECTANGLE` uses `width`+`height`), `unitMode` (`METERS`/`KILOMETERS`/`MILES`/`FEET`/`YARDS`/`NAUTICAL_MILES` — NOT `unit`), `radius`, `width`, `height`. Following the legacy doc names (`column`/`unit`) silently produces a no-op buffer step |
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

---

## Critical gotchas

### Date formatting in Prepare recipes
`DateFormatter`, `DateTruncate`, `UNIXTimestampParser` all exist on DSS 14.5. The agent trap is wrong param names: they use `inCol` / `outCol` (NOT `column` / `outputColumn` from older docs), and DSS returns a misleading `Empty column name` error otherwise — the `dku recipe add-step` CLI catches this pre-send. Other traps:
- `DateTruncate` param is `datePart` (values `YEAR` / `MONTH` / `DAY` / `HOUR` / `MINUTE` / `SECOND`) and defaults to `YEAR` if missing.
- `UNIXTimestampParser` uses `milliseconds` BOOLEAN, not `unit` string.
- GREL `formatDate()` and `toDate()` do not exist; GREL `toString(date, "format")` is a no-op.
- `DateParser` without `outCol` silently produces all nulls.
- ISO 8601 `DateParser` format: use `Z` / `z` pattern, NOT `XXX`.

### Processor field-name traps (silent no-ops)
DSS silently ignores unknown processor params — wrong field names produce a step that looks accepted but does nothing. The traps:
- `MinMaxProcessor`: `lowerBound` / `upperBound` / `clear` (NOT `min` / `max` / `action`).
- `GeoIPResolver`: `inCol` / `outColPrefix` + 10 boolean `extract_*` toggles (`extract_country` / `_country_code` / `_continent` / `_continent_code` / `_region` / `_city` / `_postal_code` / `_latitude` / `_longitude` / `_timezone`) — NOT `inputColumn` / `outputColumn`.
- `FillColumn`: `{column, value}` — sets EVERY row of `column` to `value` (overwrites non-null AND fills nulls). For "fill nulls only, leave existing values" use `FillEmptyWithValue`.
- `ArrayUnfold`: `countVal: true` emits the `<col>_count` length column (legacy `appendCount` is silently ignored).
- `PythonUDF`: requires `mode: ROW|CELL` — CELL needs `column`. Missing `mode` produces a no-op.
