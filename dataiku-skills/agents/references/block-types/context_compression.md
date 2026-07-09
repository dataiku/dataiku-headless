---
name: block-context-compression-reference
description: "Param matrix and canonical example for the CONTEXT_COMPRESSION block."
---

# CONTEXT_COMPRESSION Block

Uses an LLM to summarize earlier parts of the conversation, keeping recent messages intact. Reduces token usage for long conversations.

## Param Matrix

| Param | Required | Type | Notes |
|-------|----------|------|-------|
| `id` | yes | string | Unique block identifier |
| `type` | yes | `"CONTEXT_COMPRESSION"` | |
| `llmId` | yes | string | LLM for summarization — discover with `list_llms` |
| `activeBufferSize` | no | int | Number of recent messages to keep uncompressed (default 5) |
| `compressionTriggerChars` | no | int | Compress when conversation exceeds this length (default 1000) |
| `appliesToInitial` | no | bool | Compress initial conversation messages |
| `appliesToGenerated` | no | bool | Compress generated messages |
| `completionSettings` | no | object | Completion settings |
| `nextBlock` | yes* | string | Next block |

## Canonical Example

```json
{
  "id": "compress",
  "type": "CONTEXT_COMPRESSION",
  "llmId": "<llm_id>",
  "activeBufferSize": 5,
  "compressionTriggerChars": 2000,
  "appliesToInitial": true,
  "appliesToGenerated": true,
  "completionSettings": {"stopSequences": [], "outputTrajectory": true},
  "nextBlock": "route"
}
```

## Guardrails

1. Place after blocks that generate large amounts of internal conversation (e.g., after reflection loops).
2. `activeBufferSize` controls how many recent messages are kept verbatim — set higher if downstream blocks need recent tool results.
