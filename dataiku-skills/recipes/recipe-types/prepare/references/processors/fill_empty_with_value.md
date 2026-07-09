---
name: prepare-fill-empty-with-value
description: "Observed JSON patterns for the FillEmptyWithValue prepare/shaker processor."
---

# FillEmptyWithValue Processor

Replace empty/null cells in selected column(s) with a fixed placeholder value.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `appliesTo` | yes | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param. |
| `columns` | yes | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param. |
| `appliesToPattern` | conditional | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param; required when `appliesTo` is `PATTERN`. |
| `value` | no | `string<any>` | Any text value | Written into each null/empty cell; non-empty cells untouched. SQL engine: output column type may widen (integer stays integer if value parses as long; becomes double if numeric column and value parses as double; else string). |

## Canonical Variants

### Fill several columns with a literal placeholder

```json
{
  "type": "FillEmptyWithValue",
  "params": {
    "columns": ["sparse_label", "invalid_number"],
    "appliesTo": "COLUMNS",
    "value": "UNKNOWN"
  }
}
```

### Fill a single column with a numeric default

```json
{
  "type": "FillEmptyWithValue",
  "params": {
    "columns": ["invalid_number"],
    "appliesTo": "SINGLE_COLUMN",
    "value": "0"
  }
}
```
