---
name: prepare-measure-normalize
description: "Observed JSON patterns for the MeasureNormalize prepare/shaker processor."
---

# MeasureNormalize Processor

Normalize physical-measurement strings (mass/volume/surface) to canonical units in place. SQL translation Snowflake-UDF-only; null/empty and values `Measure.normalize()` cannot parse pass through unchanged.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `column` | yes | `string<column_name>` | Any existing column of measurement strings | Column whose measurement (mass/volume/surface) is normalized in place; only parameter. |

## Canonical Variant

```json
{
  "type": "MeasureNormalize",
  "params": {
    "column": "measurement"
  }
}
```
