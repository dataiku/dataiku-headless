---
name: dataiku-recipe-nlp_agent_evaluation
description: "Evaluate agent outputs, including answer quality, tool calls, metrics datasets, and evaluation-store outputs."
---

# Agent Evaluation Recipe Overview

Use this skill with `recipes` for work focused on recipe type `nlp_agent_evaluation`.

This recipe evaluates agent outputs row by row.

## I/O Requirements

**Input:** exactly 1 dataset (role `main`).

**Outputs:** at least one of the following is required; all are individually optional:
- 0 or 1 evaluation store (role `evaluationStore`) — preferred for tracking, comparisons, and drift analysis. `appendMode` does not apply.
- 0 or 1 dataset (role `main`) — per-row scored output.
- 0 or 1 metrics dataset (role `metrics`) — aggregate metrics; defaults to `appendMode: true`.

## Steps to Create an Agent Evaluation Recipe

Decide which outputs you need before creating the recipe:
- **Evaluation store** (preferred) — create one first with `create_evaluation_store(project_key, name, flavor="AGENT")`; `mesFlavor` is immutable after creation and must match the recipe type.
- **Per-row dataset** (role `main`) — useful for row-level score inspection downstream.
- **Metrics dataset** (role `metrics`) — useful for lightweight metric logging without a full evaluation store.

1. **Pre-create all desired outputs** before calling `create_recipe` — the SDK requires them to exist:
   - Evaluation store: `create_evaluation_store(project_key, name, flavor="AGENT")`
   - Per-row dataset and/or metrics dataset: `create_managed_dataset`
2. **Create the recipe** with `create_recipe`. Example with all three outputs:
   ```json
   [
     {"name": "<store_id>", "role": "evaluationStore"},
     {"name": "<output_dataset>", "role": "main", "appendMode": false},
     {"name": "<metrics_dataset>", "role": "metrics", "appendMode": true}
   ]
   ```
3. **Configure** using `set_recipe_settings` with `set_payload` (preferred for evaluation behavior; use `set_params` only for env/container changes).

## Steps to Update an Agent Evaluation Recipe

1. Read current settings with `get_recipe_settings` and inspect both `params` and `payload`.
2. Update evaluation behavior with `set_recipe_settings` actions `set_params` and/or `set_payload`.

## Preferred Tools

- Discover: `list_evaluation_stores(flavor="AGENT")`
- Create store: `create_evaluation_store(flavor="AGENT")`
- Inspect store run results: `get_evaluation_store_details`
- Delete store: `delete_evaluation_store`

## Required Reference Files

Read these references before editing agent-evaluation recipes:

- [Agent evaluation settings and payload](references/recipe_settings_and_payload.md) (always).

## Code Environment Requirement

`nlp_agent_evaluation` requires `langchain` and `langchain_core` to be installed in the recipe's code env. If the recipe fails immediately with `ModuleNotFoundError: No module named 'langchain'`, the code env is missing these packages. Ask the user for the name of a code env with the required packages.

## Input Format Options

`inputFormat` controls which columns the recipe reads. There are three options:

### `PROMPT_RECIPE`
Input dataset was produced by a prompt recipe. The recipe expects fixed column names:
- `llm_raw_query` — the prompt sent to the agent; emitted when `rawQueryOutputMode` is `"RAW"` or `"RAW_WITHOUT_FULL_IMAGES"` in the prompt recipe.
- `llm_raw_response` — the agent's response; emitted when `rawResponseOutputMode` is `"RAW"` or `"RAW_WITHOUT_TRACES"` in the prompt recipe.

If either column is missing, fix the upstream prompt recipe's `rawQueryOutputMode` / `rawResponseOutputMode` and rebuild it before running the eval recipe.

### `AGENT_INTERACTION_LOGS`
Input dataset comes from agent interaction logging (LLM Mesh). Column names are **fixed** — the dataset must already contain all of the following or the recipe will warn and refuse to run:
- `dku_llm_mesh_raw_query` — the input sent to the agent.
- `dku_llm_mesh_raw_response` — the agent's response (also used as `actualToolCallsColumnName`).
- `conversation_id` — identifies conversation groupings.
- `begin_time` — turn start timestamp, used for sorting within a conversation.
- `end_time` — turn end timestamp.

Only two fields remain configurable in the UI:
- `groundTruthColumnName` — column with the reference / ground-truth answer.
- `referenceToolCallsColumnName` — column with expected tool calls (array of tool name strings).

### `CUSTOM`
Input dataset uses arbitrary column names. You specify them explicitly in the payload:
- `inputColumnName` — column containing the agent input / query.
- `outputColumnName` — column containing the agent output / response.
- `groundTruthColumnName` — (optional) column containing the reference / ground-truth answer.
- `conversationIdColumnName` — (optional) column identifying conversation groupings.
- `conversationSortingKeyColumnName` — (optional) column used to sort turns within a conversation (e.g. a timestamp).
- `hasConversations` — set `true` when the dataset contains multi-turn conversations.
- `actualToolCallsColumnName` — (optional) column containing the actual tool calls made by the agent; the column must hold an **array of tool names as strings**.
- `referenceToolCallsColumnName` — (optional) column containing the expected / reference tool calls; must also be an **array of tool names as strings**.
- `evaluatedAgentId` / `evaluatedAgentVersion` — (optional) link to a specific DSS agent and version for tracking.

No required column names are enforced by DSS; the recipe uses whatever column names you configure. Omit optional column keys when not needed.

## Metric → Column Dependencies

Each metric requires certain columns to be configured; selecting a metric whose required columns are absent or whose payload fields are unset causes recipe failure. The table below maps each metric to the columns it needs:

| Requires | Metrics |
|---|---|
| Actual tool calls + Reference tool calls | `toolCallExactMatch`, `toolCallPartialMatch`, `toolCallPrecisionRecallF1` |
| Input + Output + Ground Truth + Actual tool calls + both LLMs | `agentGoalAccuracyWithReference` |
| Input + Output + Actual tool calls + both LLMs | `agentGoalAccuracyWithoutReference` |
| Input + Output + Ground Truth + both LLMs | `answerCorrectness`, `answerSimilarity` |
| Output + Ground Truth | `bertScore` |

See the [reference doc](references/recipe_settings_and_payload.md) for the full column-by-metric breakdown.

## Recipe-Specific Guardrails

1. **Before configuring `inputColumnName` and `outputColumnName`**, call `get_dataset_sample` on the input dataset and confirm the expected columns are present.
   - For `PROMPT_RECIPE`: check for `llm_raw_query` and `llm_raw_response`. If missing, fix the upstream prompt recipe's `rawQueryOutputMode` / `rawResponseOutputMode` and rebuild it first.
   - For `AGENT_INTERACTION_LOGS`: check for `dku_llm_mesh_raw_query`, `dku_llm_mesh_raw_response`, `conversation_id`, `begin_time`, and `end_time`. All five must be present or the recipe will refuse to run.
   - For `CUSTOM`: verify the column names you intend to set in `inputColumnName`, `outputColumnName`, and `groundTruthColumnName` are actually present in the dataset.
2. Preserve `params.envSelection` unless the user explicitly asks to switch the execution environment.
3. Keep `inputFormat`, input/output/ground-truth column names, and metric selection coherent.
4. Use output roles (`main`, `metrics`, `evaluationStore`) instead of payload hacks for output configuration.
5. Preserve `completionLLMId` and `embeddingLLMId` unless the user explicitly asks to switch models.

## Type-Specific Update Notes

Use parent rules from `dataiku-skills/recipes/SKILL.md` section `Settings And Payload Update Rules`.

- Use `set_params` for environment/container settings and `set_payload` for evaluation behavior.
- Keep labels/custom metrics/custom traits stable unless explicitly changing the evaluation contract.

## DSS Documentation

- Agent evaluation docs: https://doc.dataiku.com/dss/latest/generative-ai/evaluation.html
