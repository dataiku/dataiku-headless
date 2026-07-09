---
name: fine-tuning-settings-and-payload-reference
description: "Observed payload structure for LLM fine-tuning recipes."
---

# LLM Fine-Tuning Settings And Payload Reference

Use this reference for `nlp_llm_finetuning` payload edits.

## Observed Settings Shape

In observed fine-tuning recipes:

- `params` mainly carries `containerSelection`
- `payload` controls columns, system-message mode, hyperparameters, base model, and deployment behavior

Observed top-level payload keys:

- `deployFinetunedModel`
- `systemMessageColumn`
- `completionColumn`
- `completionSettings`
- `hyperparameters`
- `systemMessageMode`
- `containerSelection`
- `llmId`
- `cleanInactiveSMVDeployments`
- `promptColumn`

## Payload Matrix

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `promptColumn` | yes | `string<column_name>` | Prompt/training input column. |
| `completionColumn` | yes | `string<column_name>` | Completion/target column. |
| `llmId` | yes | `string<llm_id>` | Base model to fine-tune. |
| `systemMessageMode` | no | `enum` | Observed: `DYNAMIC`, `NONE` |
| `systemMessageColumn` | conditional | `string<column_name>` | Needed when `systemMessageMode` is dynamic. |
| `deployFinetunedModel` | no | `boolean` | Preserve unless explicitly changing deployment behavior. |
| `cleanInactiveSMVDeployments` | no | `boolean` | Preserve unless explicitly changing cleanup behavior. |
| `hyperparameters` | no | `object` | Nested local/remote hyperparameter controls. |
| `completionSettings` | no | `object` | Observed with `stopSequences`. |

## Canonical Payload Example (Trimmed)

```json
{
  "promptColumn": "prompt",
  "completionColumn": "completion",
  "llmId": "openai:<connection>:<model>",
  "systemMessageMode": "DYNAMIC",
  "systemMessageColumn": "system_message",
  "deployFinetunedModel": false,
  "cleanInactiveSMVDeployments": false,
  "completionSettings": {
    "stopSequences": []
  },
  "hyperparameters": {
    "useDefaults": true,
    "nbEpochs": 3
  }
}
```
