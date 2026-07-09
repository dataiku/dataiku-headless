---
name: prepare-split-unfold
description: "Observed JSON patterns for the SplitUnfold prepare/shaker processor."
---

# SplitUnfold Processor

Split delimited string column on a separator; unfold each distinct chunk into its own column whose cell holds that chunk's occurrence count in the row. SQL translation conditional: only after a design-time run records `unfoldedValues` and only when `keepEmptyChunks` is `false`; else DSS streaming engine.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `column` | yes | `string<column_name>` | Any existing column name | Column split by `separator` then unfolded into columns. Mandatory non-empty. |
| `prefix` | no | `string<any>` | Any string | Prepended to each created name; empty/unset=no prefix. Cols named `prefix`+`<chunk>`. |
| `separator` | yes | `string<any>` | Any non-empty string | Whole-string split separator (literal, not regex). Mandatory non-empty; no default. |
| `keepEmptyChunks` | no | `boolean` | `true` \| `false` | Default `false`. `true`=empty chunks between consecutive separators kept as a column; `true` also disables SQL translation. |
| `overflowAction` | no | `enum` | `KEEP` \| `WARNING` \| `ERROR` \| `CLIP` | Default `ERROR`. Behavior when distinct-chunk count exceeds `limit`. |
| `limit` | no | `integer` | `>= 0` (`0` = unbounded) | Default `100`. Max columns to create. |

## Canonical Variant

```json
{
  "type": "SplitUnfold",
  "params": {
    "overflowAction": "ERROR",
    "prefix": "tag_",
    "keepEmptyChunks": false,
    "column": "tags",
    "limit": 100,
    "separator": ";"
  }
}
```
