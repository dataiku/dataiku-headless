---
name: projects
description: Understand and inspect Dataiku projects, their metadata, variables, and Flow organization. Use when an agent must discover projects, orient in a project, update project variables, gather context for Cobuild, or create a new project.
---

# Projects

Use this guide to understand and inspect Dataiku projects, update project variables, and gather grounded context for Cobuild.

## Project Concepts

A project is the primary boundary for Dataiku assets, including datasets, recipes, models, folders, dashboards, agents, and Flow organization.

The project key is the stable technical identifier. The display name, shown as project metadata, is human-facing and can differ from the key.

Project metadata includes labels, descriptions, tags, and checklists.

Project variables provide runtime configuration that can be used in various places throughout a project.

`get_project_variables` returns `{"standard": {...}, "local": {...}}`.

- `standard`: shared across instances running the project
- `local`: instance-specific overrides

Flow zones organize related Flow items visually. They are useful context when a user asks Cobuild to reorganize a Flow, but they do not change an asset's technical dependencies.

## Modification Routes

| Action | Route |
| --- | --- |
| Create a new project | Direct creation exception with `create_project` |
| Update project variables | Direct write with `get_project_variables` then `set_project_variables` |
| Modify an existing project's metadata, Flow structure, or assets | Cobuild |

## Workflow

1. Use `count_projects` and `list_projects` to discover projects and confirm the exact project key.
2. For existing-project context, use `get_project_metadata` and `get_project_variables` to inspect metadata and configuration.
3. To update project variables, first read the current variables with `get_project_variables`, modify only the requested keys, then pass the complete replacement object to `set_project_variables`.
4. Use `get_flow_graph` to orient in the Flow when dependencies matter, and `list_flow_zones` when visual organization matters.
5. Use `get_flow_object_metadata` to inspect metadata for a specific project object.
6. For a new project, confirm the unique project key and display name with the user, then use `create_project`. When the user specifies a project folder, discover its `folder_id` with `list_project_folders` first and use `get_project_folder` when you need to confirm the exact folder contents, then pass that `folder_id`.
7. Verify a newly created project with `list_projects` or `get_project_metadata`.
8. Route other existing-project changes through `./cobuild.md`.

## Preferred Tools

- `count_projects`
- `list_projects`
- `create_project`
- `get_project_metadata`
- `get_project_variables`
- `set_project_variables`
- `get_flow_graph`
- `list_flow_zones`
- `get_flow_object_metadata`

## Safety Rules

- Confirm the project key and display name before creating a project.
- Verify that the requested project key is not already in use before direct creation.
- When creating a project in a folder, discover the folder ID with `list_project_folders`; do not invent it.
- `get_flow_graph` is the primary flow-orientation tool. It names the flow's `sources`, groups node refs under `nodes_by_type`, and lists dependency `edges`. On large flows those lists may come back clipped; when that affects the task, use the relevant `list_*` tools for context and inspect only the specific datasets, recipes, or flow objects that matter with the relevant `get_*` tools.
