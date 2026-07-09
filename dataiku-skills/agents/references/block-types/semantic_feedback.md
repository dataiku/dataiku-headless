---
name: block-semantic-feedback-reference
description: "Param matrix and canonical example for the SEMANTIC_FEEDBACK block (plugin-required)."
---

# SEMANTIC_FEEDBACK Block

Detects when a user message is a correction or feedback on the agent's previous output, then injects the prior conversation state so the agent can revise rather than restart. Requires the Dataiku Semantic Feedback plugin to be installed.

## How It Works

1. The block receives the current user message.
2. An LLM classifies whether it is a feedback/correction or a new request.
3. If feedback is detected: the block restores relevant prior state and routes to a revision flow.
4. If not feedback: the block routes to the normal flow unchanged.

## Param Matrix

| Param | Required | Type | Notes |
|-------|----------|------|-------|
| `id` | yes | string | Unique block identifier |
| `type` | yes | `"SEMANTIC_FEEDBACK"` | Requires plugin |
| `llmId` | yes | string | LLM used for feedback detection — discover with `list_llms` |
| `detectionPrompt` | no | string | Instructions for the feedback detection LLM |
| `feedbackNextBlock` | yes | string | Block to run when feedback is detected |
| `noFeedbackNextBlock` | yes | string | Block to run when no feedback is detected |

## Canonical Example

```json
{
  "id": "detect_feedback",
  "type": "SEMANTIC_FEEDBACK",
  "llmId": "<llm_id>",
  "detectionPrompt": "Determine if the user's message is a correction or refinement of the previous response, or a new unrelated request.",
  "feedbackNextBlock": "revise_output",
  "noFeedbackNextBlock": "main_react"
}
```

## Guardrails

1. **Plugin required.** This block type is unavailable if the Semantic Feedback plugin is not installed in DSS.
2. **Place at the entry point.** SEMANTIC_FEEDBACK should typically be the entry block or the first block after conversation history is established.
3. **Revision flow should reference prior state.** When routing to `feedbackNextBlock`, ensure the revision block uses `stateAware: true` or reads from state to access the prior output being corrected.
