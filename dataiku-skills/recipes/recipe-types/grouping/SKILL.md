---
name: dataiku-recipe-grouping
description: "Aggregate rows by group keys with metric aggregations and optional custom aggregate expressions."
---

# Grouping Recipe Overview

The grouping recipe aggregates one input dataset into one output dataset, similar to SQL `GROUP BY`.

Use this skill with `recipes` for work focused on recipe type `grouping`.

**I/O:** exactly 1 dataset in (role `main`) → exactly 1 dataset out (role `main`).

## Steps to Create or Update a Grouping Recipe

Use the parent `recipes` skill for shared lifecycle steps (flow checks, recipe creation/selection, I/O changes, execution).

Then apply grouping-specific updates:

1. Read current settings with `get_recipe_settings` and inspect `payload`.
2. Update grouping structure with `set_recipe_settings` action `set_payload`.

## Required Reference Files

Read these references before editing grouping recipes:

- [Grouping recipe settings and payload](references/recipe_settings_and_payload.md) (always).
- [Filter payload reference](../sampling/references/filter_payload.md) (when enabling or changing `preFilter` or `postFilter`).
- [Visual conditions params](../references/visual_conditions_params.md) (shared rules-mode condition fields/operators used in filters).

Before submitting any `set_payload` or `set_params` call, re-read `references/recipe_settings_and_payload.md` and for each field in the params matrices, make an explicit decision about whether to include it.

## Recipe-Specific Guardrails

1. Keep `keys[]` and `values[]` aligned with the current input schema; preserve DSS metadata keys (for example `$idx`, `$selected`) unless intentionally rebuilding the payload.
2. In `keys[]`, use grouping columns only; list must be nonempty; keep metric flags disabled there.
3. In `values[]`, each selected metric must have at least one aggregation flag enabled (`count`, `sum`, `avg`, `min`, `max`, `median`, `stddev`, `first`, `last`, etc.) or a custom aggregate expression (`customExpr` + `customName`).
4. If using `first`, `last`, or `firstLastNotNull`, set `orderColumn` to make ordering deterministic.
5. Preserve `engineParams` and `engineType` unless the user explicitly asks to change execution behavior.

## Type-Specific Update Notes

Use parent rules from `dataiku-skills/recipes/SKILL.md` section `Settings And Payload Update Rules`.

- Grouping behavior is payload-driven; prefer `set_payload`.
- `set_params` is usually not needed for grouping logic.
- Use `merge=true, deep_merge=true` only for targeted nested patches (`preFilter`, `postFilter`, or individual `values[]` entries).

## DSS Documentation

- Grouping recipe docs: https://doc.dataiku.com/dss/latest/other_recipes/grouping.html
