---
name: block-routing-reference
description: "Param matrix and canonical examples for the ROUTING block."
---

# ROUTING Block

Evaluates conditions to decide which block to run next. Supports three modes: clause-based (CEL), LLM dispatch, and expression dispatch.

## Routing Modes

| Mode | How it decides |
|------|----------------|
| `CLAUSES` | Ordered if-then clauses evaluated top-to-bottom; first match wins |
| `LLM_DISPATCH` | An LLM is called with a prompt to determine the next block |
| `EXPRESSION_DISPATCH` | A single CEL expression calculates the next block ID |

## Param Matrix

### Shared params (all modes)

| Param | Required | Type | Notes |
|-------|----------|------|-------|
| `id` | yes | string | Unique block identifier |
| `type` | yes | `"ROUTING"` | |
| `routingMode` | yes | string | `"CLAUSES"`, `"LLM_DISPATCH"`, or `"EXPRESSION_DISPATCH"` |

### CLAUSES mode params

| Param | Required | Notes |
|-------|----------|-------|
| `clausesBasedDecisions` | yes | Ordered list of clause objects |
| `defaultNextBlockIfNoClauseMatch` | yes | Fallback block if no clause matches |

### LLM_DISPATCH mode params

| Param | Required | Notes |
|-------|----------|-------|
| `llmId` | yes | LLM to call — discover with `list_llms` |
| `prompt` | yes | Instructions for the LLM on how to choose a path |
| `resultDispatch` | yes | Maps LLM keyword responses to block IDs |

`resultDispatch` entry shape:
```json
{"key": "path_a", "value": "<block_id>", "secret": false}
```
The LLM should respond with one of the `key` values; the routing block maps it to the corresponding block.

### EXPRESSION_DISPATCH mode params

| Param | Required | Notes |
|-------|----------|-------|
| `expression` | yes | CEL expression that evaluates to a block ID string |
| `validNextBlocksFromExpression` | yes | List of block IDs the expression may return (safety allowlist) |

## CLAUSES Mode — Clause Types

Clauses are evaluated in order; the first matching clause determines the next block. Available clause types:

| Clause type | Triggers when |
|-------------|---------------|
| `EXPRESSION` | A CEL expression evaluates to true |
| `STATE_HAS_KEYS` | All specified keys exist in state |
| `SCRATCHPAD_HAS_KEYS` | All specified keys exist in scratchpad |
| `TOOLS_CALLED` | All listed tools have been called in message history |

Clauses can be combined with `AND` / `OR` operators.

### Clause Object Shape (EXPRESSION type)

```json
{
  "clause": {
    "type": "EXPRESSION",
    "expression": {
      "language": "CEL",
      "expression": "state[\"decision\"] == \"approve\""
    }
  },
  "nextBlock": "target_block_id"
}
```

## CEL Expression Notes

CEL in routing supports: `==`, `!=`, `<`, `>`, `and`, `or`, `not`, `+`, `-`, `*`, `/`. Available functions: `string()`, `int()`, `len()`, `upper()`, `lower()`, `trim()`, `matches()`, `to_json()`, `parse_json()`. Available variables: `state`, `scratchpad`, `context`, `last_output`.

Known limitations observed in practice:
- `true` / `false` literals may fail with "Variable not defined" — use `1 == 1` / `1 == 0` instead
- `x.contains("y")` not supported — use `==` for exact match
- String concatenation with a list-valued state key will fail — ensure state values are strings before concatenating

## Recommended Pattern: LLM-Based Routing

For routing decisions that depend on text content, use an `LLM_REQUEST` block with `SAVE_TO_STATE` to extract a simple keyword, then check it with `==` in CEL:

1. `LLM_REQUEST` block: `outputMode: "SAVE_TO_STATE"`, `outputStateKey: "decision"`, prompt: "Respond with EXACTLY one word: approve or escalate"
2. `ROUTING` block: `state["decision"] == "approve"`

Alternatively, use `LLM_DISPATCH` mode and let the routing block itself call the LLM.

## Canonical Examples

### CLAUSES — route based on extracted decision
```json
{
  "id": "route",
  "type": "ROUTING",
  "routingMode": "CLAUSES",
  "clausesBasedDecisions": [
    {
      "clause": {
        "type": "EXPRESSION",
        "expression": {"language": "CEL", "expression": "state[\"decision\"] == \"approve\""}
      },
      "nextBlock": "approval_path"
    }
  ],
  "defaultNextBlockIfNoClauseMatch": "escalation_path"
}
```

### LLM_DISPATCH — let the LLM choose a path
```json
{
  "id": "route",
  "type": "ROUTING",
  "routingMode": "LLM_DISPATCH",
  "llmId": "<llm_id>",
  "prompt": "Based on the conversation, decide whether to take path_a or path_b.",
  "resultDispatch": [
    {"key": "path_a", "value": "block_a", "secret": false},
    {"key": "path_b", "value": "block_b", "secret": false}
  ]
}
```

### EXPRESSION_DISPATCH — CEL expression returns a block ID
```json
{
  "id": "route",
  "type": "ROUTING",
  "routingMode": "EXPRESSION_DISPATCH",
  "expression": "state[\"next_step\"]",
  "validNextBlocksFromExpression": ["block_a", "block_b"]
}
```

### CLAUSES — always-true passthrough (for testing)
```json
{
  "id": "route",
  "type": "ROUTING",
  "routingMode": "CLAUSES",
  "clausesBasedDecisions": [
    {
      "clause": {
        "type": "EXPRESSION",
        "expression": {"language": "CEL", "expression": "1 == 1"}
      },
      "nextBlock": "always_this_block"
    }
  ],
  "defaultNextBlockIfNoClauseMatch": "never_reached"
}
```

## Guardrails

1. **State key must exist** at evaluation time or CEL throws "Invalid index" error. Ensure upstream blocks set the key.
2. **Quote string literals** in CEL state comparisons: `state["key"] == "value"`.
3. **State values from Parallel blocks may be lists**, not strings — handle before routing on them.
4. **CLAUSES must use the nested clause wrapper** `{clause: {type, expression}, nextBlock}` — not a flat `{condition, expression, nextBlock}` shape.
