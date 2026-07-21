---
name: dataiku-agents
description: Understand and inspect Dataiku agents and agent tools, including agent types, versions, configuration, and execution design. Use when an agent needs existing-agent context or must prepare grounded requirements for Cobuild changes.
---

# Dataiku Agents

Use this skill to understand and inspect existing Dataiku agents and their project-level tools.

## Agent Concepts

| Type | `agent_type` | Use when |
| --- | --- | --- |
| **Simple agent** | `TOOLS_USING_AGENT` | A single LLM-driven tool loop is sufficient. |
| **Structured agent** | `STRUCTURED_AGENT` | The workflow needs deterministic branching, parallel work, explicit memory, or guaranteed pre/post-processing. |
| **Code agent** | `PYTHON_AGENT` | Simple and structured agents cannot provide the required custom behavior. |

Agent tools are project-level objects that agents call during execution. Agent configurations reference them by ID.

Read the appropriate type reference when inspecting an agent of that type or designing a new agent:

- [Simple agent](references/simple-agent.md)
- [Structured agent](references/structured-agent.md)
- [Code agent](references/code-agent.md)

Read [Agent Tools](references/agent-tools.md) when inspecting existing tools or choosing tools for an agent design.

## Workflow

1. Use `list_agents` to discover agents in the project.
2. Use `get_object_settings` with `object_type=agent` to inspect the selected agent's configuration and versions. Pass `version_id` to isolate one version.
3. Use `list_agent_tools` to discover tools and `get_object_settings` with `object_type=agent_tool` to inspect one.
4. If the task requires creating, updating, deleting, or running agents or agent tools, route that work through `./dataiku-skills/cobuild/SKILL.md` using the gathered context.

## Preferred Tools

- `list_agents`
- `get_object_settings`
- `list_agent_tools`

## Safety Rules

- Discover agent and agent-tool IDs via tools; do not invent identifiers.
- Keep this skill read-only. Route agent and agent-tool creation, edits, deletion, and execution through `./dataiku-skills/cobuild/SKILL.md`.
