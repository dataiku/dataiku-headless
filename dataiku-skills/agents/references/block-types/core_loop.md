---
name: block-core-loop-reference
description: "Param matrix and canonical example for the CORE_LOOP block (formerly STANDARD_REACT)."
---

# CORE_LOOP Block

The core AI loop. The LLM reasons, optionally calls tools, and repeats until it produces a final response or hits the max iteration limit.

## Param Matrix

| Param | Required | Type | Notes |
|-------|----------|------|-------|
| `id` | yes | string | Unique block identifier |
| `type` | yes | `"CORE_LOOP"` | |
| `llmId` | yes | string | LLM identifier — discover with `list_llms` |
| `systemPromptAfterHistory` | no | string | System prompt injected after conversation history |
| `passConversationHistory` | no | bool | Pass prior conversation to the LLM |
| `tools` | no | list | Tools available to the LLM (see tool object below) |
| `maxLoopIterations` | no | int | Max reasoning loops (default 25) |
| `maxParallelToolExecutions` | no | int | Max parallel tool calls per loop (default 2) |
| `stateAware` | no | bool | Expose state as virtual tools — the LLM can actively read and write state during the loop |
| `scratchpadAware` | no | bool | Expose scratchpad as virtual tools — the LLM can actively read and write scratchpad during the loop |
| `exitConditions` | no | list | Conditions to exit the loop early |
| `defaultNextBlock` | yes* | string | Next block after completion (*dead end without it) |
| `completionSettings` | no | object | `{stopSequences, outputTrajectory, reasoningEffort}` |
| `streamOutput` | no | bool | Stream response to user in real-time |
| `outputMode` | no | string | `"ADD_TO_MESSAGES"` or `"SAVE_TO_STATE"` |
| `outputKey` | no | string | Companion state key when `outputMode` is `"SAVE_TO_STATE"` |
| `outputStateKey` | no | string | State key when outputMode is `"SAVE_TO_STATE"` |

## Tool Object Shape

```json
{
  "type": "EXPLICIT_TOOL",
  "toolRef": "<tool_id>",
  "forwardContext": true,
  "returnArtifacts": false,
  "returnSources": false,
  "enableSetArgs": false,
  "setArgs": [],
  "outputHandling": "ADD_TO_MESSAGES",
  "treatAsJSON": false
}
```

## Exit Conditions

`exitConditions` is a list of condition objects. Each condition has its own `nextBlock` — when the condition is met, the loop exits and routes to that block (bypassing `defaultNextBlock`). Available types:

| Type | Exits when | Key param |
|------|-----------|-----------|
| `STATE_HAS_KEYS` | All specified keys exist in state | `stateKeys: [...]` |
| `SCRATCHPAD_HAS_KEYS` | All specified keys exist in scratchpad | `scratchpadKeys: [...]` |
| `TOOLS_CALLED` | All listed tools have been called at least once | `toolIds: [...]` |
| `EXPRESSION` | A CEL expression evaluates to true | `expression: {...}` |

```json
[
  {
    "type": "STATE_HAS_KEYS",
    "stateKeys": ["decision", "summary"],
    "nextBlock": "process_decision"
  },
  {
    "type": "TOOLS_CALLED",
    "toolIds": ["<tool_id>"],
    "nextBlock": "after_tool"
  },
  {
    "type": "EXPRESSION",
    "expression": {"language": "CEL", "expression": "state[\"score\"] > 0"},
    "nextBlock": "high_score_path"
  }
]
```

## Canonical Example

```json
{
  "id": "my_react_block",
  "type": "CORE_LOOP",
  "llmId": "<llm_id>",
  "systemPromptAfterHistory": "You are a helpful assistant. Use the tools available.",
  "passConversationHistory": true,
  "tools": [
    {
      "type": "EXPLICIT_TOOL",
      "toolRef": "my_tool_id",
      "forwardContext": true,
      "returnArtifacts": false,
      "returnSources": false,
      "enableSetArgs": false,
      "setArgs": [],
      "outputHandling": "ADD_TO_MESSAGES",
      "treatAsJSON": false
    }
  ],
  "maxLoopIterations": 5,
  "maxParallelToolExecutions": 1,
  "stateAware": false,
  "scratchpadAware": false,
  "exitConditions": [],
  "defaultNextBlock": "next_block",
  "completionSettings": {"stopSequences": [], "outputTrajectory": true},
  "streamOutput": true,
  "outputMode": "ADD_TO_MESSAGES"
}
```

## Guardrails

1. Set `maxLoopIterations` to a reasonable value (3-10) to avoid runaway loops.
2. When using `SAVE_TO_STATE`, the LLM's final text response is saved — not tool results.
3. Set both `outputKey` and `outputStateKey` to the same value when using `SAVE_TO_STATE`.
4. `passConversationHistory` is important in parallel blocks so child blocks see prior context.
5. Cortex LLMs may reject conversation history containing tool messages from prior blocks. Use OpenAI-hosted LLMs if this occurs.
6. `stateAware`/`scratchpadAware` give the LLM write access — use when you want the LLM to decide what to persist (e.g. flag a prospect as identified). For deterministic writes, use SET_STATE_ENTRIES instead.
