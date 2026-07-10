---
name: join
description: Inspect join recipes and use their current settings as context for Cobuild. Use when an agent must understand an existing join recipe before asking Cobuild to create or modify that recipe type.
---

# Join Recipe Context

Use this skill to understand existing join recipes and to gather specifics for Cobuild prompts.

## Workflow

1. Locate the recipe with flow context or `list_recipes`.
2. Inspect it with `get_recipe_settings`.
3. Inspect relevant input schemas with dataset read tools when needed.
4. Route recipe creation, edits, output wiring, and execution through `../../../cobuild/SKILL.md`.

## Safety Rules

- Keep this skill focused on inspection and recipe-type understanding.
- Do not document direct recipe mutation workflows here.
