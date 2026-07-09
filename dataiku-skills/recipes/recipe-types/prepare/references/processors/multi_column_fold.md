---
name: prepare-multi-column-fold
description: "Observed JSON patterns for the MultiColumnFold prepare/shaker processor."
---

# MultiColumnFold Processor

Melt chosen columns into long form, emitting one row per non-empty cell with source column name and value in two new columns. DSS streaming engine only; melt fan-out not SQL-translatable.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `columns` | yes | `list<string<column_name>>` | List of existing column names | Columns to fold (melt). Per non-empty cell among these, emits one output row with source column name and cell value. |
| `foldNameColumn` | yes | `string<any>` | New column name | New output column holding folded column names. |
| `foldValueColumn` | yes | `string<any>` | New column name | New output column holding folded values. |
| `foldRemoveFoldedColumns` | no | `boolean` | `true` \| `false` | Default `false`. `true`=original folded columns deleted after folding. |

## Canonical Variant

```json
{
  "type": "MultiColumnFold",
  "params": {
    "columns": ["qty", "price", "user_id"],
    "foldValueColumn": "fold_value",
    "foldRemoveFoldedColumns": true,
    "foldNameColumn": "fold_name"
  }
}
```
