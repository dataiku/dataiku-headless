---
name: dataiku-recipe-nlp_llm_evaluation
description: "Evaluate LLM and agent outputs with GenAI-specific evaluation workflows."
---

# nlp_llm_evaluation Recipe Skill

Use this skill with `recipes` for work focused on recipe type `nlp_llm_evaluation`.

## I/O Requirements

**Input:** exactly 1 dataset (role `main`).

**Outputs:** at least one of the following is required; all are individually optional:
- 0 or 1 evaluation store (role `evaluationStore`) — preferred for tracking, comparisons, and drift analysis. `appendMode` does not apply.
- 0 or 1 dataset (role `main`) — per-row evaluated output with metric columns.
- 0 or 1 metrics dataset (role `metrics`) — aggregate metrics; defaults to `appendMode: true`.

## Steps to Create an LLM Evaluation Recipe

Decide which outputs you need before creating the recipe:
- **Evaluation store** (preferred) — create one first with `create_evaluation_store(project_key, name, flavor="LLM")`; `mesFlavor` is immutable after creation.
- **Per-row dataset** (role `main`) — useful for row-level metric inspection downstream.
- **Metrics dataset** (role `metrics`) — useful for lightweight metric logging without a full evaluation store.

1. **Pre-create all desired outputs** before calling `create_recipe` — the SDK requires them to exist:
   - Evaluation store: `create_evaluation_store(project_key, name, flavor="LLM")`
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

## Preferred Tools

- Discover: `list_evaluation_stores(flavor="LLM")`
- Create store: `create_evaluation_store(flavor="LLM")`
- Inspect store run results: `get_evaluation_store_details`
- Delete store: `delete_evaluation_store`

## Required Reference Files

Read these references before editing nlp_llm_evaluation recipes:

- [nlp_llm_evaluation settings and payload](references/recipe_settings_and_payload.md) (always).

Before submitting any `set_payload` or `set_params` call, re-read `references/recipe_settings_and_payload.md` and make an explicit decision about each field you change.

## Input Format Options

`inputFormat` controls which columns the recipe reads. There are three options:

### `PROMPT_RECIPE`
Input dataset was produced by a prompt recipe. The recipe expects fixed column names:
- `llm_raw_query` — the prompt sent to the LLM/agent; emitted when `rawQueryOutputMode` is `"RAW"` or `"RAW_WITHOUT_FULL_IMAGES"` in the prompt recipe.
- `llm_raw_response` — the LLM/agent response; emitted when `rawResponseOutputMode` is `"RAW"` or `"RAW_WITHOUT_TRACES"` in the prompt recipe.

If either column is missing, fix the upstream prompt recipe's `rawQueryOutputMode` / `rawResponseOutputMode` and rebuild it before running the eval recipe.

### `DATAIKU_ANSWERS`
Input dataset comes from Dataiku Answers. Column names are **fixed**:
- `question` — the input sent to the LLM (maps to `inputColumnName`).
- `answer` — the LLM response (maps to `outputColumnName`).
- `sources` — (optional) RAG context (maps to `contextColumnName`); used by context-based metrics.

If these columns are missing from the input dataset, the recipe will fail.

### `CUSTOM`
Input dataset uses arbitrary column names. You specify them explicitly in the payload:
- `inputColumnName` — column containing the LLM input / query.
- `outputColumnName` — column containing the LLM output / response.
- `groundTruthColumnName` — (optional) column with the reference / expected answer; required for reference-based metrics (`answerCorrectness`, `bleu`, `rouge`).
- `contextColumnName` — (optional) column with RAG context; used by context-based metrics (`answerRelevancy`, `contextPrecision`, `contextRecall`, `faithfulness`).

Omit optional column keys when not needed.

## Metric → Column Dependencies

Each metric requires certain columns to be configured. Selecting a metric without its required columns causes recipe failure. `contextColumnName` is only available for `QUESTION_ANSWERING` and `OTHER_LLM_TASK` task types.

| Requires | Metrics |
|---|---|
| Input + Output + Ground Truth + both LLMs | `answerCorrectness`, `answerSimilarity` |
| Input + Output + both LLMs (+ Context optional) | `answerRelevancy`, `faithfulness` |
| Input + Ground Truth + both LLMs (+ Context optional) | `contextPrecision`, `contextRecall` |
| Both LLMs only | `multimodalFairness`, `multimodalRelevancy` |
| Output + Ground Truth | `bertScore`, `bleu`, `rouge` |

See the [reference doc](references/recipe_settings_and_payload.md) for the full column-by-metric breakdown.

## Code Environment Requirement

`nlp_llm_evaluation` requires `langchain` and `langchain_core` to be installed in the recipe's code env. If the recipe fails immediately with `ModuleNotFoundError: No module named 'langchain'`, the code env is missing these packages. Ask the user for the name of a code env with the required packages.

## Recipe-Specific Guardrails

1. **Before calling `set_payload`**, confirm the payload includes all required fields: `inputFormat`, `llmTaskType`, `inputColumnName`, `outputColumnName`. Omitting `llmTaskType` causes the recipe to fail with "You need to select a Task." at runtime.
2. **Before configuring `inputColumnName` and `outputColumnName`**, call `get_dataset_sample` on the input dataset and confirm the expected columns are present.
   - For `PROMPT_RECIPE`: check for `llm_raw_query` and `llm_raw_response`. If missing, fix the upstream prompt recipe's `rawQueryOutputMode` / `rawResponseOutputMode` and rebuild it first.
   - For `DATAIKU_ANSWERS`: check for `question` and `answer` (and `sources` if using context-based metrics). These are fixed — the recipe will fail if they are missing.
   - For `CUSTOM`: verify the column names you intend to set in `inputColumnName` and `outputColumnName` are actually present in the dataset.

## Type-Specific Update Notes

Use parent rules from `dataiku-skills/recipes/SKILL.md` section `Settings And Payload Update Rules`.

- Prefer `set_payload` for evaluation behavior; use `set_inputs` and `set_outputs` for I/O changes.

## DSS Reference

- Reference: `Evaluating LLMs & GenAI use cases` (https://doc.dataiku.com/dss/latest/generative-ai/evaluation.html)
