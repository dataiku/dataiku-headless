---
name: dataiku-recipe-topn
description: "Retrieve top/bottom rows per group using ordered columns."
---

# TopN Recipe Overview

The topn recipe keeps first and/or last rows by ordering rules, globally or within grouping keys.

**I/O:** exactly 1 dataset in (role `main`) → exactly 1 dataset out (role `main`).

## Steps to Create or Update a TopN Recipe

Use the parent `recipes` skill for shared lifecycle steps (flow checks, recipe creation/selection, I/O changes, execution).

Then apply topn-specific updates:

1. Read current settings with `get_recipe_settings` and inspect `payload`.
2. Update topn behavior with `set_recipe_settings` action `set_payload` (`firstRows`, `lastRows`, `orders`, `keys`, ranking flags, filters, and computed columns are the primary control blocks).

## Required Reference Files

Read these references before editing topn recipes:

- [TopN recipe settings and payload](references/recipe_settings_and_payload.md) (always).
- [Filter payload reference](../sampling/references/filter_payload.md) (for `preFilter`).
- [Visual conditions params](../references/visual_conditions_params.md) (shared rules-mode condition fields/operators used in filters).

Before submitting any `set_payload` or `set_params` call, re-read `references/recipe_settings_and_payload.md` and for each field in the params matrices, make an explicit decision about whether to include it.

## Recipe-Specific Guardrails

1. In observed topn recipes, behavior is payload-driven and `params` is `null`; avoid `set_params` unless explicitly requested.
2. Keep row selection controls coherent:
- `firstRows` controls top rows kept per partition/global ordering;
- `lastRows` controls bottom rows kept per partition/global ordering;
- use `duplicateCount=true` only when ties should expand output row count.
3. Keep grouping and ordering coherent:
- `keys[]` defines per-group partitions (empty means global topn);
- `orders[]` defines ranking/sorting precedence and direction.
4. If any of `rowNumber`, `rank`, or `denseRank` is enabled, ensure `orders[]` is present and deterministic for expected output stability.
5. Keep retrieval controls coherent:
- `retrievedColumnsSelectionMode=ALL` should usually keep `retrievedColumns` as full input (plus computed columns);
- `retrievedColumnsSelectionMode=EXPLICIT` requires a coherent `retrievedColumns[]` subset.
6. Preserve `engineParams` and `outputColumnNameOverrides` unless explicitly requested.
7. Keep `computedColumns` and `preFilter` coherent when ranking/filtering on derived values.

## Type-Specific Update Notes

Use parent rules from `dataiku-skills/recipes/SKILL.md` section `Settings And Payload Update Rules`.

- For topn, prefer `set_payload`; `set_params` is usually unnecessary.
- Use `merge=true, deep_merge=true` only for targeted nested patches (`preFilter`, one `orders[i]`, or one `computedColumns[i]` entry).

## DSS Documentation

- TopN recipe docs: https://doc.dataiku.com/dss/latest/other_recipes/topn.html
