---
name: block-for-each-reference
description: "Param matrix and canonical example for the FOR_EACH block."
---

# FOR_EACH Block

Iterates over a list (from a CEL expression) and runs a specified block once per item. Results are collected into state or scratchpad.

## Param Matrix

| Param | Required | Type | Notes |
|-------|----------|------|-------|
| `id` | yes | string | Unique block identifier |
| `type` | yes | `"FOR_EACH"` | |
| `sourceExpression` | yes | string | CEL expression returning a list |
| `blockIdToRepeat` | yes | string | Block ID to run per item |
| `forEachInputKey` | no | string | Scratchpad key under which the current item is available to the child block each iteration |
| `generatedOutputStorageLocation` | no | `"STATE"` or `"SCRATCHPAD"` | Where to store collected results |
| `targetOutputKey` | no | string | Key for collected results |
| `generatedStateKeys` | no | list[string] | State keys generated per iteration |
| `generatedScratchpadKeys` | no | list[string] | Scratchpad keys generated per iteration |
| `nextBlock` | yes* | string | Next block after all iterations |

## Canonical Example

```json
{
  "id": "process_each_item",
  "type": "FOR_EACH",
  "sourceExpression": "state[\"items\"]",
  "blockIdToRepeat": "process_item",
  "forEachInputKey": "current_item",
  "generatedOutputStorageLocation": "STATE",
  "targetOutputKey": "processed_results",
  "generatedStateKeys": [],
  "generatedScratchpadKeys": [],
  "nextBlock": "summarize"
}
```

## Guardrails

1. **`sourceExpression` must return a list** in CEL. If the state value is a string, this will fail.
2. **The child block reads the current item from scratchpad** under the key set by `forEachInputKey`. Make the child block `scratchpadAware` or read it explicitly.
3. **No human-in-the-loop inside FOR_EACH.** Tools with `requireHumanApproval: true` will fail when called from within a FOR_EACH child block.
4. **Each iteration gets its own scratchpad scope.** Scratchpad writes in one iteration are not visible to other iterations — use state with a unique key per item if cross-iteration data is needed.
