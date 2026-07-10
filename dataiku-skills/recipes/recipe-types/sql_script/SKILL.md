---
name: sql-script
description: Inspect SQL script recipes and use their current settings as context for Cobuild. Use when an agent must understand an existing SQL script recipe before asking Cobuild to create or modify that recipe type.
---

# SQL Script Recipe Context

Use this skill to understand existing SQL script recipes and to gather specifics for Cobuild prompts.

## Workflow

1. Locate the recipe with flow context or `list_recipes`.
2. Inspect it with `get_recipe_settings`.
3. Inspect relevant inputs, outputs, or SQL-dataset context with read tools when needed.
4. Route recipe creation, edits, output wiring, and execution through `../../../cobuild/SKILL.md`.

## Safety Rules

- Use code recipes only when the user explicitly requests code.
- Do not document direct recipe mutation workflows here.
