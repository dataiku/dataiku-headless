---
name: dataiku-recipe-clustering_scoring
description: "Score saved clustering models on datasets and write scored outputs with cluster assignments."
---

# Clustering Scoring Recipe Overview

The `clustering_scoring` recipe scores one input dataset with one saved clustering model and writes one scored output dataset. The scored output adds a `cluster_labels` column to the input rows.

## I/O Requirements

**Inputs:**
- 1 dataset to score (role `main`).
- 1 saved clustering model (role `model`) — use the model **ID** from `list_saved_models`, not the display name.

**Output:** 1 scored dataset (role `main`).

```json
{
  "recipe_type": "clustering_scoring",
  "inputs": [
    {"name": "<dataset_name>", "role": "main"},
    {"name": "<saved_model_id>", "role": "model"}
  ],
  "outputs": ["<scored_output_dataset>"]
}
```

## Steps To Create Or Update A Clustering Scoring Recipe

Use the parent `recipes` skill for shared lifecycle steps (flow checks, recipe creation/selection, I/O changes, execution).

Then apply clustering-scoring-specific updates:

1. Discover the saved model with `list_saved_models` and confirm the input dataset with dataset tools.
2. **If creating a new recipe**, use the `create_recipe` call shown in ## I/O Requirements above.
3. Read current settings with `get_recipe_settings` and inspect `payload`, `params`, and the `model` / `main` I/O roles.
4. Update scoring behavior with `set_recipe_settings` action `set_payload`.
5. Use `set_inputs` when changing the scored dataset or saved model, and `set_outputs` when changing the scored output dataset.

## Required Reference Files

Read these references before editing clustering scoring recipes:

- [Clustering scoring recipe settings and payload](references/recipe_settings_and_payload.md) (always).

Before submitting any `set_payload` or `set_params` call, re-read `references/recipe_settings_and_payload.md` and make an explicit decision about each field you change.

## Recipe-Specific Guardrails

1. In observed recipes, scoring behavior is payload-driven. Prefer `set_payload`; `params` is only used for `containerSelection`.
2. Keep the I/O roles coherent:
- `inputs.model` should contain exactly one saved model reference.
- `inputs.main` should contain exactly one input dataset reference.
- `outputs.main` should contain exactly one scored output dataset reference.
3. Preserve runtime and engine blocks unless the user explicitly asks to change execution behavior:
- `backendType`
- `sparkParams`
- `pythonBatchSize`
4. If `filterInputColumns=true`, keep `keptInputColumns` aligned to the columns that should be passed into scoring.
5. Preserve `removeOutliers` unless the user explicitly requests outlier-handling changes.

## Type-Specific Update Notes

Use parent rules from `dataiku-skills/recipes/SKILL.md` section `Settings And Payload Update Rules`.

- For clustering scoring, prefer `set_payload` for scoring behavior.
- Use `set_params` only for focused changes to `containerSelection`.
- Use `merge=true, deep_merge=true` only for targeted nested payload patches.

## DSS Documentation

- Saved model scoring overview: https://doc.dataiku.com/dss/latest/machine-learning/scoring-engines.html
