---
name: agent-evaluation-settings-and-payload-reference
description: "Observed params and payload structure for agent-evaluation recipes."
---

# Agent Evaluation Settings And Payload Reference

Use this reference for `nlp_agent_evaluation` edits.

## Observed Settings Shape

In observed agent-evaluation recipes:

- `params` carries `envSelection` and `containerSelection`
- `payload` controls evaluation columns, metric selection, and model ids

Omit optional column name keys when not needed.

Observed top-level payload keys:

- `inputFormat` — one of `"PROMPT_RECIPE"`, `"AGENT_INTERACTION_LOGS"`, `"CUSTOM"`
- `inputColumnName`
- `outputColumnName`
- `groundTruthColumnName`
- `conversationIdColumnName`
- `conversationSortingKeyColumnName`
- `hasConversations`
- `evaluatedAgentId`
- `evaluatedAgentVersion`
- `actualToolCallsColumnName`
- `referenceToolCallsColumnName`
- `selection`
- `embeddingLLMId`
- `embeddingSettings`
- `completionLLMId`
- `completionSettings`
- `failOnErrors`
- `bertScoreModelType`
- `metrics`
- `customMetrics`
- `customTraits`
- `customConversationTraits`
- `customConversationMetrics`
- `labels`

## Metrics and Required Columns

Each metric in the `metrics` array requires specific input columns to be configured. Selecting a metric without its required columns will cause the recipe to fail.

| Metric (payload string) | UI label | Input | Output | Ground Truth | Actual tool calls | Reference tool calls | Embedding + Completion LLM |
|---|---|:---:|:---:|:---:|:---:|:---:|:---:|
| `toolCallExactMatch` | Tool Call Exact match | | | | ✓ | ✓ | |
| `toolCallPartialMatch` | Tool Call Partial match | | | | ✓ | ✓ | |
| `toolCallPrecisionRecallF1` | Precision / Recall / F1 | | | | ✓ | ✓ | |
| `agentGoalAccuracyWithReference` | Agent Goal Accuracy with Reference | ✓ | ✓ | ✓ | ✓ | | ✓ |
| `agentGoalAccuracyWithoutReference` | Agent Goal Accuracy without Reference | ✓ | ✓ | | ✓ | | ✓ |
| `answerCorrectness` | Answer correctness | ✓ | ✓ | ✓ | | | ✓ |
| `answerSimilarity` | Answer similarity | ✓ | ✓ | ✓ | | | ✓ |
| `bertScore` | BERT Score | | ✓ | ✓ | | | |

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
    "inputColumnName": "llm_raw_query",
    "outputColumnName": "llm_raw_response",
    "groundTruthColumnName": "labeled_answer",
    "actualToolCallsColumnName": "llm_raw_response",
    "referenceToolCallsColumnName": "<column_with_array_of_tool_name_strings>",
    "completionLLMId": "openai:<connection>:<model>",
    "embeddingLLMId": "openai:<connection>:<model>",
    "metrics": [
      "agentGoalAccuracyWithReference",
      "answerCorrectness",
      "answerSimilarity",
      "bertScore"
    ]
  }
}
```

## Canonical Settings Example — `CUSTOM` (Trimmed)

Use when the input dataset has arbitrary column names rather than the fixed names emitted by a prompt recipe.

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
    "inputFormat": "CUSTOM",
    "inputColumnName": "<query_column>",
    "outputColumnName": "<response_column>",
    "groundTruthColumnName": "<reference_answer_column>",
    "conversationIdColumnName": "<conversation_id_column>",
    "conversationSortingKeyColumnName": "<sort_column>",
    "hasConversations": false,
    "evaluatedAgentId": "<project_key>.<agent_id>",
    "evaluatedAgentVersion": "v1",
    "actualToolCallsColumnName": "<column_with_array_of_tool_name_strings>",
    "referenceToolCallsColumnName": "<column_with_array_of_tool_name_strings>",
    "completionLLMId": "openai:<connection>:<model>",
    "embeddingLLMId": "openai:<connection>:<model>",
    "metrics": [
      "answerCorrectness",
      "answerSimilarity",
      "bertScore"
    ]
  }
}
```

## Canonical Settings Example — `AGENT_INTERACTION_LOGS` (Trimmed)

Use when the input dataset comes from agent interaction logging. Column names are fixed (not configurable) — the dataset must contain `dku_llm_mesh_raw_query`, `dku_llm_mesh_raw_response`, `conversation_id`, `begin_time`, and `end_time`. If any are missing, the recipe will warn and refuse to run.

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
    "inputFormat": "AGENT_INTERACTION_LOGS",
    "inputColumnName": "dku_llm_mesh_raw_query",
    "outputColumnName": "dku_llm_mesh_raw_response",
    "conversationIdColumnName": "conversation_id",
    "conversationSortingKeyColumnName": "begin_time",
    "hasConversations": false,
    "groundTruthColumnName": "<reference_answer_column>",
    "referenceToolCallsColumnName": "<column_with_array_of_tool_name_strings>",
    "completionLLMId": "openai:<connection>:<model>",
    "embeddingLLMId": "openai:<connection>:<model>",
    "metrics": [
      "toolCallExactMatch",
      "toolCallPartialMatch",
      "toolCallPrecisionRecallF1",
      "answerCorrectness",
      "answerSimilarity"
    ]
  }
}
```
