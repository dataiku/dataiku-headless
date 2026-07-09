---
name: prepare-switch-case
description: "Observed JSON patterns for the SwitchCase prepare/shaker processor."
---

# SwitchCase Processor

Map input-column values to new output column via ordered key-to-value rules; fallback default for unmatched rows. SQL pushdown when `normalization`=`EXACT`/`LOWERCASE`; `NORMALIZED`=DSS/stream engine.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `inputColumn` | yes | `string<column_name>` | Any existing column name | Source column matched against mapping keys. |
| `outputColumn` | yes | `string<column_name>` | Any valid output column name | New/overwritten output column, placed right after input column. |
| `normalization` | no | `enum` | `EXACT` \| `LOWERCASE` \| `NORMALIZED` | Default `EXACT`. LOWERCASE=ignore case; NORMALIZED=ignore case+accents. Only EXACT/LOWERCASE keep SQL engine. |
| `defaultValue` | no | `string<any>` | Any text value | Written to output for unmatched rows. Default empty string. |
| `mapping` | yes | `list<object<{from:string<any>,to:string<any>}>>` | Ordered list of `{from,to}` rules | Highest-to-lowest priority; empty `from` also matches null/empty input. |

## `mapping[]` Matrix

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `from` | yes | `string<any>` | Key matched against normalized input. |
| `to` | yes | `string<any>` | Written to output column on match. |

## Canonical Variant

```json
{
  "type": "SwitchCase",
  "params": {
    "inputColumn": "category",
    "outputColumn": "category_group",
    "normalization": "LOWERCASE",
    "defaultValue": "other",
    "mapping": [
      {"from": "electronics", "to": "group_E"},
      {"from": "books", "to": "group_B"},
      {"from": "toys", "to": "group_T"}
    ]
  }
}
```
