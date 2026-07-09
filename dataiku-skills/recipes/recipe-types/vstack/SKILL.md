---
name: dataiku-recipe-vstack
description: "Stack multiple datasets into one with union/intersect/remap/custom column-matching modes."
---

# VStack Recipe Overview

The vstack recipe stacks multiple input datasets into one output dataset, equivalent to SQL `UNION ALL`.

## I/O Requirements

**Inputs:** 2 or more datasets (all role `main`).

**Output:** exactly 1 dataset (role `main`).

## Steps to Create or Update a VStack Recipe

Use the parent `recipes` skill for shared lifecycle steps (flow checks, recipe creation/selection, I/O changes, execution).

Then apply vstack-specific updates:

1. Read current settings with `get_recipe_settings` and inspect `payload`.
2. Update vstack structure with `set_recipe_settings` action `set_payload` (`mode`, `selectedColumns`, `virtualInputs`, `postFilter` are the primary control blocks).

## Required Reference Files

Read these references before editing vstack recipes:

- [VStack recipe settings and payload](references/recipe_settings_and_payload.md) (always).
- [Filter payload reference](../sampling/references/filter_payload.md) (for `virtualInputs[i].preFilter` or `postFilter`).
- [Visual conditions params](../references/visual_conditions_params.md) (shared rules-mode condition fields/operators used in filters).

Before submitting any `set_payload` or `set_params` call, re-read `references/recipe_settings_and_payload.md` and for each field in the params matrices, make an explicit decision about whether to include it.

## Recipe-Specific Guardrails

1. In observed vstack recipes, behavior is payload-driven and `params` is empty; avoid `set_params` unless the user explicitly requests it.
2. Keep `virtualInputs[].index` aligned with input order and keep one `virtualInputs` entry per input dataset.
3. Keep mode-specific blocks coherent:
- `FROM_INDEX`: maintain `selectedColumnsIndexes` aligned with `selectedColumns`.
- `REMAP`: maintain `virtualInputs[i].columnsMatch` lists aligned to `selectedColumns`.
- `FROM_DATASET` / `FROM_INDEX` / `REMAP`: preserve `copySchemaFromDatasetWithName` unless intentionally changing schema source.
4. Use `get_dataset_info` on each input to get its schema before constructing the payload.
5. Preserve `engineParams` unless the user explicitly asks to alter execution behavior.
6. If `addOriginColumn=true`, keep `originColumnName` set and validate origin-column schema impact.

## Type-Specific Update Notes

Use parent rules from `dataiku-skills/recipes/SKILL.md` section `Settings And Payload Update Rules`.

- For vstack, prefer `set_payload`; `set_params` is usually unnecessary.
- Use `merge=true, deep_merge=true` only for targeted nested patches (`virtualInputs[i].preFilter`, `postFilter`, or one mode-specific block).

## DSS Documentation

- VStack/stack recipe docs: https://doc.dataiku.com/dss/latest/other_recipes/stack.html
