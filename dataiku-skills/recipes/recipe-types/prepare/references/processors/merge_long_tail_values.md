---
name: prepare-merge-long-tail-values
description: "Observed JSON patterns for the MergeLongTailValues prepare/shaker processor."
---

# MergeLongTailValues Processor

Keep only most frequent values in a categorical column; fold rarer values into single replacement bucket. SQL/in-database or native Spark engine only; local DSS streaming engine cannot execute it and passes rows through unchanged (no-op).

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `appliesTo` | yes | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param. |
| `columns` | yes | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param. |
| `appliesToPattern` | conditional | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param; required when `appliesTo` is `PATTERN`. |
| `thresholdMode` | yes | `enum` | `COUNT` \| `CUM_RATIO` | `COUNT`=keep top `countThreshold` most frequent; `CUM_RATIO`=keep values until cumulative share exceeds `cumRatioThreshold`. |
| `countThreshold` | conditional | `integer` | Positive integer | Count of most-frequent values to keep; required when `thresholdMode` is `COUNT`. Default `10`. |
| `cumRatioThreshold` | conditional | `number` | `0.0`-`1.0` | Cumulative frequency ratio cutoff; required when `thresholdMode` is `CUM_RATIO`. Default `0.80`. |
| `replacementValue` | no | `string<any>` | Any text value | Written into cells whose original value not kept; empty=those cells blanked. |

## Canonical Variants

### Keep top-N by count

```json
{
  "type": "MergeLongTailValues",
  "params": {
    "cumRatioThreshold": 0.8,
    "columns": ["category"],
    "thresholdMode": "COUNT",
    "appliesTo": "SINGLE_COLUMN",
    "countThreshold": 2,
    "replacementValue": "OTHER"
  }
}
```

### Keep by cumulative ratio

```json
{
  "type": "MergeLongTailValues",
  "params": {
    "cumRatioThreshold": 0.8,
    "columns": ["category"],
    "thresholdMode": "CUM_RATIO",
    "appliesTo": "SINGLE_COLUMN",
    "countThreshold": 10,
    "replacementValue": "OTHER"
  }
}
```
