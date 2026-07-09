---
name: block-set-state-entries-reference
description: "Param matrix and canonical example for the SET_STATE_ENTRIES block."
---

# SET_STATE_ENTRIES Block

Sets key-value pairs in the agent's conversation-scope state. State persists for the duration of the conversation and is accessible by downstream blocks (CEL expressions, state-aware LLM blocks, Jinja templates).

## Param Matrix

| Param | Required | Type | Notes |
|-------|----------|------|-------|
| `id` | yes | string | Unique block identifier |
| `type` | yes | `"SET_STATE_ENTRIES"` | |
| `entriesToSet` | yes | list | List of entry objects (see below) |
| `nextBlock` | yes* | string | Next block (*dead end without it) |

## Entry Object Shape

```json
{"key": "my_key", "value": "\"my string value\"", "secret": false}
```

## CEL Value Gotchas

**Values are CEL expressions, not plain strings.** This is the #1 source of errors.

| What you want | Wrong | Right |
|---------------|-------|-------|
| String `"hello"` | `"hello"` (CEL variable lookup) | `"\"hello\""` |
| String `"a, b, c"` | `"a, b, c"` (CEL tuple!) | `"\"a, b, c\""` |
| Number `6.75` | `"6.75"` (string in CEL) | `"6.75"` (numeric — but downstream may need string) |
| String `"6.75"` | `"6.75"` | `"\"6.75\""` |

## Canonical Example

```json
{
  "id": "init",
  "type": "SET_STATE_ENTRIES",
  "entriesToSet": [
    {"key": "loan_products", "value": "\"fixed_30yr, fixed_15yr, arm_5_1\"", "secret": false},
    {"key": "base_rate", "value": "\"6.75\"", "secret": false},
    {"key": "api_key", "value": "\"sk-abc123\"", "secret": true}
  ],
  "nextBlock": "intake"
}
```

## Guardrails

1. **Always double-quote string values.** An unquoted comma creates a CEL tuple. An unquoted word is a variable lookup.
2. **Secret entries** (`"secret": true`) are not visible in traces or conversation history.
3. State values set here are accessible in ROUTING CEL via `state["key"]`, in Jinja via `{{ state.key }}`, and in state-aware LLM blocks.
