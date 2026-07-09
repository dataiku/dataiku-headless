---
name: prepare-array-unfold
description: "Observed JSON patterns for the ArrayUnfold prepare/shaker processor."
---

# ArrayUnfold Processor

Unfold JSON-array string column into one column per distinct array element, holding occurrence count or binary indicator. DSS/Java engine only; not SQL-translatable; no native Spark.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `column` | yes | `string<column_name>` | Any valid source column name | Column of JSON string arrays. Unparseable-JSON rows raise `INPUT_DATA_BAD_DATA` warning and are skipped. |
| `prefix` | no | `string<any>` | Any column-name prefix | Prepended to each created name; cols named `prefix` + `<array element>`. |
| `countVal` | no | `boolean` | `true` \| `false` | Default `true`. `true`=cell holds occurrence count of term in array; `false`=binary `1` indicator per distinct term. |
| `overflowAction` | no | `enum` | `KEEP` \| `WARNING` \| `ERROR` \| `CLIP` | Behavior when distinct-term count exceeds `limit`. Default `ERROR`. `KEEP`=create all; `WARNING`=add warning; `ERROR`=throw; `CLIP`=stop creating further columns. |
| `limit` | no | `integer` | Any non-negative integer (unbounded) | Max columns to create. Default `100`. Triggers `overflowAction` once distinct terms reach this count. |

## Canonical Variant

```json
{
  "type": "ArrayUnfold",
  "params": {
    "countVal": true,
    "overflowAction": "ERROR",
    "prefix": "arr_",
    "column": "json_array",
    "limit": 100
  }
}
```
