---
name: dataiku-recipe-nlp_llm_model_provided_classification
description: "Classify dataset text into built-in LLM classification tasks such as sentiment or emotion analysis."
---

# Model-Provided Classification Recipe Overview

Use this skill with `recipes` for work focused on recipe type `nlp_llm_model_provided_classification`.

This recipe applies a built-in classification task provided by the model workflow, such as sentiment or emotion analysis.

**I/O:** exactly 1 dataset in (role `main`) → exactly 1 dataset out (role `main`).

## Steps to Create or Update a Model-Provided Classification Recipe

Use the parent `recipes` skill for shared lifecycle steps.

Then apply classification-specific updates:

1. Read current settings with `get_recipe_settings` and inspect `payload`.
2. Update task selection, model choice, or input column with `set_recipe_settings` action `set_payload`.

## Required Reference Files

Read these references before editing model-provided classification recipes:

- [Model-provided classification settings and payload](references/recipe_settings_and_payload.md) (always).

## Recipe-Specific Guardrails

1. Keep `task` to a DSS-supported built-in classification task.
2. Keep `inputColumn` aligned with the intended source text column.
3. Preserve `llmId` unless the user explicitly asks to switch models.
4. Preserve `outputMode` unless the user explicitly wants alternate output behavior.

## Type Notes

- Keep payload/params aligned to DSS expectations for `nlp_llm_model_provided_classification`.
- Preserve existing instance-specific values unless explicitly asked to change them.


## Type-Specific Update Notes

Use parent rules from `dataiku-skills/recipes/SKILL.md` section `Settings And Payload Update Rules`.

- Classification recipes are payload-driven; prefer `set_payload`.

## DSS Documentation

- Classification recipe docs: https://doc.dataiku.com/dss/latest/generative-ai/recipes/classification.html
