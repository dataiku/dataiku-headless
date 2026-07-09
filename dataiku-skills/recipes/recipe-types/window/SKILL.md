---
name: dataiku-recipe-window
description: "Compute SQL OVER-style window analytics."
---

# Window Recipe Overview

The window recipe computes window analytics (aggregations, rank/row_number metrics, lag/lead, and custom window expressions) over one input dataset.

**I/O:** exactly 1 dataset in (role `main`) → exactly 1 dataset out (role `main`).

## Steps to Create or Update a Window Recipe

Use the parent `recipes` skill for shared lifecycle steps (flow checks, recipe creation/selection, I/O changes, execution).

Then apply window-specific updates:

1. Read current settings with `get_recipe_settings` and inspect `payload`.
2. Update window behavior with `set_recipe_settings` action `set_payload` (`windows`, `values`, rank/ntile flags, filters, and computed/custom columns are the primary control blocks).

## Required Reference Files

Read these references before editing window recipes:

- [Window recipe settings and payload](references/recipe_settings_and_payload.md) (always).
- [Filter payload reference](../sampling/references/filter_payload.md) (for `preFilter` and `postFilter`).
- [Visual conditions params](../references/visual_conditions_params.md) (shared rules-mode condition fields/operators used in filters).

Before submitting any `set_payload` or `set_params` call, re-read `references/recipe_settings_and_payload.md` and for each field in the params matrices, make an explicit decision about whether to include it.

## Recipe-Specific Guardrails

1. In observed window recipes, behavior is payload-driven and `params` is empty; avoid `set_params` unless explicitly requested.
2. Keep `windows[]` internally coherent:
- if `enablePartitioning=true`, provide `partitioningColumns`;
- if `enableOrdering=true`, provide `orders`;
- if `enableLimits=true`, keep `windowLimitMode` and limit bounds (`windowLowerBound` / `windowUpperBound`, row/date mode fields) coherent.
3. For order-sensitive window metrics (`first`, `last`, `lag`, `lead`, lag/lead diff), provide coherent ordering context (`windows[].orders`, and `orderColumn` where used in `values[]`).
4. Keep `retrievedColumnsSelectionMode` coherent with `values[].value` selections (especially in `EXPLICIT` mode where `value=true` drives passthrough columns).
5. When enabling window-level rank outputs (`rowNumber`, `rank`, `denseRank`, `cumeDist`, `ntile`), validate output naming and prefix behavior across one or many windows.
6. Preserve `engineParams` unless the user explicitly asks to alter execution behavior.
7. Preserve existing `outputColumnNameOverrides` unless intentionally changing output column names.

## Type-Specific Update Notes

Use parent rules from `dataiku-skills/recipes/SKILL.md` section `Settings And Payload Update Rules`.

- For window, prefer `set_payload`; `set_params` is usually unnecessary.
- Use `merge=true, deep_merge=true` only for targeted nested patches (`preFilter`, `postFilter`, one `windows[i]`, or one `values[i]` entry).

## DSS Documentation

- Window recipe docs: https://doc.dataiku.com/dss/latest/other_recipes/window.html
