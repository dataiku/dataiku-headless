---
name: prepare-compute-n-tile
description: "Observed JSON patterns for the ComputeNTile prepare/shaker processor."
---

# ComputeNTile Processor

Assign each row n-tile (quantile) bucket for numeric column; new column or in place. SQL/in-database (or native Spark) engine only; needs DB `ntile()` operator; DSS streaming engine yields null.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `appliesTo` | yes | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param. |
| `columns` | yes | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param. |
| `appliesToPattern` | conditional | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param; required when `appliesTo` is `PATTERN`. |
| `n` | yes | `integer` | Positive integer | Number of quantiles. Default `100`. |
| `outCol` | no | `string<column_name>` \| `""` | Any valid output column name or empty string | Empty/unset=in place. Honored only under `SINGLE_COLUMN`; `COLUMNS`/`PATTERN`/`ALL` write in place per column. |

## Canonical Variant

```json
{
  "type": "ComputeNTile",
  "params": {
    "outCol": "qty_quartile",
    "columns": ["qty"],
    "appliesTo": "SINGLE_COLUMN",
    "n": 4
  }
}
```
