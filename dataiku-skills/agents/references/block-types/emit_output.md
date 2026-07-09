---
name: block-emit-output-reference
description: "Param matrix and canonical example for the EMIT_OUTPUT block."
---

# EMIT_OUTPUT Block

Generates text from a template and routes it to one or more destinations: the user, conversation history, state, or scratchpad. Called "Generate Text Output" in the DSS UI.

## Param Matrix

| Param | Required | Type | Notes |
|-------|----------|------|-------|
| `id` | yes | string | Unique block identifier |
| `type` | yes | `"EMIT_OUTPUT"` | |
| `templateType` | yes | string | `"JINJA"` or `"CEL_EXPANSION"` |
| `template` | yes | string | Template content |
| `outputMode` | no | string | Where to send the output (see Output Modes below) |
| `outputStateKey` | no | string | State key when `outputMode` is `"SAVE_TO_STATE"` |
| `outputScratchpadKey` | no | string | Scratchpad key when `outputMode` is `"SAVE_TO_SCRATCHPAD"` |
| `addToMessages` | no | bool | Also add output to conversation history |
| `streamOutput` | no | bool | Stream output to the user in real-time |
| `nextBlock` | no | string | Next block (omit to end the flow) |

## Output Modes

| Mode | Behavior |
|------|---------|
| `"ADD_TO_MESSAGES"` (default) | Sends text to the user and adds to conversation history |
| `"SAVE_TO_STATE"` | Saves text to `outputStateKey` in state (not shown to user) |
| `"SAVE_TO_SCRATCHPAD"` | Saves text to `outputScratchpadKey` in scratchpad |

## Template Types

- **CEL_EXPANSION**: Plain text with `${state.key}` interpolation.
- **JINJA**: Full Jinja2 with `{{ state.key }}`, conditionals, loops.

## Canonical Examples

### Terminal output to user
```json
{
  "id": "final_output",
  "type": "EMIT_OUTPUT",
  "templateType": "CEL_EXPANSION",
  "template": "Your application has been processed. Decision: ${state.decision}",
  "outputMode": "ADD_TO_MESSAGES"
}
```

### Save to state for downstream use
```json
{
  "id": "format_summary",
  "type": "EMIT_OUTPUT",
  "templateType": "JINJA",
  "template": "Summary for {{ state.name }}:\n{% for item in state.items %}- {{ item }}\n{% endfor %}",
  "outputMode": "SAVE_TO_STATE",
  "outputStateKey": "formatted_summary",
  "nextBlock": "send_email"
}
```

## Guardrails

1. **Omit `nextBlock` to end the turn.** Include `nextBlock` to continue the flow after generating text.
2. **`SAVE_TO_STATE` does not show output to the user.** Use this when you need to format text for a downstream block (e.g., fill a template before sending an email).
3. Jinja templates access state via `{{ state.key }}` — state must be populated by upstream blocks.
