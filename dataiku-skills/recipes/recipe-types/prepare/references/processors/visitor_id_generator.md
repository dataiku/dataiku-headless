---
name: prepare-visitor-id-generator
description: "Observed JSON patterns for the VisitorIdGenerator prepare/shaker processor."
---

# VisitorIdGenerator Processor

Derive single best-effort visitor id column by hashing several per-row web-log fields together. In-database SQL pushdown Snowflake-only; else DSS local engine.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `outputColumn` | yes | `string<any>` | Any valid output column name | New column for generated visitor id; must not be blank. |
| `ipColumn` | no | `string<column_name>` | Any existing column name | IP-address input column. Supply at least one of the four input columns for a meaningful id. |
| `userAgentColumn` | no | `string<column_name>` | Any existing column name | User-Agent input column. |
| `browserLanguageColumn` | no | `string<column_name>` | Any existing column name | Browser-language input column. |
| `timezoneOffsetColumn` | no | `string<column_name>` | Any existing column name | Timezone-offset input column; empty string when unused. |

## Canonical Variant

```json
{
  "type": "VisitorIdGenerator",
  "params": {
    "browserLanguageColumn": "user_id",
    "outputColumn": "visitor_id",
    "ipColumn": "log_line",
    "userAgentColumn": "free_text",
    "timezoneOffsetColumn": ""
  }
}
```
