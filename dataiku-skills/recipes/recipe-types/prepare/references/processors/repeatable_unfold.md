---
name: prepare-repeatable-unfold
description: "Observed JSON patterns for the RepeatableUnfold prepare/shaker processor."
---

# RepeatableUnfold Processor

Group rows by key column; each time trigger value appears in fold column, flush accumulated data-column values into new row with dynamically named fold columns. DSS streaming engine only; buffers all per-key data in memory across whole stream; not SQL-translatable.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `keyColumn` | yes | `string<column_name>` | Any existing column name | Event key grouping rows. Mandatory non-empty; null-key rows skipped. |
| `foldColumn` | yes | `string<column_name>` | Any existing column name | Values unfolded into new columns. Mandatory non-empty; source column deleted after folding. |
| `foldTrigger` | yes | `string<any>` | Any value occurring in `foldColumn` | Mandatory non-empty. Each exact occurrence in `foldColumn` flushes previous accumulated group to new row. Creates output columns named `foldTrigger` and `prev_`+`foldTrigger`. |
| `dataColumn` | yes | `string<column_name>` | Any existing column name | Values placed into unfolded output columns. Mandatory non-empty; source column deleted after folding. |

## Canonical Variant

```json
{
  "type": "RepeatableUnfold",
  "params": {
    "foldTrigger": "start",
    "keyColumn": "user_id",
    "foldColumn": "event_type",
    "dataColumn": "payload"
  }
}
```
