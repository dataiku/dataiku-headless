---
name: dataiku-agents
description: Understand and inspect Dataiku agents and agent tools, including agent types, versions, configuration, and execution design. Use when an agent needs existing-agent context or must prepare grounded requirements for Cobuild changes.
---

# Dataiku Agents

Use this guide to understand and inspect existing Dataiku agents and their project-level tools.

## Agent Concepts

| Type | `agent_type` | Use when |
| --- | --- | --- |
| **Simple agent** | `TOOLS_USING_AGENT` | A single LLM-driven tool loop is sufficient. |
| **Structured agent** | `STRUCTURED_AGENT` | The workflow needs deterministic branching, parallel work, explicit memory, or guaranteed pre/post-processing. |
| **Code agent** | `PYTHON_AGENT` | Simple and structured agents cannot provide the required custom behavior. |

Agent tools are project-level objects that agents call during execution. Agent configurations reference them by ID.

Read the appropriate type reference when inspecting an agent of that type or designing a new agent:

- [Simple agent](./agents/simple-agent.md)
- [Structured agent](./agents/structured-agent.md)
- [Code agent](./agents/code-agent.md)

Read [Agent Tools](./agents/agent-tools.md) when inspecting existing tools or choosing tools for an agent design.

## Workflow

1. Use `list_agents` to discover agents in the project.
2. Use `get_agent_settings` to inspect the selected agent's configuration and `agent_type`.
3. Use `list_agent_versions` when version context matters.
4. Use `list_agent_tools` and `get_agent_tool_settings` when existing tools are relevant.
5. If the request only changes where an agent tool's code runs, use `./container-execution.md`. This is a narrow direct-write exception and does not require Cobuild.
6. If the task requires any other creation, update, deletion, or run of agents or agent tools, route that work through `./cobuild.md` using the gathered context.

## Preferred Tools

- `list_agents`
- `get_agent_settings`
- `list_agent_versions`
- `list_agent_tools`
- `get_agent_tool_settings`

## Safety Rules
