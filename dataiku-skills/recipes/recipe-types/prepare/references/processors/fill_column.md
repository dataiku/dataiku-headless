---
name: prepare-fill-column
description: "Observed JSON patterns for the FillColumn prepare/shaker processor."
---

# FillColumn Processor

Overwrite every value in a column with single constant; create column if absent.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `column` | yes | `string<column_name>` | Any valid column name | Existing or new column; every value overwritten; created if absent. |
| `value` | yes | `string<any>` | Any constant value (may be empty) | Fixed value written into every row. Supports DSS variable expansion (`${my_var}`). |

## Canonical Variant

```json
{
  "type": "FillColumn",
  "params": {
    "column": "invalid_number",
    "value": "0"
  }
}
```
