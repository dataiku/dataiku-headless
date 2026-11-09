---
name: recipes
description: Understand and inspect Dataiku recipes, then use grounded context for Cobuild recipe work. Use when selecting a recipe type, inspecting an existing recipe, or planning a Flow transformation.
---

# Recipes

Use this guide to understand existing recipes and plan grounded Flow transformations through Cobuild.

## Recipe Concepts

A recipe is a Flow transformation that consumes one or more project objects and produces one or more outputs. Most recipes transform datasets; some consume or produce managed folders, saved models, Knowledge Banks, or evaluation outputs.

Recipe configuration defines its inputs and outputs, transformation behavior, and dependencies in the Flow. Running a recipe creates a job whose outputs should be validated before dependent work continues.

Choose the recipe family before asking Cobuild to create or change a recipe:

- **Data prep** recipes clean, combine, reshape, filter, or move data.
- **ML** recipes generate features, score data, or evaluate model outputs.
- **GenAI** recipes apply LLMs, process documents, populate Knowledge Banks, or evaluate LLM and agent outputs.
- **Code** recipes run custom code or SQL.

Use visual recipe families by default. Use a Code recipe only when the user explicitly requests a code-based transformation.

A recipe's outputs must fit the surrounding Flow. Inspect input schemas and existing storage context before requesting new datasets or managed folders. When a new managed output needs a connection, use the datasets, managed-folders, and, when needed, connections skills to ground the Cobuild request.

## Workflow

1. Use `list_recipes` to discover recipes, then use `get_recipe_settings` to inspect a selected recipe's type, inputs, outputs, and configuration.
2. Use `get_flow_graph` when upstream/downstream context, dependencies, or Flow placement matters.
3. Inspect input and output datasets when schema, data shape, storage, or sample values affect the transformation.
4. Read the matching recipe-family reference before interpreting a type-specific configuration or describing a new recipe to Cobuild.
5. Read supporting guides when the selected recipe depends on managed folders, models, LLMs, Knowledge Banks, agents, code environments, project libraries, or connections.
6. If the request only changes where an existing recipe runs, use `./container-execution.md`. This is a narrow direct-write exception and does not require Cobuild.
7. If the request only changes which code environment an existing Python recipe runs with, follow [Python Recipe Code Environment](#python-recipe-code-environment). This is also a narrow direct-write exception.
8. Route all other recipe creation, editing, and wiring through `./cobuild.md`.
9. Cobuild will run recipes and build datasets as part of broader project work. For one-off execution of an existing recipe or dataset build, use `./jobs.md`: `build_datasets` for dataset outputs and `run_recipe` for direct recipe execution.
10. After a build or run starts, use `./jobs.md` to follow an active or uncertain job. Validate outputs through the relevant guide.

## Python Recipe Code Environment

`set_recipe_code_env` requires `design`; it is unavailable on Automation.

`set_recipe_code_env` changes only the code environment selection of one existing `python` recipe. It preserves the recipe's code, inputs, outputs, container selection, and every other setting. Cobuild cannot change this selection. Route environment changes for other recipe types through `./cobuild.md`.

1. Inspect the recipe with `get_recipe_settings`. Confirm that its `type` is `python` and read `params.envSelection`.
2. Choose one mode:
   - `INHERIT`: use the project default (see `./projects/settings.md`); omit `env_name`.
   - `USE_BUILTIN_MODE`: use the instance's built-in Python environment; omit `env_name`.
   - `EXPLICIT_ENV`: select one environment and pass `env_name`.
3. Before using `EXPLICIT_ENV`, call `list_code_envs(language="PYTHON")` and copy the returned name exactly. Select an explicit environment only when the user names one or its compatibility is established; see `./administration/code-environments.md`.
4. Call `set_recipe_code_env`. It returns `previous_env_selection` and the `env_selection` read back after saving. Keep the previous selection so that you can restore it on request. Confirm the change with `get_recipe_settings`.
5. Run the recipe through `./jobs.md` only when the user asks. A successful run is the evidence that the environment fits the code.

## Recipe Families

| Family | Purpose | Reference |
| --- | --- | --- |
| Data prep | Clean, combine, filter, reshape, aggregate, and move data with visual transformations. | [Data prep recipes](./recipes/recipe-types/data-prep-recipes.md) |
| ML | Generate features, score records, and evaluate model outputs. | [ML recipes](./recipes/recipe-types/ml-recipes.md) |
| GenAI | Apply LLMs, process documents, populate Knowledge Banks, and evaluate GenAI outputs. | [GenAI recipes](./recipes/recipe-types/genai-recipes.md) |
| Code | Run explicitly requested Python, R, SQL, Spark, or shell transformations. | [Code recipes](./recipes/recipe-types/code-recipes.md) |

## Shared References

- Read the [Dataiku formula language reference](./recipes/shared/dataiku_formula_language.md) when a recipe uses or needs a formula expression.
- Read the [prepare processor catalog](./recipes/shared/prepare_processors_overview.md) when inspecting or requesting a `prepare` recipe.

## Supporting Context

- Dataset inputs and outputs: `./datasets.md`
- Managed-folder inputs and outputs: `./managed_folders.md`
- Output storage connections: `./connections.md`
- ML analyses and saved models: `./machine-learning.md`
- LLMs, Knowledge Banks, and RAG LLMs: `./llms-and-knowledge-banks.md`
- Agent-backed prompts or agent evaluation: `./agents.md`
- Explicitly requested code environments: `./administration/code-environments.md`
- Project-library code dependencies: `./project-libraries.md`
- Active or uncertain execution: `./jobs.md`
- Container execution placement for one object: `./container-execution.md`
- Creating a reusable plugin recipe component from local source: `./plugin-development.md`

## Preferred Tools

- `get_flow_graph`
- `list_recipes`
- `get_recipe_settings`
- `set_recipe_code_env`
- `list_code_envs`
- `list_datasets`
- `get_dataset_info`
- `get_dataset_profile`
- `get_dataset_sample`

## Safety Rules

- Inspect an existing recipe before any modification.
- Treat container execution selection, documented in `./container-execution.md`, and
  Python recipe code-environment selection, documented above, as the only direct
  recipe-setting writes. Route changes to recipe logic, code, inputs, outputs, or other
  engine settings through Cobuild.
- `set_recipe_code_env` saves nothing when the recipe is not a `python` recipe, exposes no
  environment selection, or names no Python environment on the instance. Dataiku can also
  refuse the save when the project prevents overriding its default environment or the
  user cannot use the environment. Report the condition; do not change project settings
  to bypass it unless the user asks.
- Dataiku replaces the whole recipe on save. An edit someone else makes between the
  tool's read and its write is lost, so avoid it while another person edits that recipe.
- Preserve the surrounding Flow's storage and dependency context unless the user requests a change.
- Treat a timed-out or interrupted build as potentially still running; inspect the job before retrying or changing related Flow objects.
- `get_flow_graph` is the primary flow-orientation tool. It returns flow sources, nodes, and dependency edges. On large flows those lists may come back clipped; when that affects the task, use the relevant `list_*` tools for context and inspect only the specific datasets, recipes, or flow objects that matter with the relevant `get_*` tools.
- Use `./jobs.md` for direct execution of an existing recipe or its dataset outputs; this guide stays focused on inspection and grounded recipe planning.
- Keep this skill focused on inspection, concepts, and Cobuild grounding. Do not add
  direct recipe mutation workflows beyond the container execution and Python
  code-environment exceptions.
