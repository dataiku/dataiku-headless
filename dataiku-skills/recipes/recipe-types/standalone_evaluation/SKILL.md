---
name: standalone-evaluation
description: Inspect standalone evaluation recipes and use their current settings as context for Cobuild. Use when an agent must understand an existing standalone evaluation recipe before asking Cobuild to create or modify that recipe type.
---

# Standalone Evaluation Recipe Context

Use this skill to understand existing standalone evaluation recipes and to gather specifics for Cobuild prompts.

## Workflow

1. Locate the recipe with flow context or `list_recipes`.
2. Inspect it with `get_recipe_settings`.
3. Inspect relevant datasets or evaluation stores with read tools when needed.
4. Route recipe creation, edits, output wiring, and execution through `../../../cobuild/SKILL.md`.

## Safety Rules

- Keep this skill focused on inspection and recipe-type understanding.
- Do not document direct recipe mutation workflows here.
