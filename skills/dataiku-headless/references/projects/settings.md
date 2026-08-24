---
name: project-settings
description: Inspect and update Dataiku project settings. Use for Flow display and pipeline options, project default Python or R code environments, and container execution defaults.
---

# Project Settings

Project settings are a narrow direct-write exception for configuration that Cobuild does not manage.

`get_project_settings` returns the editable `settings` object. `update_project_settings` accepts only the fields documented below and rejects other settings. It uses JSON Merge Patch behavior: nested objects merge, scalar values replace, and `null` removes a field.

## Workflow

1. Confirm the project key with `list_projects`.
2. Read the current values with `get_project_settings`.
3. Pass only the requested fields to `update_project_settings`. Use `null` to remove a field left by an explicit selection.
4. Read the settings again and verify the changed values.

## Flow Display and Pipelines

| Setting | Accepted values | Behavior |
| --- | --- | --- |
| `flowDisplaySettings.zonesGraphRenderingAlgorithm` | `DOT_OLDRANK` (**Standard**), `DOT_NEWRANK_FREERANK` (**New rank**) | Standard is usually more compact but can fail on complex flows with many zones. Use New rank when the Flow does not display correctly. |
| `flowDisplaySettings.zonesGraphConnectZones` | `true`, `false` | Draw arrows for inter-zone dependencies. Disable when those arrows make the graph hard to read. |
| `flowDisplaySettings.zonesGraphForJobs` | `true`, `false` | Show Flow zones in job graphs. Disable to show job graphs without zones. |
| `flowDisplaySettings.respectTraversalOrder` | `true`, `false` | Experimental. Usually improves layouts for flows containing loops. |
| `flowDisplaySettings.zonesManualPositioning` | `true`, `false` | Enable manual positioning of Flow zones. |
| `flowDisplaySettings.showFlowZoneDescriptions` | `true`, `false` | Show each zone's short description at the top of the zone in the Flow. |
| `flowBuildSettings.mergeSqlPipelines` | `true`, `false` | Enable SQL pipelines. |
| `flowBuildSettings.pruneBeforeSqlPipelines` | `true`, `false` | Prune before SQL pipelines. |
| `flowBuildSettings.mergeSparkPipelines` | `true`, `false` | Enable Spark pipelines. |
| `flowBuildSettings.pruneBeforeSparkPipelines` | `true`, `false` | Prune before Spark pipelines. |
| `flowBuildSettings.mergeCdePipelines` | `true`, `false` | Enable CDE pipelines. |
| `flowBuildSettings.pruneBeforeCdePipelines` | `true`, `false` | Prune before CDE pipelines. |

## Default Code Environments

Configure Python under `codeEnvs.python` and R under `codeEnvs.r`.

Before using `EXPLICIT_ENV`, call `list_code_envs(language="PYTHON")` or `list_code_envs(language="R")` and copy the returned environment name exactly into `envName`.

| Mode | Fields |
| --- | --- |
| Inherit the instance default | `{"mode":"INHERIT","envName":null}` |
| Use the built-in environment | `{"mode":"USE_BUILTIN_MODE","envName":null}` |
| Select an environment | `{"mode":"EXPLICIT_ENV","envName":"ENV_NAME"}` |

`preventOverride` is independent of the mode. Set it to `true` to prevent project objects from overriding the project default.

## Container Execution

`container` controls user-code workloads. `containerForVisualRecipesWorkloads` controls visual-recipe workloads. Patch either or both with the same shape.

Before using `EXPLICIT_CONTAINER`, call `list_container_exec_configs` and copy the returned `name` exactly into `containerConf`. This list tool requires global administrator rights; if it is unavailable, ask the user for the exact name instead of guessing.

| Mode | Fields |
| --- | --- |
| Inherit the instance default | `{"containerMode":"INHERIT","containerConf":null}` |
| Run without a container | `{"containerMode":"NONE","containerConf":null}` |
| Select a configuration | `{"containerMode":"EXPLICIT_CONTAINER","containerConf":"CONFIG_NAME"}` |

## Example Patch

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

- `list_projects`
- `get_project_settings`
- `update_project_settings`
- `list_code_envs`
- `list_container_exec_configs`

## Safety Rules

- Read before writing and patch only the requested fields.
- Use exact code environment and container configuration names returned by discovery tools.
- Use `null` to clear `envName` or `containerConf` when leaving an explicit selection.
- Verify every update by reading project settings again.
