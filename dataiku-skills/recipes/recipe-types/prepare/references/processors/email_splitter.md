---
name: prepare-email-splitter
description: "Observed JSON patterns for the EmailSplitter prepare/shaker processor."
---

# EmailSplitter Processor

Split each email address into local-part and domain columns. In-database SQL pushdown is Snowflake-only; otherwise runs on the DSS local engine.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `column` | yes | `string<column_name>` | Any existing column name | Input email column; split on `@` into `<column>_localpart` and `<column>_domain`. Only param; non-valid-email inputs produce no output value. |

## Canonical Variant

```json
{
  "type": "EmailSplitter",
  "params": {
    "column": "email"
  }
}
```
