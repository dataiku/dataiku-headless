---
name: projects
description: Understand and inspect Dataiku projects, their metadata, variables, settings, and Flow organization. Use when an agent must discover projects, orient in a project, update project configuration, gather context for Cobuild, or create a new project.
---

# Projects

Use this guide to inspect Dataiku projects, update project configuration, and gather grounded context for Cobuild.

## Project Concepts

A project is the primary boundary for Dataiku assets, including datasets, recipes, models, folders, dashboards, agents, and Flow organization.

The project key is the stable technical identifier. The display name, shown as project metadata, is human-facing and can differ from the key.

Project metadata includes labels, descriptions, tags, and checklists.

Project variables provide runtime configuration that can be used in various places throughout a project.

`get_project_variables` returns `{"standard": {...}, "local": {...}}`.

- `standard`: shared across instances running the project
- `local`: instance-specific overrides

`get_project_settings` returns the editable `settings` object. `update_project_settings` accepts a partial object using JSON Merge Patch behavior: nested objects merge, scalar and list values replace, and `null` removes a field.

Flow zones organize related Flow items visually. They are useful context when a user asks Cobuild to reorganize a Flow, but they do not change an asset's technical dependencies.

## Modification Routes

| Action | Route |
| --- | --- |
| Create a new project | Direct creation exception with `create_project` |
| Update project variables | Direct write with `get_project_variables` then `set_project_variables` |
| Update project settings | Direct write with `get_project_settings` then `update_project_settings` |
| Modify an existing project's metadata, Flow structure, or assets | Cobuild |

## Workflow

1. Use `count_projects` and `list_projects` to discover projects and confirm the exact project key. `list_projects` includes each project's owner, short description, and last-modified context; use `search` to narrow by project name, key, owner, or short description.
2. For existing-project context, use `get_project_metadata`, `get_project_variables`, and `get_project_settings` as needed.
3. To update project variables, first read them, modify only the requested keys, then pass the complete replacement object to `set_project_variables`.
4. To update project settings, first read them, then pass only the nested fields to change to `update_project_settings`. Use `null` to remove a field left by an explicit selection.
5. Use `get_flow_graph` to orient in the Flow when dependencies matter, and `list_flow_zones` when visual organization matters.
6. Use `get_flow_object_metadata` to inspect metadata for a specific project object.
7. For a new project, confirm the unique project key and display name with the user, then use `create_project`. When the user specifies a project folder, discover its `folder_id` with `list_project_folders` first and use `get_project_folder` when you need to confirm the exact folder contents, then pass that `folder_id`.
8. Verify a newly created project with `list_projects` or `get_project_metadata`.
9. Route other existing-project changes through `./cobuild.md`.

## Project Setting Options

### Flow Display and Pipelines

| Setting | Values |
| --- | --- |
| `flowDisplaySettings.showFlowZoneDescriptions` | Boolean; show zone descriptions on the Flow |
| `flowDisplaySettings.zonesGraphRenderingAlgorithm` | `DOT_OLDRANK` or `DOT_NEWRANK_FREERANK` |
| `flowDisplaySettings.zonesGraphConnectZones` | Boolean |
| `flowDisplaySettings.zonesGraphForJobs` | Boolean |
| `flowDisplaySettings.respectTraversalOrder` | Boolean |
| `flowDisplaySettings.zonesManualPositioning` | Boolean |
| `flowBuildSettings.mergeSqlPipelines` | Boolean; enable SQL pipelines |
| `flowBuildSettings.mergeSparkPipelines` | Boolean; enable Spark pipelines |
| `flowBuildSettings.mergeCdePipelines` | Boolean; enable CDE pipelines |

`pruneBeforeSqlPipelines`, `pruneBeforeSparkPipelines`, and `pruneBeforeCdePipelines` control pruning for those pipeline families.

### Default Code Environments

Configure Python under `codeEnvs.python` and R under `codeEnvs.r`.

| Mode | Fields |
| --- | --- |
| Inherit the instance default | `{"mode":"INHERIT","envName":null}` |
| Use the built-in environment | `{"mode":"USE_BUILTIN_MODE","envName":null}` |
| Select an environment | `{"mode":"EXPLICIT_ENV","envName":"ENV_NAME"}` |

`preventOverride` is an independent boolean. Set it to `true` to prevent project objects from overriding the project default.

### Container Execution

`container` controls user-code workloads. `containerForVisualRecipesWorkloads` controls visual-recipe workloads. Patch either or both with the same shape.

| Mode | Fields |
| --- | --- |
| Inherit the instance default | `{"containerMode":"INHERIT","containerConf":null}` |
| Run without a container | `{"containerMode":"NONE","containerConf":null}` |
| Select a configuration | `{"containerMode":"EXPLICIT_CONTAINER","containerConf":"CONFIG_NAME"}` |

Example patch:

```json
{
  "flowDisplaySettings": {"showFlowZoneDescriptions": true},
  "flowBuildSettings": {"mergeSqlPipelines": true},
  "codeEnvs": {
    "python": {
      "mode": "EXPLICIT_ENV",
      "envName": "PYTHON_ENV",
      "preventOverride": true
    }
  },
  "container": {
    "containerMode": "EXPLICIT_CONTAINER",
    "containerConf": "CONTAINER_CONFIG"
  }
}
```

## Preferred Tools

- `count_projects`
- `list_projects`
- `create_project`
- `get_project_metadata`
- `get_project_variables`
- `set_project_variables`
- `get_project_settings`
- `update_project_settings`
- `get_flow_graph`
- `list_flow_zones`
- `get_flow_object_metadata`

## Safety Rules

- Confirm the project key and display name before creating a project.
- Verify that the requested project key is not already in use before direct creation.
- When creating a project in a folder, discover the folder ID with `list_project_folders`; do not invent it.
- Read project settings before updating them, patch only the requested fields, and read them again to verify the result.
- `get_flow_graph` is the primary flow-orientation tool. It returns flow sources, nodes, and dependency edges. On large flows those lists may come back clipped; when that affects the task, use the relevant `list_*` tools for context and inspect only the specific datasets, recipes, or flow objects that matter with the relevant `get_*` tools.
