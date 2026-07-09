---
name: dataiku-recipe-generate_features
description: "Enrich a dataset with generated features for analytics and ML."
---

# Generate Features Recipe Overview

The generate_features recipe builds derived feature columns from one or more input datasets using configured relationships, selected feature families, and optional time-window context.

## I/O Requirements

**Inputs:** 1 primary dataset + 0 or more related datasets (all role `main`); relationships between them are defined in the payload.

**Output:** exactly 1 enriched dataset (role `main`).

## Steps to Create or Update a Generate Features Recipe

Use the parent `recipes` skill for shared lifecycle steps (flow checks, recipe creation/selection, I/O changes, execution).

Then apply generate-features-specific updates:

1. Read current settings with `get_recipe_settings` and inspect `payload`.
2. Update feature-generation behavior with `set_recipe_settings` action `set_payload` (`relationships`, `virtualInputs`, `features`, and `cutoffTime` are the primary control blocks).

## Required Reference Files

Read this reference before editing generate_features recipes:

- [Generate features settings and payload](references/recipe_settings_and_payload.md) (always).

Before submitting any `set_payload` or `set_params` call, re-read `references/recipe_settings_and_payload.md` and for each field in the params matrices, make an explicit decision about whether to include it.

## Recipe-Specific Guardrails

1. In observed generate_features recipes, behavior is payload-driven and `params` is `null`; avoid `set_params` unless explicitly requested.
2. Keep relationship definitions coherent:
- `relationships[]` table indexes must align with `virtualInputs[].index`;
- each `relationships[].on[]` condition must reference valid columns from the linked tables.
3. Keep virtual input blocks coherent:
- preserve `index`/`originLabel` mapping to recipe inputs;
- keep `selectedColumns[]` and optional `outputColumnsSelectionMode` aligned with intended feature generation;
- if using temporal features, keep `timeIndexColumn` and `timeWindows[]` coherent.
4. Keep `features[]` aligned with selected column variable types and time context (for date/time feature families).
5. Preserve `engineParams` unless the user explicitly asks to alter execution behavior.

## Type-Specific Update Notes

Use parent rules from `dataiku-skills/recipes/SKILL.md` section `Settings And Payload Update Rules`.

- For generate_features, prefer `set_payload`; `set_params` is usually unnecessary.
- Use `merge=true, deep_merge=true` only for targeted nested patches (one relationship, one virtual input, or one feature selection block).

## DSS Documentation

- Generate features docs: https://doc.dataiku.com/dss/latest/other_recipes/generate-features.html
