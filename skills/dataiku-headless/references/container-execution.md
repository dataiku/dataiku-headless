---
name: container-execution
description: Select where an existing recipe, ML task, saved-model retrain, WebApp backend, Knowledge Bank, or agent tool runs with set_container_exec_config. Use when the request is only about container execution placement, not about what the object does.
---

# Container Execution Placement

`set_container_exec_config` changes only the container execution selection of one
existing object. It preserves the object's logic, code, inputs, outputs, and every other
setting. This is a narrow direct-write exception and does not require Cobuild.

For project-wide defaults (`container` and `containerForVisualRecipesWorkloads`), use
`./projects/settings.md` instead. Use this guide for one specific object.

## Supported Objects

| `object_type` | `object_id` | What it sets | Inspect with |
| --- | --- | --- | --- |
| `recipe` | Recipe name | Where that recipe's execution runs | `get_recipe_settings` with `include_engine_params=true` |
| `ml_task` | Analysis id of an analysis holding a single ML task | Where that task's training runs | `get_ml_analysis_settings` |
| `saved_model` | Saved model id | Where that model's retrain runs | `list_saved_models` (id only, see below) |
| `webapp` | WebApp id | Where that WebApp's backend runs | `get_webapp_settings` |
| `knowledge_bank` | Knowledge Bank id | Where that Knowledge Bank's build runs | `get_knowledge_bank_settings` |
| `agent_tool` | Agent tool id | Where that tool's code runs | `get_agent_tool_settings` |

Only objects that actually run their own code carry a selection. A saved model imported
from MLflow has no retrain configuration, and a built-in agent tool such as a dataset
lookup runs no user code, so neither exposes an override.

A saved model's current selection cannot be read through Headless: `list_saved_models`
returns identity only, and there is no saved-model settings tool. For that one object
type, the selection this tool reads back after saving is the verification.

## Workflow

1. Discover the identifier with `list_recipes`, `list_ml_analyses`, `list_saved_models`,
   `list_webapps`, `list_knowledge_banks`, or `list_agent_tools`.
2. Inspect the current selection with the matching tool above.
3. Choose one mode:
   - `INHERIT`: use the project default; omit `container_config`.
   - `NONE`: run without a container; omit `container_config`.
   - `EXPLICIT_CONTAINER`: select one configuration and provide `container_config`.
4. Before using `EXPLICIT_CONTAINER`, call `list_container_exec_configs` and copy the
   returned name exactly. This discovery tool requires global administrator rights; if
   it is unavailable, ask the user for the exact configuration name instead of guessing.
5. Call `set_container_exec_config`. It returns the selection read back after saving;
   re-read the object's own settings to confirm.
6. Restart the WebApp backend through `./webapps.md` and Cobuild when a running backend
   must pick up its new placement.

## Preferred Tools

- `list_container_exec_configs`
- `list_recipes`, `list_ml_analyses`, `list_saved_models`, `list_webapps`,
  `list_knowledge_banks`, `list_agent_tools`
- `get_recipe_settings`
- `get_ml_analysis_settings`
- `get_webapp_settings`
- `get_knowledge_bank_settings`
- `get_agent_tool_settings`
- `set_container_exec_config`

## Safety Rules

- Do not invent a container configuration name. Use discovery or an exact name supplied
  by the user.
- Treat container execution selection as the only direct setting write for these objects.
  Route every other change through `./cobuild.md`.
- The write fails without saving when the object exposes no container execution
  override, when an analysis does not hold exactly one ML task, when a recipe exposes a
  selection in more than one place, or when Dataiku cannot resolve a plugin-backed agent
  tool's type. Nothing is written in any of these cases; report the condition instead of
  retrying or writing the setting elsewhere.
- For a WebApp, Knowledge Bank, agent tool, or saved model, Dataiku replaces the whole
  settings object on save. An edit someone else makes between this tool's read and its
  write is lost, so avoid it while another person is editing that object.
- Changing placement can change available CPU, memory, GPU, and image contents. Confirm
  the target configuration fits the workload before switching a production object.
