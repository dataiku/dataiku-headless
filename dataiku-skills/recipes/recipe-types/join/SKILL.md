---
name: dataiku-recipe-join
description: "Join two or more datasets with inner, outer, cross, advanced, and anti-join patterns, with optional pre/post-join filters and unmatched-row outputs."
---

# Join Recipe Overview

The join recipe combines two or more input datasets into one output dataset with inner, outer, cross, advanced, and anti-join patterns.

## I/O Requirements

**Inputs:** 2 or more datasets (all role `main`).

**Outputs:**
- 1 joined dataset (role `main`) — required.
- 0 or more unmatched-row datasets (role `unmatchedLeft` or `unmatchedRight`) — optional; availability depends on join type. Read the reference file for the unmatched-role matrix.

## Steps to Create or Update a Join Recipe

Use the parent `recipes` skill for shared lifecycle steps (flow checks, recipe creation/selection, I/O changes, execution).

Then apply join-specific updates:

1. Read current settings with `get_recipe_settings` and inspect `payload`.
2. If unmatched outputs are requested, explicitly resolve which side's unmatched rows are intended before editing outputs or payload.
3. If unmatched output intent is ambiguous and a known-good join recipe exists in the target DSS project, inspect that recipe before mutating anything.
4. Update join structure with `set_recipe_settings` action `set_payload`.

## Required Reference Files

Read these references before editing join recipes:

- [Join recipe settings and payload](references/recipe_settings_and_payload.md) (always).
- [Filter payload reference](../sampling/references/filter_payload.md) (for pre-join or post-join filters).
- [Visual conditions params](../references/visual_conditions_params.md) (shared rules-mode condition fields/operators used in join filters).

Before submitting any `set_payload` or `set_params` call, re-read `references/recipe_settings_and_payload.md` and for each field in the params matrices, make an explicit decision about whether to include it.

## Recipe-Specific Guardrails

1. Keep table indices consistent across `joins[]`, `selectedColumns[]`, and `virtualInputs[]`.
2. Keep join condition operators coherent with field types.
3. Preserve unknown payload keys unless intentionally changing behavior.
4. Validate unmatched output roles against join type constraints.
5. Use `get_dataset_info` on each join input to get its schema and column order before constructing the payload.
6. Order `selectedColumns[]` to match source dataset column order — DSS normalizes column order to match each input dataset's schema when the recipe is opened in the UI. Writing them out-of-order causes a spurious "save" prompt when the user opens the recipe. Call `get_dataset_info` on each input first and preserve their column order.
7. Always include `"computedColumns": []` at the top level of the payload — DSS adds this key on save if it is absent, which also triggers a spurious save prompt.
8. Never translate a user request for "unmatched rows" directly into `unmatchedLeft` or `unmatchedRight` until dataset side and preserved/non-preserved semantics are resolved.
9. Validate unmatched output roles against join type constraints before any mutation.
10. If the requested unmatched side is incompatible with the chosen join type, stop and explain the limitation instead of approximating with a different flow shape.
11. Do not change join orientation purely to satisfy unmatched-output constraints unless the user explicitly approves the changed main-output semantics.
12. If the user wants unmatched rows from the preserved side of an outer join, do not use the built-in join unmatched toggle; use a downstream recipe only if the user accepts that alternative flow shape.
13. Join-type support depends on recipe engine.

## Prefer Multi-Input Joins For Lookup Enrichment

When the task is enriching one stable base dataset with several independent lookup or assumption tables, prefer one multi-input join recipe instead of a chain of pairwise joins when all of these are true:

- each lookup joins directly to the same base grain;
- no intermediate joined output is needed for validation, branching, filtering, or downstream reuse;
- join keys are already available on the base dataset or can be prepared in one upstream recipe;
- row multiplication risks are understood from lookup keys or profiles.

## Unmatched Output Decision Rule

When a user asks for unmatched outputs:

1. Identify the left and right datasets from recipe input order.
2. Identify the join type and therefore the preserved side, if any.
3. Determine whether the user means:
- unmatched rows from one input dataset; or
- rows in the main output whose join columns are null.
4. Map only the first case to `unmatchedLeft` / `unmatchedRight`, and only when the join type allows it.
5. Treat the second case as a different requirement that may need a downstream recipe.

If the user does not specify side, infer the intended side from the business request and then validate it against the allowed unmatched-role matrix in the reference file before mutating the recipe.

## Reference Recipe Pattern

Unmatched-role behavior is easy to confuse in DSS. When unmatched outputs are part of the request and a known-good join recipe is available in the target instance:

1. Inspect that reference recipe first.
2. Treat the live recipe configuration as the source of truth for role usage and payload shape.
3. Only proceed without a reference recipe when the join type, preserved side, and unmatched side are all unambiguous from DSS constraints.

## Type-Specific Update Notes

Use parent rules from `dataiku-skills/recipes/SKILL.md` section `Settings And Payload Update Rules`.

- Join behavior is mainly payload-driven; prefer `set_payload`.
- Use `merge=true, deep_merge=true` only for targeted nested patches (`postFilter`, `virtualInputs[i].preFilter`, etc.).
- `set_params` is usually not needed for join logic.
- Role source for unmatched outputs: `dataikuapi.dss.recipe.DSSJoinRecipeSettings.set_unmatched_output`.
- For unmatched outputs, always cross-check role validity against join type before changing outputs.

## DSS Documentation

- Join recipe docs: https://doc.dataiku.com/dss/latest/other_recipes/join.html
