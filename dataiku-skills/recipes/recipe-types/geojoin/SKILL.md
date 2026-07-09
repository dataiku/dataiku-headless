---
name: dataiku-recipe-geojoin
description: "Join two or more datasets on geospatial relationships such as distance, containment, intersection, and touch predicates."
---

# Geo Join Recipe Overview

The geo join recipe is structurally very close to the standard `join` recipe: the same overall payload blocks (`joins`, `selectedColumns`, `virtualInputs`, `postFilter`, `computedColumns`) are used, but the join conditions are geospatial instead of standard equality/range conditions.

## I/O Requirements

**Inputs:** 2 or more datasets (all role `main`).

**Outputs:**
- 1 joined dataset (role `main`) - required.

## Steps to Create or Update a Geo Join Recipe

Use the parent `recipes` skill for shared lifecycle steps (flow checks, recipe creation/selection, I/O changes, execution).

Then apply geo-join-specific updates:

1. Read current settings with `get_recipe_settings` and inspect `payload`.
2. Confirm that each join operand column is geospatial (`geopoint` or `geometry`) before editing conditions.
3. If the user requests a geospatial predicate or unit not covered by the reference file and no known-good live recipe exists, stop and inspect a live DSS example before mutating anything.
4. Update join structure with `set_recipe_settings` action `set_payload`.

## Required Reference Files

Read these references before editing geo join recipes:

- [Geo join recipe settings and payload](references/recipe_settings_and_payload.md) (always).
- [Filter payload reference](../sampling/references/filter_payload.md) (for pre-join or post-join filters).
- [Visual conditions params](../references/visual_conditions_params.md) (shared rules-mode condition fields/operators used in geo join filters).

Before submitting any `set_payload` or `set_params` call, re-read `references/recipe_settings_and_payload.md` and for each field in the params matrices, make an explicit decision about whether to include it.

## Recipe-Specific Guardrails

1. Keep table indices consistent across `joins[]`, `selectedColumns[]`, and `virtualInputs[]`.
2. Only join geospatial columns to geospatial columns; do not mix standard scalar columns into `joins[].on[]`.
3. Preserve unknown payload keys unless intentionally changing behavior.
4. Use `get_dataset_info` on each geo join input to get its schema and column order before constructing the payload.
5. Order `selectedColumns[]` to match source dataset column order - DSS normalizes column order to match each input dataset's schema when the recipe is opened in the UI. Writing them out-of-order causes a spurious "save" prompt when the user opens the recipe. Call `get_dataset_info` on each input first and preserve their column order.
6. Always include `"computedColumns": []` at the top level of the payload - DSS adds this key on save if it is absent, which also triggers a spurious save prompt.
7. Preserve `unit`, `threshold`, and `dateDiffUnit` for existing geospatial conditions unless you are intentionally changing them. The live DSS examples consistently carry these fields, including on topological predicates.
8. Keep the geospatial operator coherent with the join type and business intent. For example, `DWITHIN` and `BEYOND` are distance-threshold predicates; `CONTAINS`, `WITHIN`, `INTERSECTS`, `DISJOINT`, and `TOUCHES` are topological predicates.
9. If the user asks for an unsupported or unverified geospatial predicate, do not approximate it with a different operator. Inspect a live reference recipe first.
10. Geo join supports the same pre-filter, post-filter, and selected-columns workflow as the standard `join` recipe. Reuse the same filter/reference rules and the same duplicate-column handling patterns.
11. Geo join supports the same join-type family as the standard `join` recipe. The difference is the geospatial condition model inside `joins[].on[]`, not the overall join-structure workflow.
12. Geo-join type support may vary by engine. Preserve `engineParams` unless the user explicitly asks to change engine behavior.

## Type-Specific Update Notes

Use parent rules from `dataiku-skills/recipes/SKILL.md` section `Settings And Payload Update Rules`.

- Geo join behavior is mainly payload-driven; prefer `set_payload`.
- Use `merge=true, deep_merge=true` only for targeted nested patches (`postFilter`, `virtualInputs[i].preFilter`, etc.).
- `set_params` is usually not needed for geo join logic.
- The shape is intentionally close to the standard `join` recipe: the same filter blocks, projection patterns, and virtual-input structure apply, but `joins[].on[]` uses geospatial predicate fields rather than standard scalar comparator fields.

## DSS Documentation

- Geo join docs: https://doc.dataiku.com/dss/latest/geographic/geojoin.html
