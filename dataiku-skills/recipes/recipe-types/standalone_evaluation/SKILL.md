---
name: dataiku-recipe-standalone_evaluation
description: "Evaluate externally produced model predictions with standalone evaluation recipes."
---

# standalone_evaluation Recipe Skill

Use this skill with `recipes` for work focused on recipe type `standalone_evaluation`.

## I/O Requirements

**Inputs:**
- 1 pre-scored dataset (role `main`) — must contain a predictions column; ground truth is optional (see below).
- 0 or 1 reference/training dataset (role `reference`) — optional; used for data drift detection.

**Output:** exactly 1 evaluation store (role `main`) — the eval store object is wired to the `main` output role, **not** `evaluationStore`. Each recipe run **appends a new evaluation** to the store.

## Steps to Create a Standalone Evaluation Recipe

1. **Pre-create the evaluation store** with `create_evaluation_store(project_key, name, flavor="TABULAR")` before creating the recipe; note the returned `evaluation_store_id`.
2. **Create the recipe** with `create_recipe`, passing the evaluation store as the `main` output (not `evaluationStore`). Example: `{"name": "<evaluation_store_id>", "role": "main"}`.
3. **Configure** using `set_recipe_settings` with `set_payload`.

## Key Payload Fields

Configure evaluation behavior via `set_payload`:

| Field | Description |
|---|---|
| `predictionType` | `"BINARY_CLASSIFICATION"`, `"MULTICLASS"`, or `"REGRESSION"` |
| `predictionVariable` | Name of the predictions column (mandatory) |
| `targetVariable` | Name of the ground-truth column (optional — omitting disables performance results but preserves drift analysis) |
| `weightsVariable` | Name of an optional sample weights column |
| `classes` | For classification: list of class values (e.g. `["0", "1"]`) |
| `probas` | For probabilistic classification: list of `{"value": "<col>", "key": "<class>"}` entries mapping probability columns to classes (e.g. `proba_1.0` → `"1"`) |
| `threshold` | Binary classification: decision threshold (default `0.5`) |
| `evaluationName` | Human-readable label for this run (defaults to timestamp) |
| `evaluationId` | Unique identifier in the store. Override to overwrite a prior evaluation instead of appending. |
| `labels` | List of user-defined label strings for semantic tagging of evaluations |
| `dontComputePerformance` | Set to `true` to run drift analysis only without a ground-truth column |
| `trainDataType` | Set to `"EXTERNAL"` for externally produced predictions |
| `modelType` | Set to `"EXTERNAL"` |
| `hasModel` | Set to `true` |

## Key Behaviors

- **Accumulating store:** each recipe run adds one new evaluation to the store. To overwrite a prior run, set `evaluationId` to match the existing entry.
- **Ground truth is optional:** omitting `targetVariable` disables performance metrics and results screens but drift analysis (via the reference dataset) still works.
- **Sampling:** evaluation uses at most 20,000 rows. Default is the first 20,000; sampling methodology is configurable.

## Preferred Tools

- Discover: `list_evaluation_stores(flavor="TABULAR")`
- Create store: `create_evaluation_store(flavor="TABULAR")`
- Inspect store run results: `get_evaluation_store_details`
- Delete store: `delete_evaluation_store`

## Required Reference Files

Read these references before editing standalone_evaluation recipes:

- [standalone_evaluation settings and payload](references/recipe_settings_and_payload.md) (always).

Before submitting any `set_payload` or `set_params` call, re-read `references/recipe_settings_and_payload.md` and make an explicit decision about each field you change.

## Type-Specific Update Notes

Use parent rules from `dataiku-skills/recipes/SKILL.md` section `Settings And Payload Update Rules`.

- Prefer `set_payload` for evaluation behavior; use `set_inputs` and `set_outputs` for I/O changes.

## DSS Reference

- Reference: `Evaluating other models (Standalone evaluation recipe)` (https://doc.dataiku.com/dss/latest/mlops/model-evaluations/external-models.html)
