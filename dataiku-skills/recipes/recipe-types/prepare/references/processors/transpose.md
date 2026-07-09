---
name: prepare-transpose
description: "Observed JSON patterns for the Transpose prepare/shaker processor."
---

# Transpose Processor

Transpose dataset: chosen column's row values become column headers, original columns become rows. Hard-capped at 100 input rows (rows past position 100 skipped); DSS engine only.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `column` | yes | `string<column_name>` | Any existing column name | Transpose-key column; row values become output column headers. Duplicate keys collide, last occurrence kept; null/empty value uses row index as column name. |

## Canonical Variant

```json
{
  "type": "Transpose",
  "params": {
    "column": "category"
  }
}
```
