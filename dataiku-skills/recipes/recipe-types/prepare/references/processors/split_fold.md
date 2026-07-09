---
name: prepare-split-fold
description: "Observed JSON patterns for the SplitFold prepare/shaker processor."
---

# SplitFold Processor

Split delimited column on literal whole-string separator; fan each input row into one row per non-empty chunk, overwriting column with that chunk. DSS streaming engine only; row fan-out not SQL-translatable.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `column` | yes | `string<column_name>` | Any existing column name | Column to split and fold. Mandatory non-empty; each chunk overwrites this column's value in emitted rows. |
| `separator` | yes | `string<any>` | Any non-empty string | Whole-string separator (literal, not regex). Mandatory non-empty. Value yielding exactly one chunk passes original row through unchanged. |
| `keepEmptyChunks` | no | `boolean` | `true` \| `false` | Default `false`. `false`=empty chunks produce no row; `true`=empty chunks emit a row. |
| `trimSpaces` | no | `boolean` | `true` \| `false` | Default `true`. `true`=each chunk trimmed before written back into column. |

## Canonical Variant

```json
{
  "type": "SplitFold",
  "params": {
    "trimSpaces": true,
    "keepEmptyChunks": false,
    "column": "tags",
    "separator": ";"
  }
}
```
