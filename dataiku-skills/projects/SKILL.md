---
name: projects
description: Understand and inspect Dataiku projects, their metadata, variables, and Flow organization. Use when an agent must discover projects, orient in a project, gather context for Cobuild, or create a new project through the direct creation exception.
---

# Projects

Use this skill to understand and inspect Dataiku projects and gather grounded context for Cobuild.

## Project Concepts

A project is the primary boundary for Dataiku assets, including datasets, recipes, models, folders, dashboards, agents, and Flow organization.

The project key is the stable technical identifier. The display name, shown as project metadata, is human-facing and can differ from the key.

Project metadata includes labels, descriptions, tags, and checklists. Project variables provide runtime configuration: standard variables are shared across instances, while local variables are instance-specific overrides.

Flow zones organize related Flow items visually. They are useful context when a user asks Cobuild to reorganize a Flow, but they do not change an asset's technical dependencies.

## Modification Routes

| Action | Route |
| --- | --- |
| Create a new project | Direct creation exception |
| Modify an existing project's metadata, variables, Flow structure, or assets | Cobuild |

## Workflow

1. Use `count_projects` and `list_projects` to discover projects and confirm the exact project key.
2. Start existing-project work with `get_project_overview`; it returns the main asset lists, recent jobs, Flow sources, redacted standard variables, and section warnings in one bounded call.
3. Use `get_flow_graph` and `list_flow_zones` when dependencies or organization matter. Scope a large graph by zone or raise its node and edge limits only within the documented ceilings.
4. Use `get_flow_object_metadata` to inspect metadata for a specific project object.
5. For a new project, confirm the unique project key and display name with the user, then use `create_project`.
6. Verify a newly created project with `list_projects` or `get_project_metadata`.
7. Route all existing-project changes through `./dataiku-skills/cobuild/SKILL.md`.
8. After a Cobuild build, use `audit_project` for a bounded Flow review — a finish gate, not a correctness proof. Add a contract when the requested output shape or minimum row count is known.

## Preferred Tools

- `count_projects`
- `list_projects`
- `create_project`
- `get_project_metadata`
- `get_project_variables`
- `get_project_overview`
- `get_flow_graph`
- `list_flow_zones`
- `get_flow_object_metadata`
- `audit_project`

## Safety Rules

- Discover project keys via tools; do not invent identifiers.
- Confirm the project key and display name before creating a project.
- Verify that the requested project key is not already in use before direct creation.
- Keep existing-project changes under the Cobuild route.
- Treat a warning or `truncated: true` result as partial context; narrow the request before drawing conclusions about omitted assets.
- Local project variables are opt-in and all credential-shaped values remain redacted.
