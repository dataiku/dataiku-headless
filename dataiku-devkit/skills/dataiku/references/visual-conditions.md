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

When `expression` is set, it takes precedence over `uiData.conditions`. Use Dataiku formula syntax (see `references/formulas.md`).
