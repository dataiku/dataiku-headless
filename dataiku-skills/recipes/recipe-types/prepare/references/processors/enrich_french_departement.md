---
name: prepare-enrich-french-departement
description: "Observed JSON patterns for the EnrichFrenchDepartement prepare/shaker processor."
---

# EnrichFrenchDepartement Processor

Enrich a French department code column with INSEE demography, housing, fiscal, employment, and companies columns. DSS engine only (no SQL pushdown); requires the bundled INSEE department CSV resource file on the DSS install.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `column` | yes | `string<column_name>` | Column holding the French department code | Input department code column. Single-digit codes left-padded to two chars before lookup; unmatched rows pass through unchanged. |
| `sourceDatasetVersion` | conditional | `enum` | `INSEE_2009_2011` \| `INSEE_JAN_2024` | Selects bundled INSEE CSV + column-to-category mapping. Form default `INSEE_JAN_2024`; absent at build time falls back to `INSEE_2009_2011`. |
| `basicDemography` | no | `boolean` | `true` \| `false` | Default `true`. Appends population, households, births, deaths, working-age population columns. |
| `housing` | no | `boolean` | `true` \| `false` | Default `true`. Appends dwellings, principal/secondary residences, vacant, owner-occupied columns. |
| `fiscal` | no | `boolean` | `true` \| `false` | Default `true`. Appends fiscal/revenue columns (tax households, taxable, median revenue, taxable ratio). |
| `employment` | no | `boolean` | `true` \| `false` | Default `true`. Appends employment columns (jobs, unemployment, active population). |
| `companies` | no | `boolean` | `true` \| `false` | Default `true`. Appends companies columns (establishments, sector breakdown, size breakdown). |
| `prefix` | no | `string<any>` | Any prefix string | Form default `departement`. Prefix applied to every generated output column name. |

## Canonical Variant

```json
{
  "type": "EnrichFrenchDepartement",
  "params": {
    "basicDemography": true,
    "companies": true,
    "housing": true,
    "fiscal": true,
    "prefix": "departement",
    "column": "fr_department",
    "employment": true,
    "sourceDatasetVersion": "INSEE_JAN_2024"
  }
}
```
