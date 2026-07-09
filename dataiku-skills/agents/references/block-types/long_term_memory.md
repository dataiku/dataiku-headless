---
name: block-long-term-memory-reference
description: "Param matrix and canonical example for the LONG_TERM_MEMORY block (plugin-required)."
---

# LONG_TERM_MEMORY Block

Persists memories across agent conversations and retrieves relevant ones at the start of a session. Requires the Dataiku Long-Term Memory plugin to be installed.

## Modes

| Mode | Behavior |
|------|---------|
| `STORE` | Saves key facts or summaries from the current conversation into persistent memory |
| `RETRIEVE` | Fetches relevant memories from previous conversations and injects them into context |

## Param Matrix

| Param | Required | Type | Notes |
|-------|----------|------|-------|
| `id` | yes | string | Unique block identifier |
| `type` | yes | `"LONG_TERM_MEMORY"` | Requires plugin |
| `mode` | yes | string | `"STORE"` or `"RETRIEVE"` |
| `llmId` | yes | string | LLM used to extract/summarize memories — discover with `list_llms` |
| `knowledgeBankRef` | yes | string | Knowledge bank used as the memory store |
| `extractionPrompt` | STORE only | string | Instructions for what to extract and remember |
| `retrievalQuery` | RETRIEVE only | string | Query to find relevant memories (can reference state/context) |
| `maxDocuments` | no | int | Max memories to retrieve (default 5) |
| `outputStateKey` | RETRIEVE only | string | State key to store retrieved memories |
| `nextBlock` | yes* | string | Next block |

## Canonical Examples

### RETRIEVE at conversation start
```json
{
  "id": "load_memories",
  "type": "LONG_TERM_MEMORY",
  "mode": "RETRIEVE",
  "llmId": "<llm_id>",
  "knowledgeBankRef": "<knowledge_bank_id>",
  "retrievalQuery": "Relevant context for this user's request",
  "maxDocuments": 5,
  "outputStateKey": "past_memories",
  "nextBlock": "main_react"
}
```

### STORE at conversation end
```json
{
  "id": "save_memories",
  "type": "LONG_TERM_MEMORY",
  "mode": "STORE",
  "llmId": "<llm_id>",
  "knowledgeBankRef": "<knowledge_bank_id>",
  "extractionPrompt": "Extract key facts, decisions, and user preferences from this conversation that would be useful to remember for future interactions.",
  "nextBlock": "final_output"
}
```

## Guardrails

1. **Plugin required.** This block type is unavailable if the Long-Term Memory plugin is not installed in DSS.
2. **Pair RETRIEVE + STORE.** Place RETRIEVE near the start of the flow to inject context; place STORE near the end to persist learnings.
3. **Knowledge bank must exist.** Create and configure the knowledge bank before referencing it here.
4. **RETRIEVE output is in state.** Reference retrieved memories via `state["past_memories"]` in downstream block prompts.
