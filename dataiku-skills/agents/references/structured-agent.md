---
name: structured-agent-reference
description: "Configuration guide for STRUCTURED_AGENT — memory layers, turn structure, block management, block type catalog, and common patterns."
---

# Structured Agent (STRUCTURED_AGENT)

A visual agent with blocks chained in a directed graph (BLOCKS_GRAPH mode). Each block performs one unit of work and passes control to the next via `nextBlock` or `defaultNextBlock`. The LLM is configured per-block, not at the agent level.

## Memory: State, Scratchpad, and Conversation History

Three distinct memory layers — choosing the right one is critical:

| Layer | Scope | Persists across turns? | Use for |
|-------|-------|----------------------|---------|
| **State** | Entire conversation | Yes | Data that must survive multiple turns: extracted decisions, user details, intermediate results |
| **Scratchpad** | Single block sequence | No (resets each turn; isolated per FOR_EACH iteration) | Temporary working data within one turn; avoids polluting state |
| **Conversation history** | Per-block | Configurable (`passConversationHistory`) | The actual message thread passed to LLM blocks |

**Decision rule**: Later turn needs it → **state**. Current turn only → **scratchpad**. LLM message context → **conversation history**.

## Turn Structure

Each agent turn has three phases:

- **Pre-turn blocks** — Run at the start of every turn before the main flow. Use for: loading memories, checking permissions, detecting user feedback. Wire via `update_agent_settings` with `pre_turn_block_ids`.
- **Main flow** — The block graph starting from the entry block.
- **Post-turn blocks** — Run after main flow completes every turn. Use for: saving memories, guardrail checks, logging. Wire via `update_agent_settings` with `post_turn_block_ids`.

### Subsequent-turn behavior

When a turn ends (no `nextBlock`), DSS decides where the next turn starts:
- **Restart at entry block** — Always re-runs the full flow from the beginning.
- **Resume at last block** — Continues from where the previous turn ended (for "restartable" blocks like CORE_LOOP).
- **Smart mode** — An LLM determines whether user intent changed; restarts if yes, resumes if no.

## Building and Updating a Structured Agent

### Pattern: read → modify → write

Block management follows the same pattern as prepare recipe steps:

1. `get_agent_settings` — read the current `blocks` list from the response
2. Modify the blocks array in memory (add, update, remove, reorder, or replace)
3. `update_agent_settings(blocks=[...])` — write the full updated list back

This keeps the tool surface small and gives full control over block order and structure.

### Initial build

1. `create_agent` with `agent_type: "STRUCTURED_AGENT"`
2. `get_agent_settings` to inspect the fresh agent
3. `update_agent_settings` with `blocks=[...]` — pass all blocks at once, chained with `nextBlock` / `defaultNextBlock`
4. Set `entry_block_id` to the first block's ID (or pass it alongside `blocks`)
5. Optionally set `pre_turn_block_ids` / `post_turn_block_ids`
6. `run_agent` to test

### Updating an existing agent

1. `get_agent_settings` — read the current blocks list
2. Make changes in memory:
   - **Add**: append a new block dict to the list
   - **Update**: find the block by `id` and update its fields
   - **Remove**: filter out the block by `id`; update `entry_block_id` if it was the entry block
   - **Reorder**: rearrange the list order
3. `update_agent_settings(blocks=[...])` — write back

### Rewiring block references when changing a block ID

If you change a block's `id`, update every reference to the old ID in the blocks list before writing:

| Field | Found on |
|-------|---------|
| `nextBlock` | Most block types |
| `defaultNextBlock` | CORE_LOOP, PYTHON_CODE, ROUTING |
| `defaultNextBlockIfNoClauseMatch` | ROUTING (CLAUSES mode) |
| `clausesBasedDecisions[].nextBlock` | ROUTING (CLAUSES mode) |
| `blockIds[]` | PARALLEL |
| `generatorBlockId` | REFLECTION |
| `blockIdToRepeat` | FOR_EACH |
| `startingBlockId` | Top-level entry block (set via `entry_block_id`) |

## Block Type Reference

Before adding a block, read the block-type reference for required fields, payload shape, and gotchas:

| Block Type | Category | Description | Reference |
|------------|----------|-------------|-----------|
| CORE_LOOP | CoreAI | Iteratively reasons and calls tools until done or exit condition met | [core_loop](block-types/core_loop.md) |
| LLM_REQUEST | CoreAI | Single LLM call for summarization, extraction, or classification | [llm_request](block-types/llm_request.md) |
| DELEGATE_TO_OTHER_AGENT | CoreAI | Hands off conversation to another agent's full block graph | [delegate_to_other_agent](block-types/delegate_to_other_agent.md) |
| MANDATORY_TOOL_CALL | CoreAI | Forces LLM to call one specific tool; LLM decides the arguments | [mandatory_tool_call](block-types/mandatory_tool_call.md) |
| MANUAL_TOOL_CALL | CoreAI | Calls a tool with hardcoded CEL arguments; no LLM involved | [manual_tool_call](block-types/manual_tool_call.md) |
| ROUTING | Logic | Conditional branching: CLAUSES (CEL), LLM_DISPATCH, or EXPRESSION_DISPATCH | [routing](block-types/routing.md) |
| FOR_EACH | Logic | Runs a block once per item in a list; each iteration has its own scratchpad | [for_each](block-types/for_each.md) |
| PARALLEL | Logic | Executes multiple blocks simultaneously in separate threads | [parallel](block-types/parallel.md) |
| REFLECTION | Logic | Quality loop: CRITIQUE_AND_IMPROVE, CRITIQUE_OR_RETRY, or SYNTHESIZE | [reflection](block-types/reflection.md) |
| SET_STATE_ENTRIES | Memory | Sets conversation-scope state variables with CEL expressions | [set_state_entries](block-types/set_state_entries.md) |
| SET_SCRATCHPAD_ENTRIES | Memory | Sets short-term scratchpad values for the current turn | [set_scratchpad_entries](block-types/set_scratchpad_entries.md) |
| CONTEXT_COMPRESSION | Memory | Summarizes earlier conversation history to reduce token usage | [context_compression](block-types/context_compression.md) |
| EMIT_OUTPUT | Input/Output | Generates text from a template; routes to user, state, or scratchpad | [emit_output](block-types/emit_output.md) |
| GENERATE_ARTIFACT | Input/Output | Renders a template into a downloadable artifact (Markdown, DOCX, PDF) | [generate_artifact](block-types/generate_artifact.md) |
| PYTHON_CODE | Custom | Executes custom Python with read-only state access | [python_code](block-types/python_code.md) |
| LONG_TERM_MEMORY | Memory (plugin) | Persists and retrieves memories across agent conversations | [long_term_memory](block-types/long_term_memory.md) |
| SEMANTIC_FEEDBACK | Logic (plugin) | Detects feedback/corrections in user input and routes accordingly | [semantic_feedback](block-types/semantic_feedback.md) |

## Guardrails

1. **Inspect before mutating.** Always `get_agent_settings` before making changes.
2. **To change a block's type**, read the blocks list, replace the block dict in memory with the new type and fields, then write back the full list with `update_agent_settings`. Update any references to that block's ID per the rewiring table above.
3. **Test incrementally.** Use `run_agent` after each significant change.
4. **Cortex LLM limitations.** Cortex LLMs reject conversation history containing tool messages in non-tool-call contexts. Use OpenAI-hosted LLMs if this occurs.
5. **Micro-CEL is limited.** No `true`/`false` literals (use `1 == 1`), no `.contains()`. `string()`, `int()`, `len()`, and string functions do work. See the [routing reference](block-types/routing.md) for the full function list and known limitations.
6. **No human approval inside FOR_EACH or PARALLEL.** Tools with `requireHumanApproval: true` will fail when called from within these containers.
7. **CORE_LOOP and LLM_REQUEST state writes are stricter than they look.** When a block uses `outputMode: "SAVE_TO_STATE"`, set both `outputKey` and `outputStateKey` to the same value or some DSS runtimes error with `'outputKey'`.
8. **Avoid double-emitting answers.** If a `CORE_LOOP` or `LLM_REQUEST` block saves its final text to state for a downstream `EMIT_OUTPUT` block, keep the producer block non-user-visible (`streamOutput: false`, and do not rely on it to present the final answer directly). Otherwise the same answer may appear once from the producer block and again from the terminal `EMIT_OUTPUT`.

## Common Patterns

### LLM-based routing decision
Don't try to parse free-form LLM text in CEL. Instead:
1. `LLM_REQUEST` block with `outputMode: "SAVE_TO_STATE"` — prompt: "Respond with EXACTLY one word: approve or escalate"
2. `ROUTING` block with `state["decision"] == "approve"` in a CLAUSES expression

### Parallel research with state collection
1. Create individual `CORE_LOOP` blocks, each with `outputMode: "SAVE_TO_STATE"` and a unique `outputStateKey`
2. Wrap them in a `PARALLEL` block — state values from parallel children may be lists, not strings

### Reflection with a generator
Wire `previous_block → REFLECTION`. The reflection block runs its `generatorBlockId` internally — do NOT wire `previous → generator → reflection`. See the [reflection reference](block-types/reflection.md) for the critical wiring rule.

### Using another agent as a tool
Attach an `LLMMeshLLMQuery` agent tool pointing to the sub-agent, then reference it in a `CORE_LOOP` block's `tools` array. The LLM calls it like any other tool — useful for routing specialized queries to a domain expert agent.

### Per-turn memory with pre/post-turn blocks
- Pre-turn: `LONG_TERM_MEMORY` (RETRIEVE) or `SEMANTIC_FEEDBACK` to detect corrections before the main flow
- Post-turn: `LONG_TERM_MEMORY` (STORE) to persist key facts after every turn

### Outputs and state flow

  State shapes vary by producer — see [agent-tools.md](agent-tools.md) for each tool's `state[outputKey]` shape. Inspect real shape before wiring CEL paths.

  Reading state safely:

  - JSON strings: `parse_json(state["k"])` before subscripting.
  - Cast types explicitly; CEL's `int()` / `string()` / `number()` helpers are limited.
  - Pass current state into LLM prompts via Jinja (`{{ state.x }}`) so the model preserves existing values.

  LLM-to-state via two-block handoff (direct `__dku_state_set__` from `CORE_LOOP` is unreliable across model families — flattened kwargs,
  wrapper-key nesting, parallel-call breakage):

  1. `LLM_REQUEST` with `outputMode: "SAVE_TO_STATE"` and `outputKey == outputStateKey`. Prompt for one JSON object, no prose, no markdown.
  2. `SET_STATE_ENTRIES` calling `parse_json(state["<outputKey>"])`, projecting each field to a top-level key.

  Pitfalls: markdown-fenced output (add "JSON only" to prompt); field omission (pass current values via Jinja, tell LLM to preserve); type
  coercion (cast after `parse_json`).
