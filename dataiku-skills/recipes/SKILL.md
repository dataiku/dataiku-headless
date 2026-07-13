---
name: recipes
description: Understand and inspect Dataiku recipes, then use grounded context for Cobuild recipe work. Use when selecting a recipe type, inspecting an existing recipe, or planning a Flow transformation.
---

# Recipes

Use this skill to understand existing recipes and plan grounded Flow transformations through Cobuild.

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
2. Use `get_flow_items_in_traversal_order` only when upstream/downstream context, dependencies, or Flow placement matters.
3. Inspect input and output datasets when schema, data shape, storage, or sample values affect the transformation.
4. Read the matching recipe-family reference before interpreting a type-specific configuration or describing a new recipe to Cobuild.
5. Read supporting object skills when the selected recipe depends on managed folders, models, LLMs, Knowledge Banks, agents, code environments, project libraries, or connections.
6. Route recipe creation, editing, wiring, and execution through `./dataiku-skills/cobuild/SKILL.md`.
7. After a build or run starts, use `../jobs/SKILL.md` to follow an active or uncertain job. Validate outputs through the relevant object skill.

## Recipe Families

| Family | Purpose | Reference |
| --- | --- | --- |
| Data prep | Clean, combine, filter, reshape, aggregate, and move data with visual transformations. | [Data prep recipes](references/data-prep-recipes.md) |
| ML | Generate features, score records, and evaluate model outputs. | [ML recipes](references/ml-recipes.md) |
| GenAI | Apply LLMs, process documents, populate Knowledge Banks, and evaluate GenAI outputs. | [GenAI recipes](references/genai-recipes.md) |
| Code | Run explicitly requested Python, R, SQL, Spark, or shell transformations. | [Code recipes](references/code-recipes.md) |

## Shared References

- Read the [Dataiku formula language reference](references/dataiku_formula_language.md) when a recipe uses or needs a formula expression.
- Read the [prepare processor catalog](references/prepare_processors_overview.md) when inspecting or requesting a `prepare` recipe.

## Supporting Context

- Dataset inputs and outputs: `../datasets/SKILL.md`
- Managed-folder inputs and outputs: `../managed_folders/SKILL.md`
- Output storage connections: `../connections/SKILL.md`
- ML analyses and saved models: `../machine-learning/SKILL.md`
- LLMs, Knowledge Banks, and RAG LLMs: `../llms-and-knowledge-banks/SKILL.md`
- Agent-backed prompts or agent evaluation: `../agents/SKILL.md`
- Explicitly requested code environments: `../code-environments/SKILL.md`
- Project-library code dependencies: `../project-libraries/SKILL.md`
- Active or uncertain execution: `../jobs/SKILL.md`

## Preferred Tools

- `get_flow_items_in_traversal_order`
- `list_recipes`
- `get_recipe_settings`
- `list_datasets`
- `get_dataset_info`
- `get_dataset_profile`
- `get_dataset_sample`

## Safety Rules

- Discover recipe names and referenced object identifiers through tools; do not invent them.
- Inspect an existing recipe before requesting a modification through Cobuild.
- Use visual recipes unless the user explicitly requests a code-based transformation.
- Preserve the surrounding Flow's storage and dependency context unless the user requests a change.
- Treat a timed-out or interrupted build as potentially still running; inspect the job before retrying or changing related Flow objects.
- Keep this skill focused on inspection, concepts, and Cobuild grounding. Do not document direct recipe mutation workflows here.
