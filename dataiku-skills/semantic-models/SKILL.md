---
name: semantic-models
description: Inspect Dataiku semantic models and their versions. Use when an agent must understand existing semantic-model structure before asking Cobuild to create or modify project assets.
---

# Semantic Model Inspection

Use this skill to inspect existing semantic models.

## Workflow

1. Use `list_semantic_models` to discover models and version ids.
2. Use `get_semantic_model_version_settings` to inspect the active or requested version.
3. Route semantic-model creation, versioning, activation, indexing, and deletion through `./dataiku-skills/cobuild/SKILL.md`.

## Preferred Tools

- `list_semantic_models`
- `get_semantic_model_version_settings`

## Safety Rules

- Never invent semantic model ids or version ids.
- Keep this skill focused on inspection and Cobuild grounding.
