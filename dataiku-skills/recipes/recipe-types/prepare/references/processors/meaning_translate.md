---
name: prepare-meaning-translate
description: "Observed JSON patterns for the MeaningTranslate prepare/shaker processor."
---

# MeaningTranslate Processor

Translate a column's values through a user-defined VALUES_MAPPING meaning, writing mapped labels in place or to a new column. Requires a pre-existing user-defined VALUES_MAPPING meaning referenced by `meaningId`; build fails at init if meaning unknown or not VALUES_MAPPING.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `appliesTo` | yes | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param. |
| `columns` | yes | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param. |
| `appliesToPattern` | conditional | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param; required when `appliesTo` is `PATTERN`. |
| `meaningId` | yes | `string<any>` | Id of an existing user-defined meaning of type VALUES_MAPPING | Meaning driving value replacement; init throws if unknown or not VALUES_MAPPING. Lookup normalized via meaning's normalization mode; unmatched values map to null. |
| `outCol` | no | `string<column_name>` \| `""` | Any valid output column name or empty string | Empty/unset=in-place. Honored only when `appliesTo`=`SINGLE_COLUMN`; `COLUMNS`/`PATTERN`/`ALL` always in-place. |

## Canonical Variant

```json
{
  "type": "MeaningTranslate",
  "params": {
    "outCol": "category_translated",
    "columns": ["category"],
    "appliesTo": "SINGLE_COLUMN",
    "appliesToPattern": "",
    "meaningId": "category_label_mapping"
  }
}
```
