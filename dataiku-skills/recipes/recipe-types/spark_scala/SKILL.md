---
name: spark-scala
description: Inspect Spark Scala recipes and use their current settings as context for Cobuild. Use when an agent must understand an existing Spark Scala recipe before asking Cobuild to create or modify that recipe type.
---

# Spark Scala Recipe Context

Use this skill to understand existing Spark Scala recipes and to gather specifics for Cobuild prompts.

## Workflow

1. Locate the recipe with flow context or `list_recipes`.
2. Inspect it with `get_recipe_settings`.
3. Inspect relevant inputs, outputs, or environment context with read tools when needed.
4. Route recipe creation, edits, output wiring, and execution through `../../../cobuild/SKILL.md`.

## Safety Rules

- Use code recipes only when the user explicitly requests code.
- Do not document direct recipe mutation workflows here.
