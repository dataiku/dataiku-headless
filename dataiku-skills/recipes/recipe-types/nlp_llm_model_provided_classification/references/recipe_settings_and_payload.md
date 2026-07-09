---
name: model-provided-classification-settings-and-payload-reference
description: "Observed payload structure for model-provided LLM classification recipes."
---

# Model-Provided Classification Settings And Payload Reference

Use this reference for `nlp_llm_model_provided_classification` payload edits.

## Observed Settings Shape

In observed classification recipes:

- `params` mainly carries `containerSelection`.
- `payload` controls the task, model, and input column.

Observed top-level payload keys:

- `task`
- `outputMode`
- `llmId`
- `inputColumn`

## Payload Matrix

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `task` | yes | `enum` | Observed: `SENTIMENT_ANALYSIS`, `EMOTION_ANALYSIS` |
| `inputColumn` | yes | `string<column_name>` | Source text column. |
| `llmId` | yes | `string<llm_id>` | Preserve unless intentionally switching models. |
| `outputMode` | no | `enum` | Observed: `FIRST` |

## Canonical Payload Example

```json
{
  "task": "SENTIMENT_ANALYSIS",
  "outputMode": "FIRST",
  "llmId": "openai:<connection>:<model>",
  "inputColumn": "order_notes"
}
```
