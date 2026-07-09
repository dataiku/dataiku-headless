---
name: prepare-up-down-filler
description: "Observed JSON patterns for the UpDownFiller prepare/shaker processor."
---

# UpDownFiller Processor

Fill empty cells in selected column(s) with previous non-empty value above (fill down) or next non-empty value below (fill up). Local DSS streaming engine only; order-sensitive. Engines not preserving row order (Snowflake) fill gaps but scramble sequence.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `columns` | yes | `list<string<column_name>>` | Any existing column names | Columns whose empty cells filled. Multi-column when `up`=`false`; exactly one when `up`=`true`. |
| `up` | no | `boolean` | `true` \| `false` | Default `false`. `false`=fill with previous non-empty value (fill down, multi-column); `true`=fill with next non-empty value (fill up, single column only). |

## Canonical Variants

### Fill down a single column

```json
{
  "type": "UpDownFiller",
  "params": {
    "columns": ["sparse_label"],
    "up": false
  }
}
```

### Fill up a single column

```json
{
  "type": "UpDownFiller",
  "params": {
    "columns": ["sparse_label"],
    "up": true
  }
}
```
