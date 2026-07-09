---
name: dataiku-recipe-sampling
description: "Sample and/or filter dataset rows in one visual recipe."
---

# Sampling Recipe Overview

The sampling recipe selects a subset of rows from one input dataset and writes the result to one output dataset.

It supports multiple sampling strategies (full pass-through, fixed-size, fixed-ratio, class rebalancing, and ordered sampling), plus an optional row filter payload.

**I/O:** exactly 1 dataset in (role `main`) → exactly 1 dataset out (role `main`).

## Steps to Create or Update a Sampling Recipe

Use the parent `recipes` skill for shared lifecycle steps (flow checks, recipe creation/selection, I/O changes, execution).

Then apply sampling-specific updates:

1. Read current settings with `get_recipe_settings` and inspect both `params` and `payload`.
2. Update sampling behavior with `set_recipe_settings` action `set_params` and `merge=false` (`params.selection` is the main control block).
3. If row filtering is needed, prefer rules mode over formula mode or SQL mode.
4. Update optional row filtering with `set_recipe_settings` action `set_payload` and `merge=false`.
5. Steps 2 and 4 can be combined into a single `set_recipe_settings` call with both operations in sequence.

## Required Reference Files

Read these references before editing sampling recipes:

- [Sampling recipe settings and payload](references/recipe_settings_and_payload.md) (always).
- [Filter payload reference](references/filter_payload.md) (when enabling or changing row filters).

Before submitting any `set_payload` or `set_params` call, re-read `references/recipe_settings_and_payload.md` and for each field in the params matrices, make an explicit decision about whether to include it.

## Recipe-Specific Guardrails

1. Treat `params.selection` as one coherent block; avoid piecemeal edits that drop required sibling keys.
2. Keep `params.engineParams` unchanged unless the user explicitly asks to alter execution behavior.
3. Keep filter semantics coherent with sampling intent (for example, avoid enabling filters while leaving incomplete rule blocks).
4. Prefer rules mode when the filter can be expressed with visual conditions.

## Type-Specific Update Notes

Use parent rules from `dataiku-skills/recipes/SKILL.md` section `Settings And Payload Update Rules`.

- For sampling, treat `params.selection` as one logical block.
- Safe pattern: read current `params`, update only `params.selection`, keep `engineParams` unchanged, then write with `set_params` and `merge=false`.
- For filter changes, write the full filter object with `set_payload` and `merge=false`; both operations can be sent in one `set_recipe_settings` call.

## DSS Documentation

- Sampling recipe + filtering modes: https://doc.dataiku.com/dss/latest/other_recipes/sampling.html#sampling-datasets
- Sampling method semantics: https://doc.dataiku.com/dss/latest/sampling/index.html
