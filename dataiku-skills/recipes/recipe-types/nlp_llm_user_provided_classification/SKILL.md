---
name: dataiku-recipe-nlp_llm_user_provided_classification
description: "Classify dataset text into user-defined classes with an LLM."
---

# User-Provided Classification Recipe Overview

Use this skill with `recipes` for work focused on recipe type `nlp_llm_user_provided_classification`.

This recipe classifies a text column into a user-defined set of classes.

**I/O:** exactly 1 dataset in (role `main`) → exactly 1 dataset out (role `main`).

## Steps to Create or Update a User-Provided Classification Recipe

Use the parent `recipes` skill for shared lifecycle steps.

Then apply classification-specific updates:

1. Read current settings with `get_recipe_settings` and inspect `payload`.
2. Update classes, input column, or model choice with `set_recipe_settings` action `set_payload`.

## Required Reference Files

Read these references before editing user-provided classification recipes:

- [User-provided classification settings and payload](references/recipe_settings_and_payload.md) (always).

## Recipe-Specific Guardrails

1. Keep `possibleClasses[]` names stable unless the user explicitly wants to change the business taxonomy.
2. Keep `inputColumn` aligned with the intended source text column.
3. Preserve `llmId` unless the user explicitly asks to switch models.

## Type-Specific Update Notes

Use parent rules from `dataiku-skills/recipes/SKILL.md` section `Settings And Payload Update Rules`.

- Classification recipes are payload-driven; prefer `set_payload`.
- Use a full payload round-trip when changing `possibleClasses[]`.

## DSS Documentation

- Classification recipe docs: https://doc.dataiku.com/dss/latest/generative-ai/recipes/classification.html
