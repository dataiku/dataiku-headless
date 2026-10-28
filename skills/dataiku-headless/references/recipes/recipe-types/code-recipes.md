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

As of Dataiku 15.1, Cobuild cannot create or edit `r` recipes. If the user still wants R:

- Inspect an existing R recipe with `get_recipe_settings`, which returns its code.
- Do not send R recipe creation or edits to Cobuild, and do not fall back to raw APIs. Report the gap.
- Offer a visual or `python` recipe through Cobuild as the alternative, and build it only if the user agrees.
