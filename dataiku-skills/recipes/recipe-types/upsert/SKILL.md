---
name: dataiku-recipe-upsert
description: "Merge incoming rows by keys with update-and-insert behavior (upsert)."
---

# Upsert Recipe Overview

The upsert recipe consolidates input rows into a target dataset by key, updating matching rows and inserting non-matching rows.

**I/O:** exactly 1 dataset in (role `main`) → exactly 1 dataset out (role `main`).

## Steps to Create or Update an Upsert Recipe

Use the parent `recipes` skill for shared lifecycle steps (flow checks, recipe creation/selection, I/O changes, execution).

Then apply upsert-specific updates:

1. Read current settings with `get_recipe_settings` and inspect `payload`.
2. Update upsert behavior with `set_recipe_settings` action `set_payload` (`keys`, upsert modes, and optional prefilter/computed-column blocks are the primary control blocks).

## Required Reference Files

Read these references before editing upsert recipes:

- [Upsert recipe settings and payload](references/recipe_settings_and_payload.md) (always).
- [Filter payload reference](../sampling/references/filter_payload.md) (for `preFilter`).
- [Visual conditions params](../references/visual_conditions_params.md) (shared rules-mode condition fields/operators used in filters).

Before submitting any `set_payload` or `set_params` call, re-read `references/recipe_settings_and_payload.md` and for each field in the params matrices, make an explicit decision about whether to include it.

## Recipe-Specific Guardrails

1. In observed upsert recipes, behavior is payload-driven and `params` is `null`; avoid `set_params` unless explicitly requested.
2. Keep key mapping coherent:
- `keys[]` entries define match keys via `{"column": "<column_name>"}`;
- ensure key columns exist in input/output schema and align with upsert uniqueness expectations.
3. Preserve mode controls unless explicitly requested:
- `upsertSQLMode` (observed: `PREPARE_THEN_REPLACE`);
- `upsertIndexMode` (observed: `USE_EXISTING`).
4. Preserve `engineParams` unless the user explicitly asks to alter execution behavior.
5. Keep `computedColumns` and `preFilter` coherent when using derived keys or filtering before upsert.

## Type-Specific Update Notes

Use parent rules from `dataiku-skills/recipes/SKILL.md` section `Settings And Payload Update Rules`.

- For upsert, prefer `set_payload`; `set_params` is usually unnecessary.
- Use `merge=true, deep_merge=true` only for targeted nested patches (`preFilter` or one `computedColumns[i]` entry).

## DSS Documentation

- Upsert recipe docs: https://doc.dataiku.com/dss/latest/other_recipes/upsert.html
