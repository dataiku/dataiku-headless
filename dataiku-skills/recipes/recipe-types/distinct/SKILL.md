---
name: dataiku-recipe-distinct
description: "Deduplicate rows by selected columns, with optional duplicate-count output."
---

# Distinct Recipe Overview

The distinct recipe deduplicates rows from one input dataset into one output dataset.

It can deduplicate by selected key columns or by whole-row values, and can optionally output duplicate-group counts.

**I/O:** exactly 1 dataset in (role `main`) → exactly 1 dataset out (role `main`).

## Steps to Create or Update a Distinct Recipe

Use the parent `recipes` skill for shared lifecycle steps (flow checks, recipe creation/selection, I/O changes, execution).

Then apply distinct-specific updates:

1. Read current settings with `get_recipe_settings` and inspect `payload`.
2. Update dedup behavior with `set_recipe_settings` action `set_payload` (`keys`, `selectAllColumns`, `globalCount`, `preFilter`, `postFilter` are the primary control blocks).

## Required Reference Files

Read these references before editing distinct recipes:

- [Distinct recipe settings and payload](references/recipe_settings_and_payload.md) (always).
- [Filter payload reference](../sampling/references/filter_payload.md) (for `preFilter` and `postFilter`).
- [Visual conditions params](../references/visual_conditions_params.md) (shared rules-mode condition fields/operators used in filters).

Before submitting any `set_payload` or `set_params` call, re-read `references/recipe_settings_and_payload.md` and for each field in the params matrices, make an explicit decision about whether to include it.

## Recipe-Specific Guardrails

1. In observed distinct recipes, behavior is payload-driven and `params` is empty; avoid `set_params` unless explicitly requested.
2. `selectAllColumns=true` means deduplication is based on all input columns; `keys[]` is retained in payload but is not the primary dedup selector in that mode.
3. Use `globalCount=true` only when the output should include duplicate-group counts (`count` column).
4. Preserve `engineParams` unless the user explicitly asks to alter execution behavior.
5. Keep `outputColumnNameOverrides` unchanged unless intentionally renaming output columns.

## Type-Specific Update Notes

Use parent rules from `dataiku-skills/recipes/SKILL.md` section `Settings And Payload Update Rules`.

- For distinct, prefer `set_payload`; `set_params` is usually unnecessary.
- Use `merge=true, deep_merge=true` only for targeted nested patches (`preFilter` or `postFilter`).

## DSS Documentation

- Distinct recipe docs: https://doc.dataiku.com/dss/latest/other_recipes/distinct.html
