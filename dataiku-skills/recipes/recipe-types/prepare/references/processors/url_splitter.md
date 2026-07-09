---
name: prepare-url-splitter
description: "Observed JSON patterns for the URLSplitter prepare/shaker processor."
---

# URLSplitter Processor

Parse URL column into scheme/host/port/path/query-string/anchor parts, each gated by boolean flag. In-database SQL pushdown Snowflake-only; else DSS local engine.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `column` | yes | `string<column_name>` | Any existing column name | Input column of well-formed URLs (`scheme://hostname[:port][/path][?querystring][#anchor]`). |
| `extractScheme` | no | `boolean` | `true` \| `false` | Default `true`. `true` produces `<column>_scheme`. |
| `extractHost` | no | `boolean` | `true` \| `false` | Default `true`. `true` produces `<column>_host` (UI label "Extract hostname"). |
| `extractPort` | no | `boolean` | `true` \| `false` | Default `true`. `true` produces `<column>_port` (port as string; `-1` when absent). |
| `extractPath` | no | `boolean` | `true` \| `false` | Default `true`. `true` produces `<column>_path`. |
| `extractQueryString` | no | `boolean` | `true` \| `false` | Default `true`. `true` produces `<column>_querystring`. |
| `extractAnchor` | no | `boolean` | `true` \| `false` | Default `true`. `true` produces `<column>_anchor`. |

## Canonical Variant

```json
{
  "type": "URLSplitter",
  "params": {
    "extractScheme": true,
    "extractPath": true,
    "extractPort": true,
    "extractQueryString": true,
    "column": "url",
    "extractHost": true,
    "extractAnchor": true
  }
}
```
