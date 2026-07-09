---
name: prepare-unfold
description: "Observed JSON patterns for the Unfold prepare/shaker processor."
---

# Unfold Processor

Dummify categorical column into one binary indicator column per distinct value. SQL/native-Spark translation only after a design-time run records the unfolded value set; otherwise DSS engine.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `column` | yes | `string<column_name>` | Any valid source column name | Column whose distinct values become binary (0/1) indicator columns. |
| `prefix` | no | `string<any>` | Any column-name prefix | Prepended to each created name; cols named `prefix` + `<value>`, hold `1` when row matches that value. |
| `overflowAction` | no | `enum` | `KEEP` \| `WARNING` \| `ERROR` \| `CLIP` | Behavior when distinct-value count exceeds `limit`. Default `ERROR`. `KEEP`=create all; `WARNING`=add warning; `ERROR`=throw; `CLIP`=stop creating further columns. |
| `limit` | no | `integer` | Any non-negative integer (unbounded) | Max columns to create. Default `100`. Triggers `overflowAction` once distinct values reach this count. |

## Canonical Variant

```json
{
  "type": "Unfold",
  "params": {
    "overflowAction": "ERROR",
    "prefix": "category_",
    "column": "category",
    "limit": 100
  }
}
```
