---
name: block-python-code-reference
description: "Param matrix and canonical examples for the PYTHON_CODE block."
---

# PYTHON_CODE Block

Runs custom Python code within the agent flow. The function yields output chunks streamed to the user and uses `defaultNextBlock` for routing.

## Param Matrix

| Param | Required | Type | Notes |
|-------|----------|------|-------|
| `id` | yes | string | Unique block identifier |
| `type` | yes | `"PYTHON_CODE"` | |
| `code` | yes | string | Python source code containing the function |
| `functionName` | no | string | Function name to call (default `"process"`) |
| `validNextBlocksFromCode` | no | list[string] | Block IDs this code may route to |
| `defaultNextBlock` | yes* | string | Next block after execution |

## Function Signature

```python
def process(context):
    # context is a SpanBuilder object
    yield "output text"  # streamed to user
    yield {"chunk": {"text": "more output"}}  # alternative format
```

## Context API (SpanBuilder)

| Access | Method | Notes |
|--------|--------|-------|
| Read state | `context.attributes.get('block_state', {})` | Returns a dict copy — **read-only** |
| Read current block ID | `context.attributes['block_state']['_currentBlockId']` | |
| Write state | **NOT POSSIBLE** | Mutations to the dict do not persist |
| Routing | Use `defaultNextBlock` on the block config | No `NextBlock` import available |
| Output | `yield "text"` or `yield {"chunk": {"text": "..."}}` | |

## Canonical Examples

### Read state and produce output
```python
def process(context):
    state = context.attributes.get('block_state', {})
    rate = state.get('base_rate', '6.75')
    yield f"The current base rate is {rate}%"
```

### Pass-through (no output, just routing)
```python
def process(context):
    pass
```

## Guardrails

1. **State is read-only.** `context.attributes['block_state']` is a copy. Mutations do NOT persist to downstream blocks or CEL expressions. To write state, use `SET_STATE_ENTRIES` or `LLM_REQUEST` with `SAVE_TO_STATE`.
2. **Use `yield`, not `return`.** The function is a generator. `return {"next_block": "..."}` does NOT work.
3. **No `NextBlock` import.** `from dataiku.agent_tools.next_block import NextBlock` does not exist. Routing is controlled by `defaultNextBlock` on the block config.
4. **Empty yield** (`yield ""`) may still produce visible whitespace in chat. Use `pass` for true no-op.
5. **Standard library only.** The code runs in the DSS Python environment. Third-party packages may not be available.
