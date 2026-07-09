---
name: block-set-scratchpad-entries-reference
description: "Param matrix and canonical example for the SET_SCRATCHPAD_ENTRIES block."
---

# SET_SCRATCHPAD_ENTRIES Block

Sets key-value pairs in the agent's scratchpad — very-short-term memory that resets each iteration. Same format and CEL quoting rules as SET_STATE_ENTRIES.

## Param Matrix

| Param | Required | Type | Notes |
|-------|----------|------|-------|
| `id` | yes | string | Unique block identifier |
| `type` | yes | `"SET_SCRATCHPAD_ENTRIES"` | |
| `entriesToSet` | yes | list | List of `{key, value, secret}` objects |
| `nextBlock` | yes* | string | Next block |

## Canonical Example

```json
{
  "id": "save_findings",
  "type": "SET_SCRATCHPAD_ENTRIES",
  "entriesToSet": [
    {"key": "combined_analysis", "value": "\"Analysis complete. See state keys for details.\"", "secret": false}
  ],
  "nextBlock": "reflect"
}
```

## Guardrails

1. **Same CEL quoting rules as SET_STATE_ENTRIES.** String literals need double-quoting: `"\"my string\""`.
2. Scratchpad is shorter-lived than state — it resets each iteration in loops.
