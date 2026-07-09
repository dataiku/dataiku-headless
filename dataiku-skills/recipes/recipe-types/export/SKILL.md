---
name: dataiku-recipe-export
description: "Export dataset rows to files with format, filtering, and naming controls."
---

# Export Recipe Overview

The export recipe writes rows from one input dataset to exported files within an output folder, with configurable file format, optional row filtering, filename/timestamp controls, and read-selection options.

## I/O Requirements

**Input:** exactly 1 dataset (role `main`).

**Output:** exactly 1 managed folder (role `main`). Pass the folder **ID** (not display name) to `create_recipe`.

## Steps to Create or Update an Export Recipe

Use the parent `recipes` skill for shared lifecycle steps (flow checks, recipe creation/selection, I/O changes, execution).

Then apply export-specific updates:

1. Read current settings with `get_recipe_settings` and inspect `params`.
2. Update export behavior with `set_recipe_settings` action `set_params` (export destination/format, selection, filters, and filename/timestamp blocks are the primary control blocks).

## Required Reference Files

Read these references before editing export recipes:

- [Export recipe settings and payload](references/recipe_settings_and_payload.md) (always).
- [Filter payload reference](../sampling/references/filter_payload.md) (for `params.filter` and `params.exportParams.selection.filter`).
- [Visual conditions params](../references/visual_conditions_params.md) (shared rules-mode condition fields/operators used in filters).

Before submitting any `set_params` call, re-read `references/recipe_settings_and_payload.md` and for each field in the params matrices, make an explicit decision about whether to include it.

## Recipe-Specific Guardrails

1. In observed export recipes, behavior is params-driven and payload is not used; prefer `set_params` over `set_payload`.
2. Keep `params.exportParams` coherent:
- destination/format fields (`destinationType`, `originatingOptionId`, `format.type`, `format.params`) should be aligned;
- keep selection settings in `exportParams.selection` coherent with filter/sampling/ordering toggles.
3. Preserve instance-specific routing/storage fields unless explicitly requested (`destinationDatasetProjectKey`, `destinationDatasetConnection`, `containerSelection`).
4. For output folder changes, use `set_recipe_settings` action `set_outputs` and reference discovered folder ids/names from `list_managed_folders` (do not attempt output wiring through params).
5. Keep naming controls coherent:
- if `timestampPrefix.enabled=true`, keep a valid `timestampPrefix.format`;
- if `outputFilename` is set, keep it compatible with downstream naming expectations.
6. Keep recipe-level `filter` consistent with selection filter intent. In observed recipes, `params.filter` controls export filtering behavior.
7. Preserve `variablesExpansionLoopConfig` unless the user explicitly requests dynamic variable loop behavior.

## Type-Specific Update Notes

Use parent rules from `dataiku-skills/recipes/SKILL.md` section `Settings And Payload Update Rules`.

- For export, prefer `set_params`; `set_payload` is usually unnecessary.
- For deterministic edits of complex nested params, read current params then use `set_params` with `merge=false`.

## DSS Documentation

- Dynamic recipe repeat / export docs: https://doc.dataiku.com/dss/latest/other_recipes/dynamic-repeat.html
