---
name: prepare-round-processor
description: "Observed JSON patterns for the RoundProcessor prepare/shaker processor."
---

# RoundProcessor

Round numeric values in selected columns in place; round/floor/ceiling at chosen decimal places or significant digits.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `appliesTo` | yes | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param; rounding is always applied in place. |
| `columns` | yes | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param. |
| `appliesToPattern` | conditional | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param; required when `appliesTo` is `PATTERN`. |
| `mode` | yes | `enum` | `ROUND` \| `FLOOR` \| `CEIL` | `ROUND`=HALF_UP; `FLOOR`; `CEIL`. Default `ROUND`. |
| `precision` | no | `integer` | `0` (unbounded) or any non-negative integer | Significant digits; `0`=keep all. Non-zero disables SQL/Spark translation. |
| `places` | no | `integer` | Any integer (for example `0`, `2`, `-2`) | Decimal places; `0`=round to integer, `-2`=round to hundreds. Non-zero disables SQL/Spark translation unless `mode` is `ROUND`. |

## Canonical Variant

```json
{
  "type": "RoundProcessor",
  "params": {
    "mode": "ROUND",
    "places": 2,
    "columns": ["price"],
    "precision": 0,
    "appliesTo": "SINGLE_COLUMN"
  }
}
```
