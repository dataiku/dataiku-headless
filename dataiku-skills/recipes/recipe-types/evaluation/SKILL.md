---
name: dataiku-recipe-evaluation
description: "Evaluate Dataiku prediction models using an evaluation recipe and metrics outputs."
---

# evaluation Recipe Skill

Use this skill with `recipes` for work focused on recipe type `evaluation`.

## I/O Requirements

**Inputs:**
- 1 labeled dataset (role `main`) — the evaluation dataset.
- 1 saved model (role `model`) — use `list_saved_models` to discover the ID. Defaults to the active version; a specific version can be configured in the payload.

**Outputs:** at least one of the following is required; all are individually optional:
- 0 or 1 evaluation store (role `evaluationStore`) — primary result; each recipe run **appends a new evaluation** to the store. `appendMode` does not apply.
- 0 or 1 dataset (role `main`) — per-row output with features, predictions, and prediction correctness.
- 0 or 1 metrics dataset (role `metrics`) — aggregate metrics subset from the evaluation store; defaults to `appendMode: true`.

## Steps to Create an Evaluation Recipe

Decide which outputs you need before creating the recipe:
- **Evaluation store** (preferred for MLOps tracking, drift analysis, model comparisons) — create one first with `create_evaluation_store(project_key, name, flavor="TABULAR")`; `mesFlavor` is immutable after creation.
- **Per-row dataset** (role `main`) — useful when you need prediction correctness at the row level for downstream analysis.
- **Metrics dataset** (role `metrics`) — useful for lightweight metric logging without a full evaluation store.

1. **Pre-create all desired outputs** before calling `create_recipe` — the SDK requires them to exist:
   - Evaluation store: `create_evaluation_store(project_key, name, flavor="TABULAR")`
   - Per-row dataset and/or metrics dataset: `create_managed_dataset`
2. **Create the recipe** with `create_recipe`. Example with all three outputs:
   ```json
   [
     {"name": "<store_id>", "role": "evaluationStore"},
     {"name": "<output_dataset>", "role": "main", "appendMode": false},
     {"name": "<metrics_dataset>", "role": "metrics", "appendMode": true}
   ]
   ```
3. **Configure** using `set_recipe_settings` with `set_payload`.

## Key Payload Fields

Configure evaluation behavior via `set_payload`:

| Field | Description |
|---|---|
| `evaluationName` | Human-readable label for this evaluation run (defaults to a timestamp). Useful for tracking evaluations over time. |
| `evaluationId` | Unique identifier for this evaluation in the store. Default is a random string. Override to overwrite a specific prior evaluation. |
| `labels` | List of user-defined label strings (e.g. `["baseline", "v2"]`) — attach semantics for comparisons. |
| `samplingMethod` | How to sample the evaluation dataset for metric computation. Respects a ~20,000-row limit. |
| `customMetrics` | List of Python custom metric definitions. Each metric returns a single float. |

## Key Behaviors

- **Accumulating store:** each recipe run appends one new evaluation record to the evaluation store; run it once per evaluation you intend to keep.
- **Model version:** the recipe defaults to the active version of the saved model. To pin a version, configure it in the payload.
- **Applies to:** visual ML models (classification, regression, time series forecasting) and imported MLflow tabular models.

## Limitations

- Non-partitioned models only.
- Computer vision, deep learning, and non-tabular MLflow inputs are not supported.
- Time series forecasting models do not support input data drift, prediction drift, or custom evaluation metrics.

## Preferred Tools

- Discover: `list_evaluation_stores(flavor="TABULAR")`
- Create store: `create_evaluation_store(flavor="TABULAR")`
- Inspect store run results: `get_evaluation_store_details`
- Delete store: `delete_evaluation_store`

## Required Reference Files

Read these references before editing evaluation recipes:

- [evaluation settings and payload](references/recipe_settings_and_payload.md) (always).

Before submitting any `set_payload` or `set_params` call, re-read `references/recipe_settings_and_payload.md` and make an explicit decision about each field you change.

## Type-Specific Update Notes

Use parent rules from `dataiku-skills/recipes/SKILL.md` section `Settings And Payload Update Rules`.

- Prefer `set_payload` for evaluation behavior; use `set_inputs` and `set_outputs` for I/O changes.
- Note: `evaluation` does not use `params.envSelection` — the code env is inherited from the saved model.

## DSS Reference

- Reference: `Evaluating Dataiku Prediction models` (https://doc.dataiku.com/dss/latest/mlops/model-evaluations/dss-models.html)
