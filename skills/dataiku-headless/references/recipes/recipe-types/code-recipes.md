---
name: code-recipes
description: Conceptual guide to Dataiku Code recipe selection when a user explicitly requests a code-based transformation.
---

# Code Recipes

Read this reference only after the user explicitly requests a code-based transformation. Complexity, libraries, or custom logic do not independently justify a Code recipe; use a visual recipe unless code is explicitly requested.

| Type | Use after code is explicitly requested |
| --- | --- |
| `python` | Python transformation. |
| `r` | R transformation, only when the user explicitly asks for R. See [R Recipes](#r-recipes). |
| `sql_query` | Single-statement SQL transformation. |
| `sql_script` | Multi-statement SQL workflow. |
| `pyspark` | Python Spark work. |
| `spark_scala` | Scala Spark work. |
| `spark_sql_query` | Spark SQL work. |
| `shell` | Explicit shell workflow. |

## Selection Notes

- Inspect existing code before requesting a change to an existing Code recipe.
- Select a code environment from discovered names only when explicit environment selection is needed.
- Use project-library context when the recipe depends on shared source files.
- For SQL, inspect dataset and storage context before describing the intended query behavior.

## R Recipes

Use an `r` recipe only when the user explicitly asks for R. Statistical logic, R package names, or R source code being migrated do not justify R on their own; follow the visual-first default, or `../../migrations.md` for ported logic.

In Dataiku 15.1 and earlier, Cobuild cannot create or edit `r` recipes, so Headless writes them directly:

- Create with `create_r_recipe`. A missing output dataset is created as a managed dataset.
- Inspect with `get_recipe_settings`, then replace the code, the main inputs, or both with `update_r_recipe`. The code can read only declared inputs.
- Build with `run_recipe` and check the output with `get_dataset_sample`.
- Delete through `../../cobuild.md`.
- If a run fails on a missing R package, find an R environment that has it with `list_code_envs` (`language` R, `packages`) and make it the project's default R environment with `update_project_settings`. If none has it, creating one changes the instance: confirm with the user first, then see `../../administration/code-environments.md`.
