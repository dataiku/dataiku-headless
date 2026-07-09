---
name: dataiku-recipe-extract_content
description: "Extract text and optional image/screenshot content from managed-folder documents into a dataset."
---

# Extract Content Recipe Overview

Use this skill with `recipes` for work focused on recipe type `extract_content`.

This recipe reads documents from a managed folder and outputs extracted text/content rows into a dataset.

## Steps to Create or Update an Extract Content Recipe

Use the parent `recipes` skill for shared lifecycle steps.

Then apply extract-content-specific updates:

1. Read current settings with `get_recipe_settings` and inspect both `params` and `payload`.
2. Update extraction behavior with `set_recipe_settings` actions `set_params` and/or `set_payload`.

## Required Reference Files

Read these references before editing extract-content recipes:

- [Extract content settings and payload](references/recipe_settings_and_payload.md) (always).

## I/O Requirements

**Input:** exactly 1 managed folder (role `main`). When calling `create_recipe`, reference the folder by its **ID** (e.g., `SKxXpma3`), not its display name.

**Output:** exactly 1 dataset (role `main`) — extracted text/content rows.

## Recipe-Specific Guardrails

1. Treat the primary input as a managed-folder ref, not a dataset.
2. Preserve `params.extractionMode`, VLM settings, and `allOtherRule` unless the user explicitly asks to change extraction behavior.
3. Preserve `payload.storeImages` and `payload.storeScreenshots` unless the user explicitly asks for multimodal outputs.

## Type-Specific Update Notes

Use parent rules from `dataiku-skills/recipes/SKILL.md` section `Settings And Payload Update Rules`.

- Use `set_params` for extraction behavior and `set_payload` for output storage behavior.
- Prefer full round-trips for `params.allOtherRule` edits.

## DSS Documentation

- Extract-content docs: https://doc.dataiku.com/dss/latest/generative-ai/knowledge/documents.html
