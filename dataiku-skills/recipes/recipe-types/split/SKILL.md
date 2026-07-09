---
name: dataiku-recipe-split
description: "Dispatch rows from one dataset into multiple outputs based on rules."
---

# Split Recipe Overview

The split recipe dispatches rows from one input dataset into multiple output datasets.

## I/O Requirements

**Input:** exactly 1 dataset (role `main`).

**Outputs:** 2 or more datasets (all role `main`) — rows are dispatched among them based on the configured split mode.

## Steps to Create or Update a Split Recipe

Use the parent `recipes` skill for shared lifecycle steps (flow checks, recipe creation/selection, I/O changes, execution).

Then apply split-specific updates:

1. Read current settings with `get_recipe_settings` and inspect `payload`.
2. Update split behavior with `set_recipe_settings` action `set_payload` (`mode`, mode-specific splits arrays, `defaultOutputIndex`, and pre-filter/computed-column blocks are the primary control blocks).

## Required Reference Files

Read these references before editing split recipes:

- [Split recipe settings and payload](references/recipe_settings_and_payload.md) (always).
- [Filter payload reference](../sampling/references/filter_payload.md) (for `preFilter`, `rangeSplits[].filter`, and `filterSplits[].filter`).
- [Visual conditions params](../references/visual_conditions_params.md) (shared rules-mode condition fields/operators used in split filters).

Before submitting any `set_payload` or `set_params` call, re-read `references/recipe_settings_and_payload.md` and for each field in the params matrices, make an explicit decision about whether to include it.

## Recipe-Specific Guardrails

1. In observed split recipes, behavior is payload-driven and `params` is empty; avoid `set_params` unless explicitly requested.
2. Keep `mode` coherent with its active split-definition block:
- `VALUES` -> `valueSplits` + top-level `"column"` key (required — builds fail without it)
- `RANGE` -> `rangeSplits`
- `RANDOM` -> `randomSplits`
- `RANDOM_COLUMNS` -> `randomColumns` + `randomColumnsSplits`
- `FILTERS` -> `filterSplits`
- `CENTILE` -> `centileOrders` + `centileSplits`
3. Keep each split entry `outputIndex` aligned with actual output order, and keep `defaultOutputIndex` aligned with fallback output behavior.
4. For percentage/share modes (`randomSplits`, `randomColumnsSplits`, `centileSplits`), keep shares coherent and non-overlapping with fallback expectations.
5. Preserve `engineParams` unless the user explicitly asks to alter execution behavior.
6. Preserve computed-column behavior consistency between `computedColumns` and `writeComputedColumnsInOutput`.

## Type-Specific Update Notes

Use parent rules from `dataiku-skills/recipes/SKILL.md` section `Settings And Payload Update Rules`.

- For split, prefer `set_payload`; `set_params` is usually unnecessary.
- Use `merge=true, deep_merge=true` only for targeted nested patches (`preFilter`, one mode split entry, or one filter block).

## DSS Documentation

- Split recipe docs: https://doc.dataiku.com/dss/latest/other_recipes/split.html
