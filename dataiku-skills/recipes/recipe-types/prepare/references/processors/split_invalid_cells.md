---
name: prepare-split-invalid-cells
description: "Observed JSON patterns for the SplitInvalidCells prepare/shaker processor."
---

# SplitInvalidCells Processor

Move cells of a column invalid for a chosen meaning into a new column; leave valid values in place. Local DSS streaming engine only (depends on meanings service to validate cells); not SQL-translatable, no native Spark implementation.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `column` | yes | `string<column_name>` | Any valid source column name | Column inspected; cells invalid for `type` moved out. |
| `invalidColumn` | yes | `string<column_name>` | Any valid output column name | New output column receiving invalid values; created immediately after `column`. |
| `type` | yes | `string<any>` | A built-in meaning identifier (for example `Number`, `Date`) or a user-defined meaning id | Meaning used to validate cells. |
| `considerEmptyAsInvalid` | no | `boolean` | `true` \| `false` | Default `false`. `true`=empty cells also treated as invalid and moved to `invalidColumn`. |

## Canonical Variant

```json
{
  "type": "SplitInvalidCells",
  "params": {
    "considerEmptyAsInvalid": false,
    "invalidColumn": "invalid_number_invalid",
    "column": "invalid_number",
    "type": "Number"
  }
}
```
