---
name: prepare-object-fold-processor
description: "Observed JSON patterns for the ObjectFoldProcessor prepare/shaker processor."
---

# ObjectFoldProcessor

Parse JSON-object column; fold each key/value entry into its own row, writing key and value into two new columns and deleting source column. DSS streaming engine only; JSON parse + one-row-per-key fan-out not SQL-translatable.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `column` | yes | `string<column_name>` | Any existing column name | Holds JSON object literal to fold. Mandatory non-empty. Creates output columns `column`+`_key` and `column`+`_val`; each object entry becomes its own row; source column deleted afterward. |
| `emitEmptyObject` | no | `boolean` | `true` \| `false` | Default `false`. `true`=empty JSON object `{}` produces one row with null key/value; `false`=no row. |
| `emitNonObject` | no | `boolean` | `true` \| `false` | Default `false`. `true`=blank cells or values failing JSON object parse produce one row with null key/value; `false`=no row. |

## Canonical Variant

```json
{
  "type": "ObjectFoldProcessor",
  "params": {
    "emitNonObject": false,
    "column": "json_object",
    "emitEmptyObject": false
  }
}
```
