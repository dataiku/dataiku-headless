---
name: prompt-recipe-settings-and-payload-reference
description: "Observed payload structure for prompt recipes, including template inputs, validation, filtering, completion settings, and context passing."
---

# Prompt Recipe Settings And Payload Reference

Use this reference for `prompt` payload edits.

## Observed Settings Shape

In observed prompt recipes:

- `params` mainly carries `containerSelection`.
- `payload` controls prompt behavior.

Observed top-level payload keys:

- `rawQueryOutputMode` — controls whether the `llm_raw_query` column is emitted. Values: `"RAW"` (full query incl. images), `"RAW_WITHOUT_FULL_IMAGES"` (query without image data), or omit to suppress the column. Required as input by `nlp_agent_evaluation` and `nlp_llm_evaluation` recipes.
- `completionSettings`
- `rawResponseOutputMode` — controls whether the `llm_raw_response` column is emitted. Values: `"RAW"` (full response incl. traces), `"RAW_WITHOUT_TRACES"` (response without trace data), or omit to suppress the column. Required as output by `nlp_agent_evaluation` and `nlp_llm_evaluation` recipes.
- `llmId` - LLM identifier - discover with `list_llms`
- `associatedPromptStudioId`
- `associatedPromptStudioPromptId`
- `prompt`
- `passContext`
- `context`
- `filter` — observed in payloads but not exposed in the UI; do not modify.
- `performFiltering` — observed in payloads but not exposed in the UI; do not modify.

## Prompt Modes

`promptMode` controls which template fields are active:

| `promptMode` | UI name | Active template fields | Placeholder syntax |
| --- | --- | --- | --- |
| `PROMPT_TEMPLATE_STRUCTURED` | Managed mode | `structuredPromptPrefix`, `promptTemplateInputs` | `[[inputName]]` |
| `PROMPT_TEMPLATE_TEXT` | Advanced mode | `textPromptTemplate`, `textPromptSystemTemplate`, `textPromptTemplateInputs` | `{{inputName}}` for text; `{{image:inputName}}` for images |

In Managed mode, Dataiku generates the final prompt from the structured prefix. In Advanced mode, the user authors the full prompt with explicit variable placeholders.

## `payload.prompt` Matrix

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `promptMode` | yes | `enum` | `PROMPT_TEMPLATE_STRUCTURED` (Managed) or `PROMPT_TEMPLATE_TEXT` (Advanced). |
| `promptTemplateQueriesSource` | yes | `enum` | Observed: `DATASET` |
| `structuredPromptPrefix` | conditional | `string` | Active when `promptMode` is `PROMPT_TEMPLATE_STRUCTURED`. Prompt template text using `[[inputName]]` placeholders. |
| `promptTemplateInputs` | conditional | `list<object>` | Active when `promptMode` is `PROMPT_TEMPLATE_STRUCTURED`. Maps dataset columns to `[[inputName]]` placeholders. |
| `textPromptTemplate` | conditional | `string` | Active when `promptMode` is `PROMPT_TEMPLATE_TEXT`. User message text with `{{inputName}}` / `{{image:inputName}}` placeholders. |
| `textPromptSystemTemplate` | no | `string` | System message text. Observed in `PROMPT_TEMPLATE_TEXT` recipes. |
| `textPromptTemplateInputs` | conditional | `list<object>` | Active when `promptMode` is `PROMPT_TEMPLATE_TEXT`. Maps dataset columns to `{{inputName}}` placeholders. |
| `resultValidation` | yes | `object` | Structured-output validation rules. |
| `structuredPromptExamples` | no | `list<object>` | Empty in observed recipes. |
| `chatMessages` | no | `object` | Empty in observed recipes. |
| `guardrailsPipelineSettings` | no | `object` | Guardrails config, observed with empty guardrails list. |
| `streamingDisabled` | no | `boolean` | Preserve unless explicitly changing streaming behavior. |

## `payload.prompt.promptTemplateInputs[]`

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `datasetColumnName` | yes | `string<column_name>` | Source dataset column. |
| `name` | yes | `string` | Placeholder name used in the template. |
| `type` | no | `enum` | Observed as optional in live recipes; when present, observed: `TEXT`. |

## `payload.prompt.textPromptTemplateInputs[]`

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `name` | yes | `string` | Variable name matching a `{{inputName}}` or `{{image:inputName}}` placeholder in `textPromptTemplate` or `textPromptSystemTemplate`. |
| `datasetColumnName` | no | `string<column_name>` | May be absent in live recipes; preserve the observed shape unless intentionally normalizing. |

## `payload.prompt.resultValidation`

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `expectedFormat` | yes | `enum` | `NONE`, `JSON_ARRAY`, `JSON_OBJECT` |
| `requiredJSONObjectKeys` | no | `list<string>` | Populated when `expectedFormat` is `JSON_OBJECT`; empty otherwise. |
| `forbiddenTerms` | no | `list<string>` | Empty in observed recipes. |

## `payload.completionSettings`

All keys are optional. Include only keys that are intentionally changed.

| Param | Domain | Notes |
| --- | --- | --- |
| `stopSequences` | `list<string>` | Stop sequences; empty list is the default. |
| `reasoningEffort` | `enum` | Controls reasoning depth: low values for faster, simpler answers; high values for deeper, complex analysis. Support varies by model. Observed values: `MODEL_DEFAULT`, `STANDARD`, `OFF`. Omit the key entirely for "Inherit connection default". |
| `temperature` | `number` | Sampling temperature. |
| `topP` | `number` | Nucleus sampling probability. |
| `maxOutputTokens` | `integer` | Maximum tokens in the response. |
| `presencePenalty` | `number` | Penalizes new tokens based on whether they appear in the text so far. Valid range varies by model. |
| `frequencyPenalty` | `number` | Penalizes new tokens based on their frequency in the text so far. Valid range varies by model. |
| `responseFormat` | `object` | Structured-output schema config. Observed fields: `type` (`"json"`), `schema` (example object), `compatible` (`boolean`), `strict` (`boolean`). |

## Context Passing Notes

When `passContext` is `true`, the `context` object is sent to the LLM alongside the prompt. Observed `context` shape:

```json
{
  "mode": "KEY_VALUE",
  "jsonField": {"fromColumn": false, "value": "{}"},
  "fields": []
}
```

Preserve `passContext` and `context` unless the user explicitly asks to change context behavior.

## Canonical Payload Examples (Trimmed)

### Managed mode (`PROMPT_TEMPLATE_STRUCTURED`)

```json
{
  "llmId": "<llm_id>",
  "rawQueryOutputMode": "RAW_WITHOUT_FULL_IMAGES",
  "rawResponseOutputMode": "RAW_WITHOUT_TRACES",
  "completionSettings": {"stopSequences": []},
  "associatedPromptStudioId": "<prompt_studio_id>",
  "associatedPromptStudioPromptId": "<prompt_studio_prompt_id>",
  "prompt": {
    "promptMode": "PROMPT_TEMPLATE_STRUCTURED",
    "promptTemplateQueriesSource": "DATASET",
    "structuredPromptPrefix": "answer the [[question]]",
    "promptTemplateInputs": [
      {"datasetColumnName": "question", "name": "question"}
    ],
    "resultValidation": {
      "expectedFormat": "NONE",
      "requiredJSONObjectKeys": [],
      "forbiddenTerms": []
    }
  }
}
```

### Advanced mode (`PROMPT_TEMPLATE_TEXT`)

```json
{
  "llmId": "<llm_id>",
  "rawQueryOutputMode": "RAW_WITHOUT_FULL_IMAGES",
  "rawResponseOutputMode": "RAW_WITHOUT_TRACES",
  "passContext": false,
  "context": {
    "mode": "KEY_VALUE",
    "jsonField": {"fromColumn": false, "value": "{}"},
    "fields": []
  },
  "completionSettings": {
    "stopSequences": [],
    "responseFormat": {
      "type": "json",
      "schema": {"key_1": "string", "key_2": 0},
      "compatible": true,
      "strict": false
    }
  },
  "prompt": {
    "promptMode": "PROMPT_TEMPLATE_TEXT",
    "promptTemplateQueriesSource": "DATASET",
    "textPromptSystemTemplate": "You are a helpful assistant.",
    "textPromptTemplate": "Summarize the order for {{customer_name}}.",
    "textPromptTemplateInputs": [
      {"name": "customer_name", "datasetColumnName": "customer_name"}
    ],
    "resultValidation": {
      "expectedFormat": "JSON_OBJECT",
      "requiredJSONObjectKeys": ["summary"],
      "forbiddenTerms": []
    }
  }
}
```
