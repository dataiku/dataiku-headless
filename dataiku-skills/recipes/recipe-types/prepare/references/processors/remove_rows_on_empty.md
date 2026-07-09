---
name: prepare-remove-rows-on-empty
description: "Observed JSON patterns for the RemoveRowsOnEmpty prepare/shaker processor."
---

# RemoveRowsOnEmpty Processor

Delete rows with empty/null value in selected column(s); or keep only those rows when `keep` is `true`.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `appliesTo` | yes | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param. |
| `columns` | yes | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param. |
| `appliesToPattern` | conditional | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param; required when `appliesTo` is `PATTERN`. |
| `keep` | no | `boolean` | `true` \| `false` | Default `false`. `false`=remove rows where any selected column empty; `true`=keep only rows where at least one selected column empty. Multiple columns: emptiness OR-combined. |

## Canonical Variants

### Remove rows empty in either of several columns

```json
{
  "type": "RemoveRowsOnEmpty",
  "params": {
    "columns": ["sparse_label", "invalid_number"],
    "keep": false,
    "appliesTo": "COLUMNS"
  }
}
```

### Keep only rows that are empty in a single column

```json
{
  "type": "RemoveRowsOnEmpty",
  "params": {
    "columns": ["sparse_label"],
    "keep": true,
    "appliesTo": "SINGLE_COLUMN"
  }
}
```
