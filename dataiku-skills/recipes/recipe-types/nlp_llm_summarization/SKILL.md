---
name: dataiku-recipe-nlp_llm_summarization
description: "Summarize dataset text columns with LLM-backed summarization controls for length, overlap, and output language."
---

# LLM Summarization Recipe Overview

Use this skill with `recipes` for work focused on recipe type `nlp_llm_summarization`.

The summarization recipe summarizes one text column into shorter outputs, with chunking and target-length controls.

**I/O:** exactly 1 dataset in (role `main`) → exactly 1 dataset out (role `main`).

## Steps to Create or Update a Summarization Recipe

Use the parent `recipes` skill for shared lifecycle steps.

Then apply summarization-specific updates:

1. Read current settings with `get_recipe_settings` and inspect `payload`.
2. Update the summarization controls with `set_recipe_settings` action `set_payload`.

## Required Reference Files

Read these references before editing summarization recipes:

- [Summarization recipe settings and payload](references/recipe_settings_and_payload.md) (always).

## Recipe-Specific Guardrails

1. Keep `inputColumn` aligned with the actual source text column.
2. Preserve `llmId` unless the user explicitly asks to switch models.
3. Keep `targetLength`, `targetLengthUnit`, and `controlTargetLength` coherent.
4. Preserve chunking parameters (`maxNumSplitLevels`, `numOverlapTokens`, `specialTokensSafetyFactor`) unless the user explicitly wants different long-text handling.

## Type Notes

- Keep payload/params aligned to DSS expectations for `nlp_llm_summarization`.
- Preserve existing instance-specific values unless explicitly asked to change them.


## Type-Specific Update Notes

Use parent rules from `dataiku-skills/recipes/SKILL.md` section `Settings And Payload Update Rules`.

- Summarization recipes are payload-driven; prefer `set_payload`.
- Use `merge=true, deep_merge=true` only for targeted nested patches such as `completionSettings`.

## DSS Documentation

- Summarization recipe docs: https://doc.dataiku.com/dss/latest/generative-ai/recipes/summarization.html
