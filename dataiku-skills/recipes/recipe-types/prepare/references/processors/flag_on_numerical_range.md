---
name: prepare-flag-on-numerical-range
description: "Observed JSON patterns for the FlagOnNumericalRange prepare/shaker processor."
---

# FlagOnNumericalRange Processor

Flag rows whose selected numeric column values fall inclusively within a numerical range; creates column holding `1` for matching rows.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `appliesTo` | yes | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param. |
| `columns` | conditional | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param; required non-empty when `appliesTo` is `SINGLE_COLUMN` or `COLUMNS`. |
| `appliesToPattern` | conditional | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param; required when `appliesTo` is `PATTERN`. |
| `action` | yes | `enum` | `FLAG` | Creates flag column; never removes rows. |
| `booleanMode` | no | `enum` | `AND` \| `OR` | Combines range checks across selected columns: `AND`=all in range; `OR`=any in range. |
| `flagColumn` | yes | `string<column_name>` | Any valid output column name | Column created/updated with `1` for matching (in-range) rows. |
| `min` | no | `number` | Any numeric value; null/empty allowed | Inclusive lower bound; empty=no lower bound. |
| `max` | no | `number` | Any numeric value; null/empty allowed | Inclusive upper bound; empty=no upper bound. |
| `includeEmptyValues` | no | `boolean` | `true` \| `false` | `true`=empty cell counts as matching; else empty/non-numeric out of range. |

## Canonical Variant

```json
{
  "type": "FlagOnNumericalRange",
  "params": {
    "min": 1.0,
    "max": 10.0,
    "columns": ["qty"],
    "booleanMode": "AND",
    "appliesTo": "SINGLE_COLUMN",
    "action": "FLAG",
    "includeEmptyValues": false,
    "flagColumn": "qty_in_range_1_10"
  }
}
```
