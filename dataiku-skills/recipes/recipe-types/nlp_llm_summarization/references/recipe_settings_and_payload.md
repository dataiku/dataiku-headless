---
name: summarization-recipe-settings-and-payload-reference
description: "Observed payload structure for LLM summarization recipes."
---

# Summarization Recipe Settings And Payload Reference

Use this reference for `nlp_llm_summarization` payload edits.

## Observed Settings Shape

In observed summarization recipes:

- `params` mainly carries `containerSelection`.
- `payload` controls summarization behavior.

Observed top-level payload keys:

- `outputLanguage`
- `maxNumSplitLevels`
- `specialTokensSafetyFactor`
- `targetLength`
- `controlTargetLength`
- `completionSettings`
- `targetLengthUnit`
- `huggingFaceMaxTokens`
- `huggingFaceMinTokens`
- `llmId`
- `inputColumn`
- `numOverlapTokens`

## Payload Matrix

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `inputColumn` | yes | `string<column_name>` | Source text column. |
| `llmId` | yes | `string<llm_id>` | Preserve unless intentionally switching models. |
| `outputLanguage` | no | `string` | e.g. `"english"`. |
| `controlTargetLength` | no | `boolean` | Whether DSS should try to control output length. |
| `targetLength` | no | `integer` | DSS preserves this value in the payload regardless; only takes effect when `controlTargetLength=true`. |
| `targetLengthUnit` | no | `enum` | Same — preserved always, effective only when `controlTargetLength=true`. Observed: `SENTENCE`. |
| `maxNumSplitLevels` | no | `integer` | Long-text splitting depth. |
| `numOverlapTokens` | no | `integer` | Overlap for chunked summarization. |
| `specialTokensSafetyFactor` | no | `integer` | Preserve unless intentionally tuning token safety. |
| `huggingFaceMaxTokens` | no | `integer` | Preserve unless intentionally tuning Hugging Face behavior. |
| `huggingFaceMinTokens` | no | `integer` | Preserve unless intentionally tuning Hugging Face behavior. |
| `completionSettings` | no | `object` | Observed with `stopSequences`. |

## Canonical Payload Example

```json
{
  "inputColumn": "LOAN_PURPOSE",
  "llmId": "openai:<connection>:<model>",
  "controlTargetLength": false,
  "targetLength": 3,
  "targetLengthUnit": "SENTENCE",
  "maxNumSplitLevels": 3,
  "numOverlapTokens": 5,
  "specialTokensSafetyFactor": 4,
  "huggingFaceMaxTokens": 300,
  "huggingFaceMinTokens": 50,
  "completionSettings": {
    "stopSequences": []
  }
}
```
