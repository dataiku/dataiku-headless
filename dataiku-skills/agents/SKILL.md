---
name: dataiku-agents
description: "Create, configure, and manage Dataiku DSS agents — simple tools-using ReAct agents, BLOCKS_GRAPH structured visual agents, and custom python code agents."
---

# Agents Overview

DSS agents come in three types:

| Type | When to use |
|------|-------------|
| **TOOLS_USING_AGENT** | Q&A, retrieval, or chat — a single ReAct loop where the LLM picks tools autonomously. |
| **STRUCTURED_AGENT** | Any agent with **deterministic guardrails**, **hard rules that must hold regardless of LLM behaviour**, **multi-stage pipelines** (collect → filter → rank → emit), conditional logic, or parallel work. |
| **PYTHON_AGENT** | Fully custom agent logic in Python — subclass `BaseLLM` from `dataiku.llm.python`; full control over streaming, tool calls, and response shaping. **Use only when TOOLS_USING_AGENT and STRUCTURED_AGENT cannot meet the requirement** — they are easier to understand and maintain. |

For detailed configuration, go straight to the type-specific reference:
- [Simple agent reference](references/simple-agent.md) — TOOLS_USING_AGENT
- [Structured agent reference](references/structured-agent.md) — STRUCTURED_AGENT (BLOCKS_GRAPH)
- [Code agent reference](references/code-agent.md) — PYTHON_AGENT

> **PYTHON_AGENT** agents are configured entirely through Python code. `get_agent_settings` returns `code`, `code_env_name`, and `supports_image_inputs`. Use `update_agent_settings` to write any of these fields.

## Discovering and Managing Agents

- `list_agents` — list all agents in a project; use to find an agent ID before editing
- `get_agent_settings` — read full agent config; accepts optional `version_id` (defaults to active version); returns `version.code` for PYTHON_AGENT, blocks for STRUCTURED_AGENT, LLM/tools for TOOLS_USING_AGENT; **always call before mutating**
- `delete_agent` — delete an agent permanently; confirm with user first
- `run_agent` — test an agent after changes
- `get_flow_object_metadata` — read tags, descriptions, and custom fields for an agent; use object ID as `object_name`

> **Limitation:** `set_flow_object_metadata` writes are silently ignored for agents (Dataiku bug).

## Version Management

Agents support multiple named versions; one version is active at a time.

| Goal | Tool |
| --- | --- |
| List all versions | `list_agent_versions` |
| Create a new (empty) version | `create_agent_version` with `version_id` |
| Create a version copied from another | `create_agent_version` with `version_id` + `duplicate_of` |
| Switch the active version | `set_active_agent_version` |

**Versioning workflow** (e.g. iterating on a TOOLS_USING_AGENT):
1. `list_agent_versions` — confirm current versions and which is active.
2. `create_agent_version` with `duplicate_of` set to the current active version — copies all settings into the new version.
3. `update_agent_settings` with the new `version_id` — make changes only in the new version.
4. `set_active_agent_version` to the new version, then `run_agent` — test it; switch back to the previous version if needed.

## Create Workflow

**TOOLS_USING_AGENT / STRUCTURED_AGENT:**
1. `create_agent` with `agent_type`: `"TOOLS_USING_AGENT"` or `"STRUCTURED_AGENT"`
2. `get_agent_settings` to inspect the newly created agent
3. `update_agent_settings` to configure — see the type-specific reference for what to set
4. `run_agent` to test

**PYTHON_AGENT:**
1. `create_agent` with `agent_type`: `"PYTHON_AGENT"`
2. `update_agent_settings` with `code`, `code_env_name`, and `supports_image_inputs` as needed — see the [code agent reference](references/code-agent.md)
3. `run_agent` to test

## Agent Tools

Agent tools are project-level objects agents call during execution. Core types cover dataset lookups, vector search, LLM/agent queries, ML prediction, inline Python, MCP servers, and messaging. Plugin tools (SQL QA, Semantic Model Query, Google Search, enterprise integrations) are available when connections are configured.

**Always set `additionalDescriptionForLLM`** — it is the primary signal the LLM uses to select and invoke tools correctly.

Read the [agent tools reference](references/agent-tools.md) for the full type catalog, CRUD workflow, config shapes, and guardrails before creating or attaching tools.
