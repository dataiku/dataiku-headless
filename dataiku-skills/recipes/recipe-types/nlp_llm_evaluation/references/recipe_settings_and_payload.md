---
name: nlp-llm-evaluation-settings-and-payload-reference
description: "Observed params and payload structure for nlp_llm_evaluation recipes."
---

# nlp_llm_evaluation Settings And Payload Reference

Use this reference for `nlp_llm_evaluation` edits.

## Observed Settings Shape

In observed nlp_llm_evaluation recipes:

- `params` holds execution environment settings
- `payload` controls which columns to evaluate, which LLMs to use as judges, which metrics to compute, and sampling behavior

Observed top-level `params` keys:

- `envSelection`
- `containerSelection`

Omit optional column name keys when not needed.

Observed top-level `payload` keys:

- `inputFormat`
- `llmTaskType`
- `inputColumnName`
- `outputColumnName`
- `groundTruthColumnName`
- `contextColumnName`
- `completionLLMId`
- `embeddingLLMId`
- `metrics`
- `customMetrics`
- `customTraits`
- `labels`
- `failOnErrors`
- `bleuTokenizer`
- `bertScoreModelType`
- `embeddingSettings`
- `completionSettings`
- `selection`

## Params Notes

- `params.envSelection`: code environment. Preserve unless the user explicitly asks to change it.
- `params.containerSelection`: execution container. Preserve unless the user explicitly asks to change it.

## Payload Matrix

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `inputFormat` | yes | `enum` | One of `PROMPT_RECIPE`, `DATAIKU_ANSWERS`, `CUSTOM`. Describes the shape of the input dataset. |
| `llmTaskType` | yes | `enum` | Observed: `OTHER_LLM_TASK`, `SUMMARIZATION`, `QUESTION_ANSWERING`, `TRANSLATION`. Describes the task being evaluated. |
| `inputColumnName` | yes | `string` | Column containing the LLM input / query. |
| `outputColumnName` | yes | `string` | Column containing the LLM output / response to evaluate. |
| `groundTruthColumnName` | no | `string` | Column with the expected / reference output. Required for reference-based metrics (`answerCorrectness`, `bleu`, `rouge`). |
| `contextColumnName` | no | `string` | Column with RAG context used in the prompt. Only available for `QUESTION_ANSWERING` and `OTHER_LLM_TASK` — absent for `SUMMARIZATION` and `TRANSLATION`. Omit entirely when not applicable. |
| `completionLLMId` | no | `string` | LLM used as judge for semantic/correctness metrics. Preserve unless the user explicitly asks to change it. |
| `embeddingLLMId` | no | `string` | Embedding model used for similarity metrics. Preserve unless the user explicitly asks to change it. |
| `metrics` | yes | `list<string>` | Observed values: `answerCorrectness`, `answerRelevancy`, `answerSimilarity`, `bertScore`, `contextPrecision`, `contextRecall`, `faithfulness`, `multimodalFairness`, `multimodalRelevancy`, `bleu`, `rouge`. |
| `customMetrics` | no | `list<object>` | Custom metric definitions. Empty list is valid. |
| `customTraits` | no | `list<object>` | Custom trait definitions. Empty list is valid. |
| `labels` | no | `list<object>` | Label definitions. Empty list is valid. |
| `failOnErrors` | no | `boolean` | Whether to abort on row-level evaluation errors. |
| `bleuTokenizer` | no | `string` | Observed: `13a`. Tokenizer for BLEU scoring. |
| `bertScoreModelType` | no | `string` | Observed: `bert-base-uncased`. Model used for BERTScore. |
| `embeddingSettings` | no | `object` | Chunking settings for embedding-based metrics. Preserve unless explicitly changing. |
| `completionSettings` | no | `object` | LLM completion settings (e.g. stop sequences). Preserve unless explicitly changing. |
| `selection` | no | `object` | Input row sampling/filter settings. Preserve unless the user explicitly asks to change sampling behavior. |

## Metrics and Required Columns

Each metric requires specific columns to be configured. Selecting a metric without its required columns will cause the recipe to fail. "Context" column (`contextColumnName`) is only available for `QUESTION_ANSWERING` and `OTHER_LLM_TASK` task types.

| Metric (payload string) | UI label | Input | Output | Ground Truth | Context | Embedding + Completion LLM |
|---|---|:---:|:---:|:---:|:---:|:---:|
| `answerCorrectness` | Answer correctness | ✓ | ✓ | ✓ | | ✓ |
| `answerRelevancy` | Answer relevancy | ✓ | ✓ | | optional | ✓ |
| `answerSimilarity` | Answer similarity | ✓ | ✓ | ✓ | | ✓ |
| `bertScore` | BERT Score | | ✓ | ✓ | | |
| `contextPrecision` | Context precision | ✓ | | ✓ | optional | ✓ |
| `contextRecall` | Context recall | ✓ | | ✓ | optional | ✓ |
| `faithfulness` | Faithfulness | ✓ | ✓ | | optional | ✓ |
| `multimodalFairness` | Multimodal fairness | | | | | ✓ |
| `multimodalRelevancy` | Multimodal relevancy | | | | | ✓ |
| `bleu` | BLEU | | ✓ | ✓ | | |
| `rouge` | ROUGE | | ✓ | ✓ | | |

## Canonical Settings Example — `PROMPT_RECIPE` (Trimmed)

```json
{
  "params": {
    "envSelection": {
      "envMode": "EXPLICIT_ENV",
      "envName": "<env_name>"
    },
    "containerSelection": {
      "containerMode": "INHERIT"
    }
  },
  "payload": {
    "inputFormat": "PROMPT_RECIPE",
    "llmTaskType": "SUMMARIZATION",
    "inputColumnName": "llm_raw_query",
    "outputColumnName": "llm_raw_response",
    "groundTruthColumnName": "llm_output",
    "completionLLMId": "openai:<connection>:<model>",
    "embeddingLLMId": "openai:<connection>:text-embedding-3-small",
    "metrics": [
      "answerSimilarity",
      "bertScore",
      "rouge",
      "answerCorrectness",
      "bleu"
    ],
    "customMetrics": [],
    "customTraits": [],
    "labels": [],
    "failOnErrors": true,
    "bleuTokenizer": "13a",
    "bertScoreModelType": "bert-base-uncased",
    "embeddingSettings": {
      "chunkOverlapCharacters": 0,
      "chunkSizeCharacters": 0,
      "documentSplittingMode": "CHARACTERS_BASED"
    },
    "completionSettings": {
      "stopSequences": []
    },
    "selection": {
      "samplingMethod": "FULL",
      "maxRecords": 10000,
      "filter": {
        "enabled": false,
        "distinct": false
      }
    }
  }
}
```

## Canonical Settings Example — `DATAIKU_ANSWERS` (Trimmed)

Use when the input dataset comes from Dataiku Answers. Column names are fixed: `question` (input), `answer` (output), `sources` (optional context).

```json
{
  "params": {
    "envSelection": {
      "envMode": "INHERIT"
    },
    "containerSelection": {
      "containerMode": "INHERIT"
    }
  },
  "payload": {
    "inputFormat": "DATAIKU_ANSWERS",
    "llmTaskType": "OTHER_LLM_TASK",
    "inputColumnName": "question",
    "outputColumnName": "answer",
    "groundTruthColumnName": "<reference_answer_column>",
    "contextColumnName": "sources",
    "completionLLMId": "openai:<connection>:<model>",
    "embeddingLLMId": "openai:<connection>:text-embedding-3-small",
    "metrics": [
      "answerSimilarity",
      "answerCorrectness",
      "bertScore"
    ],
    "customMetrics": [],
    "customTraits": [],
    "labels": [],
    "failOnErrors": true,
    "bleuTokenizer": "13a",
    "bertScoreModelType": "bert-base-uncased",
    "embeddingSettings": {
      "chunkOverlapCharacters": 0,
      "chunkSizeCharacters": 0,
      "documentSplittingMode": "CHARACTERS_BASED"
    },
    "completionSettings": {
      "stopSequences": []
    },
    "selection": {
      "samplingMethod": "FULL",
      "maxRecords": 10000,
      "filter": {
        "enabled": false,
        "distinct": false
      }
    }
  }
}
```

## Canonical Settings Example — `CUSTOM` (Trimmed)

Structurally identical to `DATAIKU_ANSWERS` — use when the input dataset comes from a non-Dataiku-Answers source with custom column naming.

```json
{
  "params": {
    "envSelection": {
      "envMode": "INHERIT"
    },
    "containerSelection": {
      "containerMode": "INHERIT"
    }
  },
  "payload": {
    "inputFormat": "CUSTOM",
    "llmTaskType": "QUESTION_ANSWERING",
    "inputColumnName": "<query_column>",
    "outputColumnName": "<response_column>",
    "groundTruthColumnName": "<reference_answer_column>",
    "contextColumnName": "<rag_context_column>",
    "completionLLMId": "openai:<connection>:<model>",
    "embeddingLLMId": "openai:<connection>:text-embedding-3-small",
    "metrics": [
      "answerCorrectness",
      "answerRelevancy",
      "bertScore",
      "bleu",
      "rouge"
    ],
    "customMetrics": [],
    "customTraits": [],
    "labels": [],
    "failOnErrors": true,
    "bleuTokenizer": "13a",
    "bertScoreModelType": "bert-base-uncased",
    "embeddingSettings": {
      "chunkOverlapCharacters": 0,
      "chunkSizeCharacters": 0,
      "documentSplittingMode": "CHARACTERS_BASED"
    },
    "completionSettings": {
      "stopSequences": []
    },
    "selection": {
      "samplingMethod": "FULL",
      "maxRecords": 10000,
      "filter": {
        "enabled": false,
        "distinct": false
      }
    }
  }
}
```
