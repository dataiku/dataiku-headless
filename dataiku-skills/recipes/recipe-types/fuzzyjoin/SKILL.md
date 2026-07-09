---
name: dataiku-recipe-fuzzyjoin
description: "Join exactly two datasets using fuzzy matching distances on text, numeric, date, or geopoint keys, with optional normalization, filters, and matching-detail output."
---

# Fuzzy Join Recipe Overview

The fuzzy join recipe joins exactly two datasets when join keys do not match exactly. It is structurally close to the standard `join` recipe for projection and filtering, but `joins[].on[]` uses fuzzy-distance settings rather than standard comparator operators.

## I/O Requirements

**Inputs:** exactly 2 datasets (both role `main`).

**Outputs:**
- 1 joined dataset (role `main`) — required.

## Steps to Create or Update a Fuzzy Join Recipe

Use the parent `recipes` skill for shared lifecycle steps (flow checks, recipe creation/selection, I/O changes, execution).

Then apply fuzzy-join-specific updates:

1. Read current settings with `get_recipe_settings` and inspect `payload`.
2. Confirm the join-key column types before editing conditions.
3. If the requested distance or normalization pattern is not covered by the reference file, inspect a live DSS example before mutating.
4. Update join structure with `set_recipe_settings` action `set_payload`.

## Required Reference Files

Read these references before editing fuzzy join recipes:

- [Fuzzy join recipe settings and payload](references/recipe_settings_and_payload.md) (always).
- [Filter payload reference](../sampling/references/filter_payload.md) (for pre-join or post-join filters).
- [Visual conditions params](../references/visual_conditions_params.md) (shared rules-mode condition fields/operators used in fuzzy join filters).

Before submitting any `set_payload` or `set_params` call, re-read `references/recipe_settings_and_payload.md` and for each field in the params matrices, make an explicit decision about whether to include it.

## Recipe-Specific Guardrails

1. Fuzzy join is a two-dataset recipe.
2. Keep table indices consistent across `joins[]`, `selectedColumns[]`, and `virtualInputs[]`.
3. Keep fuzzy distance choices coherent with field types. Use text distances on text columns, numeric distances on numeric/date columns, and geospatial distance only on geopoint columns.
4. If all join conditions are strict equality (`EXACT` with zero threshold), prefer a regular `join` recipe unless the user explicitly wants to stay with fuzzy join.
5. Preserve unknown payload keys unless intentionally changing behavior.
6. Use `get_dataset_info` on each fuzzy join input to get its schema and column order before constructing the payload.
7. Order `selectedColumns[]` to match source dataset column order — DSS normalizes column order when the recipe is opened in the UI.
8. Always include `"computedColumns": []` at the top level of the payload.
9. `withMetaColumn=true` adds a `meta` column with join-match details. Only enable it when the user asks for matching diagnostics or explainability.
10. `debugMode=true` forces a cross join and also enables meta-column generation. It can create very large outputs.
11. Text normalization (`normaliseDesc`) can materially change match behavior. Preserve existing normalization flags unless the user explicitly wants different matching semantics.
12. Numeric fuzzy distances may fail on null join-key values; pre-filter nulls first when using them.
13. Fuzzy join only supports the DSS engine. Preserve engine settings unless the user explicitly asks to inspect or change them.

## Type-Specific Update Notes

Use parent rules from `dataiku-skills/recipes/SKILL.md` section `Settings And Payload Update Rules`.

- Fuzzy join behavior is mainly payload-driven; prefer `set_payload`.
- Use `merge=true, deep_merge=true` only for targeted nested patches (`postFilter`, `virtualInputs[i].preFilter`, individual `fuzzyMatchDesc` / `normaliseDesc` blocks, etc.).
- `set_params` is usually not needed for fuzzy join logic.
- The shape is intentionally close to the standard `join` recipe for selected columns, pre/post filters, and virtual inputs, but `joins[].on[]` uses `fuzzyMatchDesc` and optional `normaliseDesc` instead of standard comparator fields.

## DSS Documentation

- Fuzzy join docs: https://doc.dataiku.com/dss/latest/other_recipes/fuzzy-join.html
