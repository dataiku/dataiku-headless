---
name: block-delegate-to-other-agent-reference
description: "Param matrix and canonical example for the DELEGATE_TO_OTHER_AGENT block."
---

# DELEGATE_TO_OTHER_AGENT Block

Delegates the conversation to another agent. The delegated agent runs its full flow and returns a response.

## Param Matrix

| Param | Required | Type | Notes |
|-------|----------|------|-------|
| `id` | yes | string | Unique block identifier |
| `type` | yes | `"DELEGATE_TO_OTHER_AGENT"` | |
| `agentRef` | yes | string | Agent ID to delegate to |
| `streamOutput` | no | bool | Stream delegated agent's response |
| `outputMode` | no | string | `"ADD_TO_MESSAGES"` |
| `nextBlock` | yes* | string | Next block after delegation returns |

## Canonical Example

```json
{
  "id": "delegate_review",
  "type": "DELEGATE_TO_OTHER_AGENT",
  "agentRef": "<agent_id>",
  "streamOutput": false,
  "outputMode": "ADD_TO_MESSAGES",
  "nextBlock": "next_block"
}
```

## Guardrails

1. **The delegated agent must exist and be active in the same DSS instance.** Use `list_agents` to verify the `agentRef` is valid before wiring this block.
2. **Prefer `LLMMeshLLMQuery` tool for sub-tasks.** If you just need a specialized LLM call, an `LLMMeshLLMQuery` agent tool attached to a CORE_LOOP block is simpler. Use DELEGATE_TO_OTHER_AGENT when you need the full block graph of another agent to execute.
3. Consider having a fallback routing path if delegation may fail.
