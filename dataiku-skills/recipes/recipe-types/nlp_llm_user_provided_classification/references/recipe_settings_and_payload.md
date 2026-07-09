---
name: user-provided-classification-settings-and-payload-reference
description: "Observed payload structure for user-provided LLM classification recipes."
---

# User-Provided Classification Settings And Payload Reference

Use this reference for `nlp_llm_user_provided_classification` payload edits.

## Observed Settings Shape

In observed user-provided classification recipes:

- `params` mainly carries `containerSelection`
- `payload` controls the class list, few-shot examples, model, and input column

Observed top-level payload keys:

- `possibleClasses`
- `examples`
- `hypothesisTemplate`
- `explainOutput`
- `completionSettings`
- `llmId`
- `inputColumn`

## Payload Matrix

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `possibleClasses` | yes | `list<object>` | Each object has a `name` field. |
| `inputColumn` | yes | `string<column_name>` | Source text column. |
| `llmId` | yes | `string<llm_id>` | Preserve unless intentionally switching models. |
| `examples` | no | `list<object>` | Few-shot examples; each has `input`, `outputClass`, `explanation`. |
| `hypothesisTemplate` | no | `string` | Template string with `{class}` placeholder, e.g. `"This example is {class}."` |
| `explainOutput` | no | `boolean` | Whether to include an explanation column in output. Observed: `false` |
| `completionSettings` | no | `object` | Observed with `stopSequences: []`. |

## `possibleClasses[]`

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `name` | yes | `string` | User-defined class label. |

## `examples[]`

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `input` | yes | `string` | Example input text. |
| `outputClass` | yes | `string` | Expected class for this example. Must match a value in `possibleClasses[].name`. |
| `explanation` | no | `string` | Optional explanation; observed as `""`. |

## Canonical Payload Example

```json
{
  "possibleClasses": [
    {"name": "car"},
    {"name": "home"},
    {"name": "education"},
    {"name": "other"}
  ],
  "examples": [
    {"input": "car example", "outputClass": "car", "explanation": ""},
    {"input": "home example", "outputClass": "home", "explanation": ""}
  ],
  "hypothesisTemplate": "This example is {class}.",
  "explainOutput": false,
  "completionSettings": {"stopSequences": []},
  "llmId": "openai:<connection>:<model>",
  "inputColumn": "LOAN_PURPOSE"
}
```
