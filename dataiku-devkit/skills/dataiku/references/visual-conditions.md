# Visual Conditions Reference

Shared `uiData.conditions[]` schema used across DSS visual recipe filters, split conditions, prepare VisualIfRule, and sampling filters.

## Where Used

- **Filter recipes** — the `filterCondition` in payload
- **Join recipes** — `preFilter` and `postFilter` on virtual inputs
- **Group/Window/TopN/Distinct** — `preFilter` and `postFilter`
- **Split recipes** — split condition per output
- **Prepare VisualIfRule** — branch conditions in `visualIfDesc.ifThen.filter`
- **Sampling recipes** — row sampling filter

## Condition Structure

Every filter uses this envelope:

```json
{
  "enabled": true,
  "distinct": false,
  "uiData": {
    "mode": "&&",
    "conditions": [
      { "input": "column_name", "operator": "operator_string", ... }
    ]
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `enabled` | boolean | Whether filter is active |
| `distinct` | boolean | Deduplicate after filtering |
| `uiData.mode` | `"&&"` or `"\|\|"` | AND or OR between conditions |
| `uiData.conditions` | array | List of condition objects |

## Condition Object Fields

Each condition in the `conditions[]` array:

| Field | Type | Used when |
|-------|------|-----------|
| `input` | string | Column name to test (always required) |
| `operator` | string | Operator string (see catalog below) |
| `string` | string | Text value for string operators |
| `num` | number | Numeric value for comparison operators |
| `num2` | number | Second numeric value for range operators |
| `date` | string | ISO-8601 date for date operators |
| `col` | string | Column name for column-vs-column comparisons |
| `items` | array | Values list for `in [string]` operator |

> **VisualIfRule caveat:** Inside a Prepare recipe's `VisualIfRule` step, several operators below produce a silent `False` when the step is created via API (DSS bug, verified on stock DSS): `regex`, `in [string]`, `not in [string]`, `== [date]`/`>  [date]`/`<  [date]`, and geo operators. In filter/join/split recipes these operators work; only VisualIfRule is affected. If you need these inside a VisualIfRule, use GREL alternatives in a `CreateColumnWithGREL` or `FilterOnCustomFormula` step instead (see `prepare-processors.md` → VisualIfRule).

## Operator Catalog

### String Operators

| Operator | Meaning | Required fields |
|----------|---------|-----------------|
| `== [string]` | Equals | `string` |
| `!= [string]` | Not equals | `string` |
| `== [string]i` | Equals (case-insensitive) | `string` |
| `contains` | Contains substring | `string` |
| `not contains` | Does not contain | `string` |
| `contains [string]i` | Contains (case-insensitive) | `string` |
| `starts with` | Starts with | `string` |
| `ends with` | Ends with | `string` |
| `regex` | Matches regex | `string` |
| `in [string]` | In list of values | `items: [{"string":"val1"},{"string":"val2"}]` |
| `not in [string]` | Not in list | `items: [{"string":"val1"}]` |

### Numeric Operators

| Operator | Meaning | Required fields |
|----------|---------|-----------------|
| `>  [number]` | Greater than | `num` |
| `<  [number]` | Less than | `num` |
| `>= [number]` | Greater or equal | `num` |
| `<= [number]` | Less or equal | `num` |
| `== [number]` | Equals | `num` |
| `!= [number]` | Not equals | `num` |
| `>< [number]` | Between (inclusive) | `num`, `num2` |

Note: Operator strings include trailing spaces (e.g. `">  [number]"` with two spaces).

### Null/Empty Operators

| Operator | Meaning | Required fields |
|----------|---------|-----------------|
| `is empty` | Value is null or empty | (none) |
| `not empty` | Value is not null/empty | (none) |

### Date Operators

| Operator | Meaning | Required fields |
|----------|---------|-----------------|
| `== [date]` | Date equals | `date` |
| `>  [date]` | After date | `date` |
| `<  [date]` | Before date | `date` |

### Column-vs-Column Operators

| Operator | Meaning | Required fields |
|----------|---------|-----------------|
| `== [column]` | Equals another column | `col` |
| `!= [column]` | Not equals another column | `col` |
| `>  [column]` | Greater than another column | `col` |

## Canonical Examples

### AND group — numeric range + not empty

```json
{
  "enabled": true,
  "distinct": false,
  "uiData": {
    "mode": "&&",
    "conditions": [
      {"input": "age", "operator": ">= [number]", "num": 18},
      {"input": "age", "operator": "<= [number]", "num": 65},
      {"input": "email", "operator": "not empty"}
    ]
  }
}
```

### OR group — multiple string matches

```json
{
  "enabled": true,
  "distinct": false,
  "uiData": {
    "mode": "||",
    "conditions": [
      {"input": "country", "operator": "== [string]", "string": "US"},
      {"input": "country", "operator": "== [string]", "string": "GB"},
      {"input": "country", "operator": "== [string]", "string": "DE"}
    ]
  }
}
```

### Contains with regex

```json
{
  "enabled": true,
  "distinct": false,
  "uiData": {
    "mode": "&&",
    "conditions": [
      {"input": "email", "operator": "regex", "string": ".*@company\\.com$"}
    ]
  }
}
```

### Between (numeric range)

```json
{
  "enabled": true,
  "distinct": false,
  "uiData": {
    "mode": "&&",
    "conditions": [
      {"input": "price", "operator": ">< [number]", "num": 10.0, "num2": 100.0}
    ]
  }
}
```

## Filter Envelope in Recipes

In visual recipe payloads, filters are wrapped in a filter object:

```json
{
  "preFilter": {
    "enabled": true,
    "distinct": false,
    "uiData": { "mode": "&&", "conditions": [...] }
  },
  "postFilter": {
    "enabled": false,
    "distinct": false,
    "uiData": { "mode": "&&", "conditions": [] }
  }
}
```

- **preFilter** — applied before the recipe operation (filtering input rows)
- **postFilter** — applied after the recipe operation (filtering output rows)

Both use the same `uiData.conditions[]` schema above.

## Formula Mode (Alternative)

Filters can also use formula mode instead of visual conditions:

```json
{
  "enabled": true,
  "$status": { "schema": { "columns": [...] } },
  "uiData": { "mode": "&&", "conditions": [] },
  "expression": "price > 100 && category == 'Electronics'"
}
```

**Which field DSS evaluates depends entirely on `uiData.mode`:**

| `uiData.mode` | What DSS evaluates | Syntax in `expression` | Use when |
|---|---|---|---|
| `"&&"` or `"\|\|"` | `uiData.conditions[]` (visual mode) | n/a — ignored | Single- or multi-column comparisons composable as AND/OR |
| `"CUSTOM"` | `expression` (formula mode) | GREL — `val("col") != 0`, `isnull(col)`, etc. | Multi-column formulas, GREL functions, computed-column references; works on every engine |
| `"SQL"` | `expression` (SQL mode) | Raw SQL — `"order_id" != 0` (column names quoted as SQL identifiers) | SQL-only constructs (subqueries, SQL-flavor regex, vendor-specific functions). Requires a SQL engine — won't run on the in-memory DSS engine |

**This is the gotcha.** If you set `expression` but leave `uiData.mode: "&&"` (or `"||"`), DSS evaluates the visual-conditions array (which is probably empty) and ignores your formula. The filter becomes a no-op with no error. Empirically verified on Group recipe pre/postFilter — `mode: "&&"` + populated `expression` + empty `conditions: []` returned all input rows; switching to `mode: "CUSTOM"` (with the same `expression`) honored the formula.

**Canonical formula-mode shape (matches what the DSS UI saves):**

```json
{
  "enabled": true,
  "distinct": false,
  "uiData": {
    "mode": "CUSTOM",
    "$latestOperator": "&&",
    "$filterOptions": "CUSTOM",
    "conditions": []
  },
  "expression": "amount_sum >= 300 && status == 'A'"
}
```

**Canonical SQL-mode shape:**

```json
{
  "enabled": true,
  "distinct": false,
  "uiData": {
    "mode": "SQL",
    "$latestOperator": "&&",
    "$filterOptions": "SQL",
    "conditions": []
  },
  "expression": "\"order_id\" != 0 AND \"status\" = 'A'"
}
```

In SQL mode, `expression` is raw SQL: identifier quoting (double quotes around column names) and SQL operators (`=` not `==`, `AND` not `&&`, `IS NULL` not `isnull(col)`). **`fullyTranslated: false` is expected** when SQL mode references constructs the engine-fallback layer can't reproduce — that's fine if your flow is SQL-pinned (rule 2), but it's a problem on a flow that may execute in the in-memory engine.

The `$latestOperator` and `$filterOptions` are UI metadata for round-tripping when the user toggles between modes — preserve them if you read-modify-write, but they're not required for evaluation. The `conditions[]` array can be empty in `CUSTOM` or `SQL` mode.
