---
name: dataiku-agents
description: Inspect Dataiku DSS agents and use the results as context for Cobuild. Documents agent types (simple/code/structured) and the structured agent's memory model and block-type catalog — grounding for interpreting `get_agent_settings` output and writing precise Cobuild prompts. Use when an agent must list agents, inspect agent settings, versions, or tools before asking Cobuild to create or modify project assets.
---

# Agent Inspection

Use this skill to inspect existing agents and supporting agent-tool configuration.

## Workflow

1. Use `list_agents` to discover agents in the project.
2. Use `get_agent_settings` to inspect an agent before any Cobuild prompt about modifying it. Use the reference material below to interpret the returned agent type, blocks, and tool config.
3. Use `list_agent_versions` when version context matters.
4. Use `list_agent_tools` and `get_agent_tool_settings` to inspect available tool objects.
5. If the task requires creating, updating, deleting, or running agents, route that work through `./dataiku-skills/cobuild/SKILL.md`. Use the domain knowledge below to write a precise, well-grounded natural-language Cobuild prompt (correct agent type, correct block types).

## Preferred Tools

- `list_agents`
- `get_agent_settings`
- `list_agent_versions`
- `list_agent_tools`
- `get_agent_tool_settings`

## Safety Rules

- Never invent agent ids or agent tool names.
- Keep this skill focused on inspection and Cobuild grounding. Do not attempt direct `create_agent`/`update_agent_settings`/`replace_agent_block`-style writes — there is no such tool in this environment; all mutations route through Cobuild.

---

# Agent Types

DSS agents come in three types (the `agent_type` field returned by `get_agent_settings`):

| Type | `agent_type` value | What it is | Use when |
|------|---------------------|------------|----------|
| **Simple agent** | `TOOLS_USING_AGENT` | A single ReAct loop: the LLM sees the full conversation, picks tools based on their `additionalDescriptionForLLM`, calls them, reads results, and repeats until it decides it's done. No state or scratchpad — memory is conversation history only. No explicit exit conditions. | Straightforward tool-using assistants where the LLM itself should drive tool selection and looping, and no deterministic branching/parallelism/guaranteed post-processing is needed. |
| **Code agent** | `PYTHON_AGENT` | A fully custom Python class subclassing `BaseLLM` (from `dataiku.llm.python`), implementing exactly one of `process`/`aprocess`/`process_stream`/`aprocess_stream`. DSS invokes the class directly — no built-in LLM loop, tool dispatch, or memory management; all of that is custom code. | Only when capabilities are unavailable through visual agents: custom streaming protocols, multimodal processing, external SDK integration, bespoke control flow. Prefer simple or structured agents otherwise. |
| **Structured agent** | `STRUCTURED_AGENT` (BLOCKS_GRAPH mode) | A visual agent: blocks chained in a directed graph, each doing one unit of work and passing control via `nextBlock`/`defaultNextBlock`. The LLM is configured per-block, not at the agent level. | Deterministic branching, parallel work, guaranteed pre/post-processing, explicit memory management, quality loops (reflection), or any workflow that needs more control than a single ReAct loop offers. |

---

# Structured Agent: Memory Model

Three distinct memory layers — the layer in play changes how a value should be interpreted when reading `get_agent_settings`/traces:

| Layer | Scope | Persists across turns? | Use for |
|-------|-------|------------------------|---------|
| **State** | Entire conversation | Yes | Data that must survive multiple turns: extracted decisions, user details, intermediate results |
| **Scratchpad** | Single block sequence | No — resets each turn; isolated per FOR_EACH iteration / PARALLEL branch | Temporary working data within one turn; avoids polluting state |
| **Conversation history** | Per-block | Configurable (`passConversationHistory`) | The actual message thread passed to LLM blocks |

Decision rule when interpreting or specifying design intent: needed by a *later* turn → **state**; needed only in the *current* turn → **scratchpad**; needed as LLM message context → **conversation history**.

## Turn Structure

Each agent turn has three phases:

- **Pre-turn blocks** — run at the start of every turn, before the main flow. Typical use: loading memories, checking permissions, detecting user feedback.
- **Main flow** — the block graph starting from the entry block.
- **Post-turn blocks** — run after the main flow completes, every turn. Typical use: saving memories, guardrail checks, logging.

### Subsequent-turn behavior

When a turn ends without a `nextBlock`, DSS decides where the next turn starts:
- **Restart at entry block** — always re-runs the full flow from the beginning.
- **Resume at last block** — continues from where the previous turn ended (for "restartable" blocks like CORE_LOOP).
- **Smart mode** — an LLM determines whether user intent changed; restarts if yes, resumes if no.

---

# Block Types (STRUCTURED_AGENT)

Block type catalog — use this to interpret a `get_agent_settings` blocks list, or to name exact block types in a Cobuild prompt.

| Block Type | Category | Description |
|------------|----------|--------------|
| CORE_LOOP | CoreAI | The core AI loop: LLM reasons, optionally calls tools, repeats until done or `maxLoopIterations`/an exit condition is hit. `exitConditions` (STATE_HAS_KEYS, SCRATCHPAD_HAS_KEYS, TOOLS_CALLED, EXPRESSION) can each route to a different next block, bypassing `defaultNextBlock`. |
| LLM_REQUEST | CoreAI | A single LLM call, no tool access — for summarization, classification, extraction, or drafting. The primary way to get LLM output into state (`outputMode: SAVE_TO_STATE`), since Python code blocks can't write state. |
| DELEGATE_TO_OTHER_AGENT | CoreAI | Hands the conversation to another agent's full block graph, which runs and returns a response. |
| MANDATORY_TOOL_CALL | CoreAI | Like CORE_LOOP but the LLM is forced to call one specific tool; the LLM only decides the arguments. `passConversationHistory` is silently unsupported — the LLM sees only the system prompt. |
| MANUAL_TOOL_CALL | CoreAI | Calls a tool with hardcoded CEL-expression arguments; no LLM involved. |
| ROUTING | Logic | Conditional branching in one of three modes: CLAUSES (ordered CEL if/then, first match wins), LLM_DISPATCH (LLM picks a path via keyword → block-id mapping), or EXPRESSION_DISPATCH (single CEL expression evaluates directly to a block id, checked against an allowlist). |
| FOR_EACH | Logic | Runs one block once per item in a CEL-evaluated list; each iteration gets its own isolated scratchpad. No tool with `requireHumanApproval: true` can be called from inside it. |
| PARALLEL | Logic | Runs multiple child blocks concurrently in separate threads/scratchpad scopes. Children don't see each other's output during execution; state writes from parallel children may come back as lists, not scalars; concurrent writes to the same state key race (last-write-wins) — use unique per-branch keys. No human-approval tools inside it either. |
| REFLECTION | Logic | Quality loop over a generator block: CRITIQUE_AND_IMPROVE (feedback loops back to the same generator), CRITIQUE_OR_RETRY (generator restarts from scratch on rejection), or SYNTHESIZE (generator runs N times in parallel, then an LLM consolidates). The generator block runs internally via `generatorBlockId`, separate from the main chain. |
| SET_STATE_ENTRIES | Memory | Deterministically sets conversation-scope state variables from expressions. |
| SET_SCRATCHPAD_ENTRIES | Memory | Same as SET_STATE_ENTRIES, but writes to the current turn's short-lived scratchpad instead. |
| CONTEXT_COMPRESSION | Memory | Uses an LLM to summarize earlier conversation history while keeping recent messages intact — reduces token usage in long conversations. |
| EMIT_OUTPUT | Input/Output | Renders a template and routes the result to the user, conversation history, state, or scratchpad. Omitting `nextBlock` ends the turn. |
| GENERATE_ARTIFACT | Input/Output | Renders a template into a downloadable/viewable artifact (Markdown, DOCX, PDF). |
| PYTHON_CODE | Custom | Runs custom Python. State access is **read-only**. |
| LONG_TERM_MEMORY | Memory (plugin) | Persists (`STORE` mode) or retrieves (`RETRIEVE` mode) memories across separate conversations via a knowledge bank. Requires the Long-Term Memory plugin. |
| SEMANTIC_FEEDBACK | Logic (plugin) | Classifies whether the current user message is a correction/refinement of the prior turn's output vs. a new request, and routes accordingly. Requires the Semantic Feedback plugin. |

---

# Agent Tools

Agent tools are project-level objects (distinct from MCP tools) that agents call during execution — dataset lookups, vector search, LLM/sub-agent queries, model predictions, custom code, messaging integrations, etc. They're referenced by `id` in a simple agent's `tool_ids` or a structured-agent block's `tools`/`tool` field.

## Tool Type Catalog

**Core (always available):**

| Type | Use when |
|------|----------|
| `DatasetRowLookup` | Look up rows from a DSS dataset by key. Output shape in state is flat columns at the top level (`state["x"]["email"]`), not nested under `rows`. |
| `DatasetRowAppend` | Append rows to a DSS dataset. |
| `VectorStoreSearch` | Semantic-similarity search over a knowledge bank / vector store. |
| `LLMMeshLLMQuery` | Query an LLM, or another DSS agent, as a sub-task. Output shape in state is a plain response string. |
| `ClassicalPredictionModelPredict` | Run a deployed ML prediction model on a single record. Output shape: `{"prediction": ..., "probas": {...}}`. |
| `GRELCalculator` | Evaluate GREL formula expressions (arithmetic, date, geometry, etc.); no config needed. |
| `InlinePython` | Custom Python tool logic. |
| `RemoteMCPClient` | Call tools exposed by a remote MCP server connection. |
| `DataikuReporter` | Send a message via a DSS integration (email, Slack, Teams). |
| `ApiEndpoint` | Call a DSS API endpoint. |

**Plugin/enterprise (require plugin install or a pre-configured connection):** SQL Question Answering (NL→SQL over datasets), Semantic Model Query (NL query over a pre-built DSS Semantic Model), other `Custom_agent_tool_<plugin>_<tool>` types, Google Search, Jira/Salesforce/ServiceNow, Snowflake Cortex/Databricks Genie.

## Cross-Cutting Tool Notes

- `additionalDescriptionForLLM` is the primary signal the LLM uses to select/invoke a tool correctly — vague descriptions cause missed or misused tools.
- Tool IDs are stable; tool names are not — agent configs reference tools by `id`.
