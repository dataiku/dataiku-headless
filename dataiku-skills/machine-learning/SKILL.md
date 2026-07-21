---
name: machine-learning
description: Understand and inspect Dataiku visual ML analyses, trained models, and saved models. Use when an agent must interpret existing ML objects or gather grounded context before asking Cobuild to create, tune, train, deploy, or modify ML assets.
---

# Machine Learning

Use this skill to understand and inspect existing Dataiku visual ML analyses, trained models, and saved models.

## ML Concepts

An ML analysis is an experimentation and training configuration. It defines the task, source data, feature roles, preprocessing, algorithms, validation, and evaluation settings.

Trained models are candidate results produced within an analysis. Compare candidate models in the context of the task, validation method, business objective, and baseline rather than treating one metric as sufficient evidence.

A saved model is a deployed, versioned model artifact. Scoring and retraining are Flow concerns and should be created or modified through the recipes skill and Cobuild.

Data suitability and evaluation context matter before model selection. Inspect the source dataset before interpreting model results or preparing an ML request.

| Task type | Goal | Reference |
| --- | --- | --- |
| Prediction | Predict a known target value or category. | [Prediction](references/prediction.md) |
| Clustering | Discover similar-record segments without a target. | [Clustering](references/clustering.md) |
| Causal prediction | Estimate the effect of a treatment on an outcome. | [Causal Prediction](references/causal-prediction.md) |
| Time series forecasting | Predict future values along a time axis. | [Time Series Forecasting](references/timeseries-forecasting.md) |

## Inspection Workflow

1. Use `./dataiku-skills/datasets/SKILL.md` to inspect the source dataset's schema, quality signals, sample size, and potential leakage before interpreting or requesting ML work.
2. Use `list_ml_analyses` when analysis discovery, comparison, or reuse context matters. For a known analysis, use `get_ml_analysis_summary` for normalized context and `get_object_settings` with `object_type=ml_analysis` for raw settings evidence.
3. Use `list_ml_analysis_models` and `get_ml_model_details` to inspect candidate trained models, their evaluation results, and feature behavior.
4. Use `list_saved_models`, then `get_object_settings` with `object_type=saved_model`. Omit `version_id` to discover versions; pass one to inspect its detail snippet.
5. When training, deployment, or retraining is already in progress, use `./dataiku-skills/jobs/SKILL.md` to supervise the existing job.
6. Route ML analysis creation, tuning, training, deployment, and saved-model changes through `./dataiku-skills/cobuild/SKILL.md`.
7. Route scoring and retraining Flow assets through `./dataiku-skills/recipes/SKILL.md` and Cobuild.

## Preferred Tools

- `list_ml_analyses`
- `get_ml_analysis_summary`
- `get_object_settings`
- `list_ml_analysis_models`
- `get_ml_model_details`
- `list_saved_models`

## Safety Rules

- Discover analysis IDs, model IDs, saved-model IDs, and dataset names via tools; do not invent identifiers.
- Keep this skill read-only. Route ML analysis, training, deployment, and saved-model changes through `./dataiku-skills/cobuild/SKILL.md`.
- Interpret model results against the relevant business objective, validation design, baseline, and source-data quality.
- Do not claim causal effect from a prediction or clustering model.
- Flag likely leakage, severe class imbalance, small samples, train/test gaps, and implausibly strong performance before recommending deployment.
