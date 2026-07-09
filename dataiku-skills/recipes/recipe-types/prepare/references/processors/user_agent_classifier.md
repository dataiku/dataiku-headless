---
name: prepare-user-agent-classifier
description: "Observed JSON patterns for the UserAgentClassifier prepare/shaker processor."
---

# UserAgentClassifier Processor

Parse a User-Agent string column into classified browser/device metadata.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `column` | yes | `string<column_name>` | Any valid input column name | Input column containing User-Agent strings to classify. |

## Canonical Variant

```json
{
  "type": "UserAgentClassifier",
  "params": {
    "column": "fake_user_agent"
  }
}
```

## Update Guidance

1. Read existing payload first and keep unrelated top-level keys untouched.
2. Modify only target `steps[]` entries for `UserAgentClassifier`.
3. Ensure `column` points to the raw User-Agent string column, not a derived classification column.
