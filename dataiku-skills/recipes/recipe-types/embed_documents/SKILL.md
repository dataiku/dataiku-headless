---
name: embed-documents
description: Inspect embed_documents recipes and use their current settings as context for Cobuild. Use when an agent must understand an existing embed_documents recipe before asking Cobuild to create or modify that recipe type.
---

# Embed Documents Recipe Context

Use this skill to understand existing embed_documents recipes and to gather specifics for Cobuild prompts.

## Workflow

1. Locate the recipe with flow context or `list_recipes`.
2. Inspect it with `get_recipe_settings`.
3. Inspect relevant folder or knowledge-bank inputs and outputs with read tools when needed.
4. Route recipe creation, edits, output wiring, and execution through `../../../cobuild/SKILL.md`.

## Safety Rules

- Keep this skill focused on inspection and recipe-type understanding.
- Do not document direct recipe mutation workflows here.
