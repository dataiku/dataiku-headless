---
name: recipes
description: Inspect Dataiku recipes and use their current settings as grounding for Cobuild. Use when an agent must discover recipes, inspect recipe settings, or understand recipe types before asking Cobuild to create, edit, or build project assets.
---

# Recipe Inspection

Use this skill to inspect existing recipes and gather context for Cobuild.

## Workflow

1. Use `get_flow_items_in_traversal_order`, `list_recipes`, and `list_datasets` when you need flow context.
2. Use `get_recipe_settings` to inspect a specific recipe before asking Cobuild to modify it.
3. Use dataset inspection tools when input or output schema details matter.
4. If the task requires creating, editing, wiring, or executing a recipe, route that work through `./dataiku-skills/cobuild/SKILL.md`.
5. Use the recipe-type child skills as supporting context only when you need help understanding how a specific recipe family behaves.

## Preferred Tools

- `get_flow_items_in_traversal_order`
- `list_recipes`
- `get_recipe_settings`
- `list_datasets`
- `get_dataset_info`
- `get_dataset_profile`
- `get_dataset_sample`

## Safety Rules

- Prefer visual recipe families unless the user explicitly requests code.
- Keep this skill focused on inspection and Cobuild grounding.
- Do not document non-Cobuild recipe mutation workflows here.
