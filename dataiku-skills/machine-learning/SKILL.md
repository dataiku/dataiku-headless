---
name: machine-learning
description: Inspect Dataiku visual ML analyses and saved models. Use when an agent must understand existing ML objects before asking Cobuild to create or modify project assets.
---

# Machine Learning Inspection

Use this skill to inspect existing ML analyses and saved models.

## Workflow

1. Use `list_ml_analyses`, `get_ml_analysis_summary`, and `get_ml_analysis_settings` to inspect analyses.
2. Use `list_ml_analysis_models` and `get_ml_model_details` to inspect trained models within an analysis.
3. Use `list_saved_models`, `list_saved_model_versions`, and `get_saved_model_version_details` to inspect saved models.
4. Route ML creation, tuning, training, deployment, or updates through `./dataiku-skills/cobuild/SKILL.md`.

## Preferred Tools

- `list_ml_analyses`
- `get_ml_analysis_summary`
- `get_ml_analysis_settings`
- `list_ml_analysis_models`
- `get_ml_model_details`
- `list_saved_models`
- `list_saved_model_versions`
- `get_saved_model_version_details`

## ML Task Types

The `task_type` field returned by the tools above (and `prediction_type` for prediction tasks) distinguishes four kinds of ML analysis:

| Task type | What it does |
| --- | --- |
| **Prediction** | Predicts a target column from feature columns. `prediction_type` narrows this further: binary/multiclass classification (predict a category) or regression (predict a number). |
| **Clustering** | Groups similar records together with no target column (unsupervised) — surfaces natural segments in the data rather than predicting a known label. |
| **Causal prediction** | Estimates the causal effect of a treatment variable on an outcome variable, controlling for confounders — answers "what changed *because of* the treatment," not just "what correlates with it." |
| **Time series forecasting** | Predicts future values of one or more target columns along a time axis, using historical values (and optionally identifiers for multiple parallel series). |

## Safety Rules

- Never invent analysis ids, model ids, or saved model ids.
- Keep this skill focused on inspection and Cobuild grounding.
