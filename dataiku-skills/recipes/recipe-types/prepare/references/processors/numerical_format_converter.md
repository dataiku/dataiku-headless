---
name: prepare-numerical-format-converter
description: "Observed JSON patterns for the NumericalFormatConverter prepare/shaker processor."
---

# NumericalFormatConverter Processor

Convert numbers from one language/country-specific format to another.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `appliesTo` | yes | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param. |
| `columns` | yes | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param. |
| `appliesToPattern` | conditional | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param; required when `appliesTo` is `PATTERN`. |
| `inFormat` | yes | `enum` | `FR` \| `CH` \| `IT` \| `RAW` \| `EN` | Same value set as `outFormat`. |
| `outCol` | yes | `string<column_name>` | Any valid output column name | Column containing converted values. |
| `outFormat` | yes | `enum` | `FR` \| `CH` \| `IT` \| `RAW` \| `EN` | Output number formatting convention. |

## Canonical Variants

### English to French format

```json
{
  "type": "NumericalFormatConverter",
  "params": {
    "appliesTo": "SINGLE_COLUMN",
    "columns": ["score"],
    "inFormat": "EN",
    "outCol": "score_french_format",
    "outFormat": "FR"
  }
}
```

### English to raw numeric string

```json
{
  "type": "NumericalFormatConverter",
  "params": {
    "appliesTo": "SINGLE_COLUMN",
    "columns": ["score"],
    "inFormat": "EN",
    "outCol": "score_raw_format",
    "outFormat": "RAW"
  }
}
```

## Update Guidance

1. Read existing payload first and keep unrelated top-level keys untouched.
2. Modify only target `steps[]` entries for `NumericalFormatConverter`.
3. Keep `outCol` unique per conversion step to avoid overwriting prior outputs.
4. If multiple destination formats are needed, add separate steps rather than overloading one step.
