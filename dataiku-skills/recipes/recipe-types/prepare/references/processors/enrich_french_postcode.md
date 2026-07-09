---
name: prepare-enrich-french-postcode
description: "Observed JSON patterns for the EnrichFrenchPostcode prepare/shaker processor."
---

# EnrichFrenchPostcode Processor

Enrich French postcode column with associated department code plus INSEE demography, housing, fiscal, employment, companies columns. DSS engine only; requires bundled INSEE postcode CSV resource file on DSS install.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `column` | yes | `string<column_name>` | Column holding the French postcode (numeric, 5 digits) | Input postcode column. Parsed as integer then formatted to five digits for lookup; non-numeric values skipped, row passes through. |
| `sourceDatasetVersion` | conditional | `enum` | `INSEE_2009_2011` \| `INSEE_JAN_2024` | Selects bundled INSEE CSV + column mapping. Form default `INSEE_JAN_2024`; absent at build time falls back to `INSEE_2009_2011`. |
| `departement` | no | `boolean` | `true` \| `false` | Default `true`. Appends associated department code column. Unique to postcode processor. |
| `basicDemography` | no | `boolean` | `true` \| `false` | Default `true`. Appends basic demographic columns aggregated over cities sharing the postcode. |
| `housing` | no | `boolean` | `true` \| `false` | Default `true`. Appends housing columns. |
| `fiscal` | no | `boolean` | `true` \| `false` | Default `true`. Appends fiscal/revenue columns. |
| `employment` | no | `boolean` | `true` \| `false` | Default `true`. Appends employment columns. |
| `companies` | no | `boolean` | `true` \| `false` | Default `true`. Appends companies columns. |
| `prefix` | no | `string<any>` | Any prefix string | Form default `postcode`. Prefix applied to every generated output column name. |

## Canonical Variant

```json
{
  "type": "EnrichFrenchPostcode",
  "params": {
    "basicDemography": true,
    "companies": true,
    "departement": true,
    "housing": true,
    "fiscal": true,
    "prefix": "postcode",
    "column": "fr_postcode",
    "employment": true,
    "sourceDatasetVersion": "INSEE_JAN_2024"
  }
}
```
