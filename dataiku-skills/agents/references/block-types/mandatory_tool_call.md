---
name: block-mandatory-tool-call-reference
description: "Param matrix and canonical example for the MANDATORY_TOOL_CALL block."
---

# MANDATORY_TOOL_CALL Block

Like CORE_LOOP but the LLM is forced to call a specific tool. The LLM decides the arguments based on context and the system prompt.

## Param Matrix

| Param | Required | Type | Notes |
|-------|----------|------|-------|
| `id` | yes | string | Unique block identifier |
| `type` | yes | `"MANDATORY_TOOL_CALL"` | |
| `tool` | yes | object | Tool config (same shape as CORE_LOOP tool object) |
| `llmId` | yes | string | LLM identifier — discover with `list_llms` |
| `systemPrompt` | no | string | Instructions for the LLM |
| `stateAware` | no | bool | Include state in LLM context |
| `completionSettings` | no | object | Completion settings |
| `outputMode` | no | string | `"ADD_TO_MESSAGES"` or `"SAVE_TO_STATE"` |
| `outputStateKey` | no | string | State key when SAVE_TO_STATE |
| `nextBlock` | yes* | string | Next block |

## Canonical Example

```json
{
  "id": "create_ticket",
  "type": "MANDATORY_TOOL_CALL",
  "tool": {
    "type": "EXPLICIT_TOOL",
    "toolRef": "<tool_id>",
    "forwardContext": true,
    "returnArtifacts": false,
    "returnSources": false,
    "enableSetArgs": false,
    "setArgs": [],
    "outputHandling": "ADD_TO_MESSAGES",
    "treatAsJSON": false
  },
  "llmId": "<llm_id>",
  "systemPrompt": "Create a ticket with the customer details and assessment findings.",
  "stateAware": false,
  "completionSettings": {"stopSequences": [], "outputTrajectory": true},
  "outputMode": "ADD_TO_MESSAGES",
  "nextBlock": "next_block"
}
```

## Guardrails

1. **`passConversationHistory` is not supported.** DSS silently strips it. The LLM only sees the system prompt.
2. **Cortex LLMs may fail** with "assistant role in final position" if conversation history contains tool messages. Use OpenAI-hosted LLMs.
3. Consider using CORE_LOOP with a strong prompt instead if you need conversation context.
4. **`SAVE_TO_STATE` requires both `outputKey` AND `outputStateKey`** set to the same value.
