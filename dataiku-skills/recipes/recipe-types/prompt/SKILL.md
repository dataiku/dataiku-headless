---
name: dataiku-recipe-prompt
description: "Configure prompt recipes over dataset rows, including structured prompt inputs, validation, completion settings, and context passing."
---

# Prompt Recipe Overview

Use this skill with `recipes` for work focused on recipe type `prompt`.

The prompt recipe sends row values from a dataset through a prompt template backed by an LLM or agent.

**I/O:** exactly 1 dataset in (role `main`) → exactly 1 dataset out (role `main`).

**LLM or Agent:** The `llmId` field selects what processes the prompt. It can be:
- A standard LLM connection ID (discover with `list_llms`) — completion or chat models.
- An agent reference `agent:<agent_id>` (discover with `list_agents`) — runs a DSS agent. For evaluation, set `rawQueryOutputMode` (`RAW` / `RAW_WITHOUT_FULL_IMAGES`) and `rawResponseOutputMode` (`RAW` / `RAW_WITHOUT_TRACES`) to emit the `llm_raw_query` / `llm_raw_response` columns consumed by `nlp_agent_evaluation` and `nlp_llm_evaluation`.

## Output Columns

The prompt recipe always emits these columns; the name is fixed and cannot be changed in the recipe config:

| Column | Always emitted | Description |
| --- | --- | --- |
| `llm_output` | yes | The LLM's text response for each row. |
| `llm_validation_status` | yes | Validation outcome (`VALID`, `INVALID`) only if `resultValidation` settings set. If no validation constraint, all values empty. |
| `llm_error_message` | yes | Error detail when the LLM call fails for a row; empty on success. |
| `llm_raw_query` | only if `rawQueryOutputMode` is set | Full prompt sent to the LLM, including images if `RAW`; without images if `RAW_WITHOUT_FULL_IMAGES`. Required by evaluation recipes. |
| `llm_raw_response` | only if `rawResponseOutputMode` is set | Full LLM response including traces if `RAW`; without traces if `RAW_WITHOUT_TRACES`. Required by evaluation recipes. |

Two prompt modes are supported (see reference for field details):
- **Managed mode** (`PROMPT_TEMPLATE_STRUCTURED`): Dataiku generates the final prompt from a structured prefix with `[[inputName]]` placeholders.
- **Advanced mode** (`PROMPT_TEMPLATE_TEXT`): user authors the full user message and optional system message with `{{inputName}}` / `{{image:inputName}}` placeholders.

## Steps to Create or Update a Prompt Recipe

Use the parent `recipes` skill for shared lifecycle steps.

Then apply prompt-specific updates:

1. Read current settings with `get_recipe_settings` and inspect both `payload` and `params`.
2. Update the prompt behavior with `set_recipe_settings` action `set_payload`.

## Required Reference Files

Read these references before editing prompt recipes:

- [Prompt recipe settings and payload](references/recipe_settings_and_payload.md) (always).

## Recipe-Specific Guardrails

1. Keep input lists aligned with placeholders in the active template: `promptTemplateInputs[]` with `[[inputName]]` placeholders in `structuredPromptPrefix` (Managed mode); `textPromptTemplateInputs[]` with `{{inputName}}` / `{{image:inputName}}` placeholders in `textPromptTemplate` or `textPromptSystemTemplate` (Advanced mode).
2. Preserve `llmId` unless the user explicitly asks to switch models or agents.
3. Keep `resultValidation.expectedFormat` aligned with any structured-output prompt contract.
4. Preserve Prompt Studio linkage fields such as `associatedPromptStudioId` and `associatedPromptStudioPromptId`.
5. Preserve `rawQueryOutputMode` and `rawResponseOutputMode` unless the user explicitly asks for trace/raw-output changes.
6. Preserve `passContext` and `context` unless the user explicitly asks to change context-passing behavior.
7. When creating a prompt recipe, create the recipe first, then configure its prompt payload with `set_recipe_settings` action `set_payload`.

## Type Notes

- Keep payload/params aligned to DSS expectations for `prompt`.
- Preserve existing instance-specific values unless explicitly asked to change them.

## Type-Specific Update Notes

Use parent rules from `dataiku-skills/recipes/SKILL.md` section `Settings And Payload Update Rules`.

- Prompt recipes are payload-driven; prefer `set_payload`.
- Use `merge=true, deep_merge=true` only for targeted nested patches such as `prompt.resultValidation` or `completionSettings`.

## DSS Documentation

- Prompt recipe docs: https://doc.dataiku.com/dss/latest/generative-ai/recipes/prompt.html
