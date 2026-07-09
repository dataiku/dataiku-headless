---
name: block-manual-tool-call-reference
description: "Param matrix and canonical example for the MANUAL_TOOL_CALL block."
---

# MANUAL_TOOL_CALL Block

Calls a tool directly with pre-specified arguments. No LLM is involved — the arguments are set statically via CEL expressions.

## Param Matrix

| Param | Required | Type | Notes |
|-------|----------|------|-------|
| `id` | yes | string | Unique block identifier |
| `type` | yes | `"MANUAL_TOOL_CALL"` | |
| `tool` | yes | object | Tool configuration (see below) |
| `outputMode` | no | string | `"ADD_TO_MESSAGES"` or `"SAVE_TO_STATE"` |
| `outputStateKey` | no | string | State key when SAVE_TO_STATE |
| `nextBlock` | yes* | string | Next block |

## Tool Object Shape

```json
{
  "type": "EXPLICIT_TOOL",
  "toolRef": "<tool_id>",
  "setArgs": [
    {"key": "query", "value": "\"What is the default rate by state?\"", "secret": false}
  ]
}
```

**NOT** `{argName, valueMode, staticValue}` — that format is wrong despite appearing in some documentation.

## setArgs Value Gotcha

Values are CEL expressions, same rules as SET_STATE_ENTRIES:

| What you want | Wrong | Right |
|---------------|-------|-------|
| String query | `"my query"` | `"\"my query\""` |
| State reference | `"\"state.key\""` | `state["key"]` |

## Canonical Example

```json
{
  "id": "get_stats",
  "type": "MANUAL_TOOL_CALL",
  "tool": {
    "type": "EXPLICIT_TOOL",
    "toolRef": "<tool_id>",
    "setArgs": [
      {"key": "query", "value": "\"What is the average loan amount by state?\"", "secret": false}
    ]
  },
  "outputMode": "SAVE_TO_STATE",
  "outputStateKey": "market_stats",
  "nextBlock": "next_block"
}
```

## Guardrails

1. **Double-quote string values in setArgs.** Same CEL quoting rules as SET_STATE_ENTRIES.
2. **Consider using CORE_LOOP instead** if the query should be dynamic (based on conversation context). MANUAL_TOOL_CALL is only for truly static invocations.
3. **`passConversationHistory` is not supported** on this block type. DSS silently strips it.
