---
name: prepare-json-path-extractor
description: "Observed JSON patterns for the JSONPathExtractor prepare/shaker processor."
---

# JSONPathExtractor Processor

Extract JSON content of a column via JSONPath expression into new column. DSS local (stream) engine only; not SQL/Snowflake-pushable (Jayway JsonPath / json-smart Java library).

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `inCol` | yes | `string<column_name>` | Any existing column name | Input column containing JSON to extract from (JSON key is `inCol`, not `column`). |
| `outCol` | yes | `string<column_name>` | Any valid output column name | Output column to create (inserted after `inCol`); no JSONPath match = previous value kept. |
| `expression` | yes | `string<any>` | Valid JSONPath expression (Goessner syntax, e.g. `$.age`, `$.store.book[*].author`) | Compiled at init; invalid expression fails step. |
| `singleValue` | no | `boolean` | `true` \| `false` | Default `true`. `true`=path treated as single value (object/map results skipped; arrays emit first element only). `false`=full matched value (array/object) written, JSON-serialized. |

## Canonical Variant

```json
{
  "type": "JSONPathExtractor",
  "params": {
    "inCol": "json_object",
    "outCol": "json_object_extracted",
    "expression": "$",
    "singleValue": false
  }
}
```
