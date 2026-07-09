---
name: dataiku-recipe-pivot
description: "Build pivot tables with configurable rows, columns, and aggregations."
---

# Pivot Recipe Overview

The pivot recipe reshapes rows into columns by pivot key(s), with configurable value limits, aggregates, identifiers, filters, and computed columns.

**I/O:** exactly 1 dataset in (role `main`) → exactly 1 dataset out (role `main`).

## Steps to Create or Update a Pivot Recipe

Use the parent `recipes` skill for shared lifecycle steps (flow checks, recipe creation/selection, I/O changes, execution).

Then apply pivot-specific updates:

1. Read current settings with `get_recipe_settings` and inspect `payload`.
2. Update pivot behavior with `set_recipe_settings` action `set_payload` (`pivots`, identifiers, other columns, and prefilter/computed-column blocks are the primary control blocks).

## Required Reference Files

Read these references before editing pivot recipes:

- [Pivot recipe settings and payload](references/recipe_settings_and_payload.md) (always).
- [Filter payload reference](../sampling/references/filter_payload.md) (for `preFilter`).
- [Visual conditions params](../references/visual_conditions_params.md) (shared rules-mode condition fields/operators used in filters).

Before submitting any `set_payload` or `set_params` call, re-read `references/recipe_settings_and_payload.md` and for each field in the params matrices, make an explicit decision about whether to include it.

## Recipe-Specific Guardrails

1. In observed pivot recipes, behavior is payload-driven and `params` is empty; avoid `set_params` unless explicitly requested.
2. Keep `pivots[]` coherent:
- `keyColumns` define pivot dimensions;
- `valueColumns` define pivoted metric outputs;
- `valueLimit` controls modality inclusion strategy (`NO_LIMIT`, `TOP_N`, `AT_LEAST_N_OCC`, `EXPLICIT`).
3. When `valueLimit=EXPLICIT`, keep `explicitValues` coherent with `keyColumns` cardinality.
4. Keep identifier behavior coherent:
- `identifierColumnsSelection=EXPLICIT` requires `explicitIdentifiers`;
- `identifierColumnsSelection=ALL_BUT_USED` should typically keep `explicitIdentifiers` empty.
5. Preserve `engineParams`, schema/modality naming controls (`schemaComputation`, `modalitySlugification`, `$withModalityMaxLength`, `modalityMaxLength`) unless the user explicitly asks to alter them.
6. Keep ordering-sensitive aggregates (`first`/`last`) coherent with `orderColumn` where present.

## Type-Specific Update Notes

Use parent rules from `dataiku-skills/recipes/SKILL.md` section `Settings And Payload Update Rules`.

- For pivot, prefer `set_payload`; `set_params` is usually unnecessary.
- Use `merge=true, deep_merge=true` only for targeted nested patches (`preFilter`, one pivot definition, `otherColumns`, or `computedColumns`).

## DSS Documentation

- Pivot recipe docs: https://doc.dataiku.com/dss/latest/other_recipes/pivot.html
