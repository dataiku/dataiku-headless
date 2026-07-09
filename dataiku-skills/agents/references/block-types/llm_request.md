---
name: block-llm-request-reference
description: "Param matrix and canonical examples for the LLM_REQUEST block."
---

# LLM_REQUEST Block

A single LLM call with no tool access. The LLM receives the system prompt and conversation history, generates a response, and moves on. Ideal for summarization, classification, extraction, or drafting.

## Param Matrix

| Param | Required | Type | Notes |
|-------|----------|------|-------|
| `id` | yes | string | Unique block identifier |
| `type` | yes | `"LLM_REQUEST"` | |
| `llmId` | yes | string | LLM identifier — discover with `list_llms` |
| `systemPromptAfterHistory` | no | string | System prompt injected after conversation history |
| `passConversationHistory` | no | bool | Pass prior conversation to the LLM |
| `outputMode` | no | string | `"ADD_TO_MESSAGES"` or `"SAVE_TO_STATE"` |
| `outputStateKey` | no | string | State key when outputMode is `"SAVE_TO_STATE"` |
| `completionSettings` | no | object | `{stopSequences, outputTrajectory}` |
| `streamOutput` | no | bool | Stream response to user |
| `nextBlock` | yes* | string | Next block (*dead end without it) |

## Canonical Examples

### Add response to conversation
```json
{
  "id": "draft_report",
  "type": "LLM_REQUEST",
  "llmId": "<llm_id>",
  "passConversationHistory": true,
  "systemPromptAfterHistory": "Summarize the key findings from the conversation.",
  "completionSettings": {"stopSequences": [], "outputTrajectory": true},
  "streamOutput": false,
  "outputMode": "ADD_TO_MESSAGES",
  "nextBlock": "next_block"
}
```

### Extract a decision to state (for routing)
```json
{
  "id": "extract_decision",
  "type": "LLM_REQUEST",
  "llmId": "<llm_id>",
  "passConversationHistory": true,
  "systemPromptAfterHistory": "Based on the assessment, respond with EXACTLY one word: approve or escalate",
  "completionSettings": {"stopSequences": [], "outputTrajectory": true},
  "streamOutput": false,
  "outputMode": "SAVE_TO_STATE",
  "outputStateKey": "decision",
  "nextBlock": "route"
}
```

## Guardrails

1. **SAVE_TO_STATE is the primary way to set state from LLM output.** Python code blocks cannot write to state. Use this block to extract values for downstream CEL routing.
2. When using SAVE_TO_STATE for routing, prompt the LLM to return exactly one word to avoid CEL parsing issues.
3. **`SAVE_TO_STATE` requires both `outputKey` AND `outputStateKey`** set to the same value.
4. **Chaining to a next block**: `LLM_REQUEST` supports `nextBlock` when `outputMode: "SAVE_TO_STATE"`. Without it the block is terminal and the turn ends. Pair with a downstream `SET_STATE_ENTRIES` using `parse_json(state["<outputKey>"])` to flatten the LLM's JSON response into top-level state keys.
5. The REFLECTION block uses LLM_REQUEST as its generator — see [reflection](reflection.md).
