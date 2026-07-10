---
name: dataiku-agents
description: Inspect Dataiku DSS agents and use the results as context for Cobuild. Use when an agent must list agents, inspect agent settings, versions, or tools before asking Cobuild to create or modify project assets.
---

# Agent Inspection

Use this skill to inspect existing agents and supporting agent-tool configuration.

## Workflow

1. Use `list_agents` to discover agents in the project.
2. Use `get_agent_settings` to inspect an agent before any Cobuild prompt about modifying it.
3. Use `list_agent_versions` when version context matters.
4. Use `list_agent_tools` and `get_agent_tool_settings` to inspect available tool objects.
5. If the task requires creating, updating, deleting, or running agents, route that work through `./dataiku-skills/cobuild/SKILL.md`.

## Preferred Tools

- `list_agents`
- `get_agent_settings`
- `list_agent_versions`
- `list_agent_tools`
- `get_agent_tool_settings`

## Safety Rules

- Never invent agent ids or agent tool names.
- Keep this skill focused on inspection and Cobuild grounding.
