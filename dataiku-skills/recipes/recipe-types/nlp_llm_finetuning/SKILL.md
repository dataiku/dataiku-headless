---
name: dataiku-recipe-nlp_llm_finetuning
description: "Fine-tune an LLM from prompt/completion training data, with optional validation input and deployment settings."
---

# LLM Fine-Tuning Recipe Overview

Use this skill with `recipes` for work focused on recipe type `nlp_llm_finetuning`.

This recipe trains a fine-tuned model from prompt/completion data.

## I/O Requirements

**Inputs:** 1 training dataset (role `main`) containing `promptColumn` and `completionColumn`; optionally 1 validation dataset (role `validation`).

**Output:** 1 saved model (role `savedModel`).

Creating a fine-tuning recipe from scratch is not currently supported via MCP — use these tools to update an existing recipe.

## Steps to Create or Update an LLM Fine-Tuning Recipe

Use the parent `recipes` skill for shared lifecycle steps.

Then apply fine-tuning-specific updates:

1. Read current settings with `get_recipe_settings` and inspect both `params` and `payload`.
2. Update training behavior with `set_recipe_settings` action `set_payload`.

## Required Reference Files

Read these references before editing fine-tuning recipes:

- [Fine-tuning settings and payload](references/recipe_settings_and_payload.md) (always).

## Recipe-Specific Guardrails

1. Keep `promptColumn` and `completionColumn` aligned with the training dataset schema.
2. Keep `systemMessageMode` coherent with `systemMessageColumn` usage.
3. Preserve `hyperparameters.useDefaults` unless the user explicitly asks for manual tuning.
4. Preserve `llmId` unless the user explicitly asks to switch the base model.

## Type-Specific Update Notes

Use parent rules from `dataiku-skills/recipes/SKILL.md` section `Settings And Payload Update Rules`.

- Fine-tuning behavior is payload-driven; prefer `set_payload`.
- Use a full payload round-trip for `hyperparameters`; partial edits are easy to make inconsistent.

## DSS Documentation

- Fine-tuning docs: https://doc.dataiku.com/dss/latest/generative-ai/recipes/fine-tuning.html
