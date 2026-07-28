# Structured Agent (`STRUCTURED_AGENT`)

A structured agent is a block graph. Each block performs one unit of work and passes control through `nextBlock` or `defaultNextBlock`. LLMs are configured on the blocks that use them, not on the agent as a whole.

Use a structured agent for deterministic branching, parallel work, explicit memory, quality loops, or guaranteed pre/post-processing.

## Memory Model

| Layer | Scope | Persists across turns? | Use for |
| --- | --- | --- | --- |
| **State** | Entire conversation | Yes | Values needed by later turns. |
| **Scratchpad** | Current block sequence | No | Temporary values in the current turn. It is isolated per `FOR_EACH` iteration and `PARALLEL` branch. |
| **Conversation history** | Per block | Configurable | Messages provided to an LLM block. |

Decision rule: use **state** for later turns, **scratchpad** for the current turn, and **conversation history** for LLM message context.

## Turn Lifecycle

Every turn can include pre-turn blocks, the main graph from its entry block, and post-turn blocks. When a turn ends without a `nextBlock`, subsequent turns can restart at the entry block, resume at the last restartable block, or use Smart mode to choose between them.

## Block Types

| Block | Purpose |
| --- | --- |
| `CORE_LOOP` | LLM and optional-tool loop with configurable exit conditions. |
| `LLM_REQUEST` | One LLM call for extraction, classification, summarization, or drafting. |
| `DELEGATE_TO_OTHER_AGENT` | Runs another agent's graph as a subtask. |
| `MANDATORY_TOOL_CALL` | Requires the LLM to call one specified tool. |
| `MANUAL_TOOL_CALL` | Calls a tool with CEL-expression arguments and no LLM. |
| `ROUTING` | Branches with clauses, LLM dispatch, or an allowlisted expression result. |
| `FOR_EACH` | Runs a block for each item in a CEL-evaluated list. |
| `PARALLEL` | Runs child blocks concurrently in isolated scratchpad scopes. |
| `REFLECTION` | Evaluates and improves, retries, or synthesizes generator output. |
| `SET_STATE_ENTRIES` | Deterministically writes conversation state. |
| `SET_SCRATCHPAD_ENTRIES` | Deterministically writes current-turn scratchpad values. |
| `CONTEXT_COMPRESSION` | Summarizes earlier conversation history. |
| `EMIT_OUTPUT` | Renders output to the user, history, state, or scratchpad. |
| `GENERATE_ARTIFACT` | Renders a downloadable Markdown, DOCX, or PDF artifact. |
| `PYTHON_CODE` | Runs custom Python with read-only state access. |
| `LONG_TERM_MEMORY` | Stores or retrieves cross-conversation memories through a plugin. |
| `SEMANTIC_FEEDBACK` | Routes corrections versus new requests through a plugin. |

## Important Constraints

- `LLM_REQUEST` is the usual way to save LLM output to state; `PYTHON_CODE` cannot write state.
- `MANDATORY_TOOL_CALL` does not pass conversation history to its LLM.
- `FOR_EACH` and `PARALLEL` cannot call tools that require human approval.
- Parallel branches cannot read each other's in-flight output. Writes to the same state key race, so use unique per-branch keys.
- `REFLECTION` runs its generator through `generatorBlockId`, outside the main chain.
