---
name: prepare-grok-processor
description: "Observed JSON patterns for the GrokProcessor prepare/shaker processor."
---

# GrokProcessor

Parse free-text string column with Grok expression; emit one output column per named capture plus optional match-flag column. No SQL translation; DSS/stream engine only. Composite patterns (`HTTPDATE`, `NUMBER`) expand into own sub-capture columns, so output column count can exceed top-level named captures.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `sourceColumn` | yes | `string<column_name>` | Any existing column name | Input column the Grok expression applies to. |
| `grokPattern` | yes | `string<any>` | A Grok expression with `%{PATTERN:name}` named captures | Each captured variable=new output column; `UNWANTED` variable ignored. Invalid patterns fail validation. |
| `found_col` | no | `boolean` | `true` \| `false` | `true`=add boolean column flagging match. Default `false`. |
| `found_col_name` | conditional | `string<any>` | Any valid output column name | Match-flag column name; required when `found_col`=`true`. Default `found`. |

## Canonical Variant

```json
{
  "type": "GrokProcessor",
  "params": {
    "sourceColumn": "log_line",
    "grokPattern": "%{IPORHOST:client_ip} %{USER:ident} %{USER:auth} \\[%{HTTPDATE:log_ts}\\] \"%{WORD:http_method} %{NOTSPACE:request} HTTP/%{NUMBER:http_version}\" %{NUMBER:status} %{NUMBER:bytes}",
    "found_col": true,
    "found_col_name": "log_matched"
  }
}
```
