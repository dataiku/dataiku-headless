---
name: prepare-boolean-not
description: "Observed JSON patterns for the BooleanNot prepare/shaker processor."
---

# BooleanNot Processor

Negate a boolean column in place: true<->false. Not SQL-translatable (stream engine only); null/empty values and any token not recognized as boolean pass through unchanged (original casing preserved).

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `column` | yes | `string<column_name>` | Any existing boolean-valued column name | Boolean column to negate in place; only parameter. |

## Canonical Variant

```json
{
  "type": "BooleanNot",
  "params": {
    "column": "bool_flag"
  }
}
```
