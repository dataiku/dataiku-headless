---
name: dataiku-recipe-sync
description: "Copy/sync one dataset to another managed dataset, typically from one storage backend to another. "
---

# Sync Recipe Overview

The sync recipe copies data from one input dataset to one output dataset.

One major use-case of the sync recipe is to copy a dataset between storage backends where different computation are possible (e.g. copying a dataset from S3 into Snowflake so that a Snowflake SQL engine can be used for subsequent recipes).

**I/O:** exactly 1 dataset in (role `main`) → exactly 1 dataset out (role `main`).

## Steps to Create or Update a Sync Recipe

Use the parent `recipes` skill for shared lifecycle steps (flow checks, recipe creation/selection, I/O changes, execution).

Then apply sync-specific updates:

1. Read current settings with `get_recipe_settings` and inspect `params` and `payload`.
2. Update sync behavior with `set_recipe_settings` action `set_params` (`params.schemaMode` is the primary control in observed recipes).

## Required Reference Files

Read these references before editing sync recipes:

- [Sync recipe settings and payload](references/recipe_settings_and_payload.md) (always).

## Recipe-Specific Guardrails

1. In observed sync recipes, behavior is `params`-driven and `payload` is `{}`; avoid payload edits unless explicitly needed.
2. Preserve `params.engineParams` unless the user explicitly asks to alter execution engine behavior.
3. Keep `params.forcePipelineableForTests` unchanged unless working on test-only scenarios.
4. Use supported schema modes (`STRICT_SYNC`, `FREE_SCHEMA_NAME_BASED`).

## Type-Specific Update Notes

Use parent rules from `dataiku-skills/recipes/SKILL.md` section `Settings And Payload Update Rules`.

- For sync, prefer `set_params` updates; `set_payload` is usually unnecessary.
- Safe pattern: read current `params`, update only the intended keys (typically `schemaMode`), and write with `set_params` using `merge=false` for deterministic updates.

## DSS Documentation

- Sync recipe docs: https://doc.dataiku.com/dss/latest/other_recipes/sync.html
