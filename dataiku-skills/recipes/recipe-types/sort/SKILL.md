---
name: dataiku-recipe-sort
description: "Order dataset rows by selected columns and sort directions."
---

# Sort Recipe Overview

The sort recipe orders rows from one input dataset into one output dataset using one or more ordering keys.

**I/O:** exactly 1 dataset in (role `main`) → exactly 1 dataset out (role `main`).

## Steps to Create or Update a Sort Recipe

Use the parent `recipes` skill for shared lifecycle steps (flow checks, recipe creation/selection, I/O changes, execution).

Then apply sort-specific updates:

1. Read current settings with `get_recipe_settings` and inspect `payload`.
2. Update sort behavior with `set_recipe_settings` action `set_payload` (`orders`, rank flags, and prefilter/computed-column blocks are the primary control blocks).

## Required Reference Files

Read these references before editing sort recipes:

- [Sort recipe settings and payload](references/recipe_settings_and_payload.md) (always).
- [Filter payload reference](../sampling/references/filter_payload.md) (for `preFilter`).
- [Visual conditions params](../references/visual_conditions_params.md) (shared rules-mode condition fields/operators used in filters).

Before submitting any `set_payload` or `set_params` call, re-read `references/recipe_settings_and_payload.md` and for each field in the params matrices, make an explicit decision about whether to include it.

## Recipe-Specific Guardrails

1. In observed sort recipes, behavior is payload-driven and `params` is empty; avoid `set_params` unless explicitly requested.
2. Keep `orders[]` coherent with available columns and intended precedence (order of entries defines sort priority).
3. If any of `rowNumber`, `rank`, or `denseRank` is enabled, ensure `orders[]` is present and deterministic for expected output stability.
4. Handle DSS order-preservation warnings explicitly. Some dataset/storage types (for example SQL datasets) do not preserve write order, so sort output order may not be stable when read later. If deterministic downstream behavior is required, add an explicit ordering key (for example enable `rowNumber`) and use that key in downstream logic.
5. Preserve `engineParams` unless the user explicitly asks to alter execution behavior.
6. Preserve `outputColumnNameOverrides` unless intentionally renaming generated output columns.
7. Keep `computedColumns` and `preFilter` coherent when filtering/sorting on derived values.

## Type-Specific Update Notes

Use parent rules from `dataiku-skills/recipes/SKILL.md` section `Settings And Payload Update Rules`.

- For sort, prefer `set_payload`; `set_params` is usually unnecessary.
- Use `merge=true, deep_merge=true` only for targeted nested patches (`preFilter`, one order entry, or `computedColumns`).

## DSS Documentation

- Sort recipe docs: https://doc.dataiku.com/dss/latest/other_recipes/sort.html
