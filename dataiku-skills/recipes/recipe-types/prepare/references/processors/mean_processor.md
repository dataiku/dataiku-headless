---
name: prepare-mean-processor
description: "Observed JSON patterns for the MeanProcessor prepare/shaker processor."
---

# MeanProcessor

Compute per-row mean of two or more numeric columns into new output column.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `appliesTo` | yes | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param. Typical usage is `COLUMNS` across two or more numeric columns. |
| `columns` | conditional | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param; required non-empty when `appliesTo` is `SINGLE_COLUMN` or `COLUMNS`. |
| `appliesToPattern` | conditional | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param; required when `appliesTo` is `PATTERN`. |
| `outputColumn` | yes | `string<column_name>` | Any valid output column name | Target for row-wise mean; cannot be blank (no in-place). Created or overwritten. |
| `useDefaultValue` | yes | `boolean` | `true` \| `false` | `false`=all-empty selection yields empty cell; `true`=write `defaultValue`. |
| `defaultValue` | conditional | `number` | Any numeric value | Value when every selected column empty for row; required when `useDefaultValue` is `true`. |

## Canonical Variant

```json
{
  "type": "MeanProcessor",
  "params": {
    "outputColumn": "qty_price_mean",
    "columns": ["qty", "price"],
    "defaultValue": 0,
    "appliesTo": "COLUMNS",
    "useDefaultValue": false
  }
}
```
