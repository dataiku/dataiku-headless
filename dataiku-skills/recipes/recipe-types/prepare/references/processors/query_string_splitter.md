---
name: prepare-query-string-splitter
description: "Observed JSON patterns for the QueryStringSplitter prepare/shaker processor."
---

# QueryStringSplitter Processor

Explode HTTP query string into separate optionally-prefixed column per parameter key. Column set is data-dependent (one new column per distinct key); in-database SQL pushdown is Snowflake-only and needs a recorded design-time run, else DSS local engine.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `column` | yes | `string<column_name>` | Any existing column name | Input column holding HTTP query string (part after `?`). |
| `prefix` | no | `string<any>` | Any free-text prefix | Prepended to each output column name (output column = `prefix` + key). Unset = output columns named by bare keys. |

## Canonical Variant

```json
{
  "type": "QueryStringSplitter",
  "params": {
    "prefix": "qs_",
    "column": "query_string"
  }
}
```
