---
name: window-recipe-settings-and-payload-reference
description: "Settings and payload reference for window recipes, including window definitions, value metrics, ranking flags, and filters."
---

# Window Recipe Settings And Payload Reference

Use this reference for `window` payload edits (`get_recipe_settings` + `set_recipe_settings` action `set_payload`).

## Observed Settings Shape

In these recipes:

- `payload` controls behavior.
- `params` is empty.

Observed top-level payload keys:

- `windows`
- `values`
- `computedColumns`
- `preFilter`
- `postFilter`
- rank flags: `rowNumber`, `rank`, `denseRank`, `cumeDist`, `ntile`, `ntileValues`
- `retrievedColumnsSelectionMode`
- `outputColumnNameOverrides`
- `engineParams`
- `legacyUnboundedWindowStreamBehavior`

## Payload Matrix

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `windows` | yes | `list<object>` | Window definitions (partitioning, ordering, limits, prefixes). |
| `values` | yes | `list<object>` | Selected columns + window metric flags and options. |
| `computedColumns` | no | `list<object>` | Computed columns available before window operations. |
| `rowNumber` | no | `boolean` | Enable row number per configured window. |
| `rank` | no | `boolean` | Enable rank per configured window. |
| `denseRank` | no | `boolean` | Enable dense rank per configured window. |
| `cumeDist` | no | `boolean` | Enable cumulative distribution per configured window. |
| `ntile` | no | `boolean` | Enable ntile per configured window. |
| `ntileValues` | no | `string` | Bucket count for ntile (observed as string values like `"10"`). |
| `retrievedColumnsSelectionMode` | no | `enum` | Observed values: `ALL`, `EXPLICIT`. |
| `preFilter` | no | `object` | Filter before window calculations. |
| `postFilter` | no | `object` | Filter after window calculations. |
| `outputColumnNameOverrides` | no | `object<string,string>` | Optional output column rename overrides. |
| `engineParams` | no | `object` | Engine/runtime settings; preserve unless explicitly changing execution behavior. |
| `legacyUnboundedWindowStreamBehavior` | no | `boolean` | Legacy execution behavior switch. |

## `windows[]` Matrix

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `enablePartitioning` | no | `boolean` | If true, provide `partitioningColumns`. |
| `partitioningColumns` | conditional | `list<string<column_name>>` | Partition keys for the window. |
| `enableOrdering` | no | `boolean` | If true, provide `orders`. |
| `orders` | conditional | `list<object>` | Window ordering columns and direction. |
| `enableLimits` | no | `boolean` | If true, provide limit bounds and mode fields. |
| `windowLimitMode` | conditional | `enum` | Observed values: `ROWS`, `RANGE`. |
| `limitPreceding` / `limitFollowing` | conditional | `boolean` | Limit switches for bounds. |
| `windowLowerBound` / `windowUpperBound` | conditional | `integer` | Limit bounds values. |
| `precedingRows` / `followingRows` | no | `integer` | Row offsets in row-based windows. |
| `windowDateRangeUnit` | conditional | `enum` | Date range unit (observed: `MONTH` in range mode). |
| `prefix` | no | `string<column_prefix>` | Prefix for generated output columns. |

### `windows[].orders[]` Matrix

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `column` | yes | `string<column_name>` | Order-by column. |
| `desc` | no | `boolean` | Descending sort when true. |

## `values[]` Matrix

`values[]` carries both passthrough column selection (`value=true`) and metric toggles.

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `column` | conditional | `string<column_name>` | Source column for metric/passthrough entries. |
| `type` | yes | `string<meaning_or_storage_type>` | Output type hint for generated metrics. |
| `value` | no | `boolean` | Keep source value in output. In `retrievedColumnsSelectionMode=EXPLICIT`, this is the primary passthrough selector. |
| Aggregation flags (`sum`, `avg`, `min`, `max`, `stddev`, `count`, `concat`, `concatDistinct`, `first`, `last`) | conditional | `boolean` | Window metric selection flags. |
| Lag/lead flags (`lag`, `lead`, `lagDiff`, `leadDiff`) | conditional | `boolean` | Lag/lead metric controls. |
| `lagValues` / `leadValues` | conditional | `string` | Comma-separated offsets (observed as strings). |
| `orderColumn` | conditional | `string<column_name>` | Order-sensitive metric support field (observed with first/last/lag/lead entry). |
| `concatSeparator` | conditional | `string` | Separator for concat metrics. |
| `customExpr` / `customName` | conditional | `string` | Custom window SQL expression + output column name. |
| `dateDiffUnit` | no | `enum` | Date diff unit for date-based lag/lead diffs. |

## `computedColumns[]` Matrix

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `mode` | yes | `enum` | `GREL` \| `SQL` | Expression engine. |
| `name` | yes | `string<column_name>` | Any valid output column name | Computed column name. |
| `expr` | yes | `string<any>` | Any formula/SQL expression | Computed column expression text. |
| `type` | yes | `string<meaning_or_storage_type>` | Any valid output type | Computed column type. |

## Canonical Payload Examples (Trimmed)

### Single window with partition-only average

```json
{
  "windows": [
    {
      "enablePartitioning": true,
      "partitioningColumns": ["state"],
      "enableOrdering": false,
      "orders": [],
      "enableLimits": false
    }
  ],
  "values": [
    {"column": "monthly_income", "avg": true, "type": "double", "value": true}
  ],
  "rowNumber": false,
  "rank": false,
  "denseRank": false,
  "cumeDist": false,
  "ntile": false,
  "ntileValues": "10"
}
```

### Range window with concat + lag/lead metrics

```json
{
  "windows": [
    {
      "enablePartitioning": true,
      "partitioningColumns": ["state"],
      "enableOrdering": true,
      "orders": [{"column": "date_of_birth", "desc": false}],
      "enableLimits": true,
      "windowLimitMode": "RANGE",
      "windowDateRangeUnit": "MONTH",
      "windowLowerBound": 3,
      "windowUpperBound": 3,
      "prefix": "state_dob_6_month_window"
    }
  ],
  "values": [
    {"column": "status", "concat": true, "concatDistinct": true, "concatSeparator": ",", "type": "string", "value": true},
    {
      "column": "interest_rate",
      "sum": true,
      "avg": true,
      "min": true,
      "max": true,
      "stddev": true,
      "count": true,
      "first": true,
      "last": true,
      "lag": true,
      "lead": true,
      "lagDiff": true,
      "leadDiff": true,
      "lagValues": "1,2,3",
      "leadValues": "5",
      "orderColumn": "id",
      "type": "double",
      "value": true
    }
  ]
}
```

### Multi-window ranking and ntile outputs

```json
{
  "windows": [
    {
      "prefix": "w1",
      "enablePartitioning": true,
      "partitioningColumns": ["status"],
      "enableOrdering": true,
      "orders": [{"column": "interest_rate", "desc": true}],
      "enableLimits": true,
      "windowLimitMode": "ROWS",
      "followingRows": 5
    },
    {
      "prefix": "w2",
      "enablePartitioning": true,
      "partitioningColumns": ["status"],
      "enableOrdering": true,
      "orders": [{"column": "interest_rate", "desc": true}],
      "enableLimits": true,
      "windowLimitMode": "ROWS",
      "followingRows": 10
    }
  ],
  "values": [
    {"column": "default", "avg": true, "type": "double", "value": true}
  ],
  "rowNumber": true,
  "rank": true,
  "denseRank": true,
  "cumeDist": true,
  "ntile": true,
  "ntileValues": "10"
}
```

### Window with computed column, custom expression, and filters

```json
{
  "computedColumns": [
    {"mode": "GREL", "name": "interest_rate_plus_2", "expr": "interest_rate+2", "type": "double"}
  ],
  "values": [
    {"column": "interest_rate", "avg": true, "type": "double", "value": true},
    {"customExpr": "RANK() OVER $window + 1", "customName": "rank_over_window_plus_1", "type": "INT"}
  ],
  "preFilter": {"enabled": true, "distinct": true},
  "postFilter": {"enabled": true, "distinct": false}
}
```

### Explicit retrieved-columns mode with selective passthrough

```json
{
  "retrievedColumnsSelectionMode": "EXPLICIT",
  "windows": [
    {
      "enablePartitioning": true,
      "partitioningColumns": ["state"],
      "enableOrdering": true,
      "orders": [{"column": "date_of_birth", "desc": false}],
      "enableLimits": false
    }
  ],
  "values": [
    {"column": "id", "value": true, "type": "bigint"},
    {"column": "date_of_birth", "value": true, "type": "date"},
    {"column": "monthly_income", "value": true, "avg": true, "type": "double"},
    {"column": "interest_rate", "value": false, "avg": true, "sum": true, "type": "double"},
    {"column": "status", "value": false, "type": "string"}
  ],
  "rowNumber": false,
  "rank": false,
  "denseRank": false,
  "cumeDist": false,
  "ntile": false,
  "ntileValues": "10"
}
```

## Recommended Update Pattern

1. Read current settings with `get_recipe_settings`.
2. Copy current payload.
3. Edit only intended blocks (`windows`, `values`, rank flags, filters, computed/custom columns).
4. Write payload with `set_recipe_settings` action `set_payload`.
5. Re-read settings to confirm only intended keys changed.
