---
name: projects
description: Explore Dataiku projects through MCP tools. Use when an agent must list projects, inspect project metadata and variables, or orient in the flow before asking Cobuild to create or modify project assets. Project creation remains a direct exception.
---

# Project Operations

Use this skill to inspect projects and gather context for Cobuild.

## Workflow

1. Use `list_projects` and `count_projects` for project discovery.
2. Use `get_project_metadata` and `get_project_variables` to understand the current project state.
3. Use `get_flow_items_in_traversal_order` and `list_flow_zones` for flow orientation.
4. Use `get_flow_object_metadata` to inspect object-level metadata.
5. If the user wants to create a new project, `create_project` remains a direct-tool exception.
6. If the task requires modifying an existing project's assets, metadata, or flow structure, route that work through `./dataiku-skills/cobuild/SKILL.md`.

## Preferred Tools

- `count_projects`
- `list_projects`
- `create_project`
- `get_project_metadata`
- `get_project_variables`
- `get_flow_items_in_traversal_order`
- `list_flow_zones`
- `get_flow_object_metadata`

## Safety Rules

- Never invent project keys.
- Confirm project key and display name before `create_project`.
- Do not document direct project-mutation workflows here beyond `create_project`.
