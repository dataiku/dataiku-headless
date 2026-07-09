---
name: machine-learning-causal-prediction
description: Tune causal prediction analyses in Dataiku DSS after initial create-plus-guess. Use when an agent must modify causal outcome/treatment settings, algorithms, splits, feature roles, or raw causal settings.
---

# Causal Prediction Updates

Use this child skill after the analysis has already been created.

## Workflow

1. Read raw settings with `get_ml_analysis_settings`.
2. Confirm the treatment variable, outcome variable, control value, and enabled algorithms.
3. Update the task with `update_causal_prediction_analysis`.
4. Train with `train_ml_analysis`.
5. Compare trained models and inspect details with `get_ml_model_details`.

## Preferred Mutations

- Adjust outcome variable through reguess when needed.
- Update treatment variable, control value, treatment values, and positive class carefully.
- Tune split strategy and enabled algorithms.
- Reject identifiers and irrelevant covariates while preserving target and treatment roles.
- Use raw `algorithm_settings_patch` and `feature_preprocessing_patch` for advanced tuning.

## Algorithm Identifiers

Always use these exact strings for the `algorithms` parameter of `update_causal_prediction_analysis`.

### Causal-Specific

| Algorithm | Correct identifier |
|---|---|
| Causal Forest | `CAUSAL_FOREST` |

### Shared Classification Algorithms (for binary causal tasks)

| Algorithm | Correct identifier |
|---|---|
| Logistic Regression | `LOGISTIC_REGRESSION` |
| Random Forest | `RANDOM_FOREST_CLASSIFICATION` |
| Gradient Boosted Trees | `GBT_CLASSIFICATION` |
| XGBoost | `XGBOOST_CLASSIFICATION` |
| LightGBM | `LIGHTGBM_CLASSIFICATION` |
| Decision Tree | `DECISION_TREE_CLASSIFICATION` |
| SGD | `SGD_CLASSIFICATION` |

### Shared Regression Algorithms (for continuous outcome tasks)

| Algorithm | Correct identifier |
|---|---|
| Ridge Regression | `RIDGE_REGRESSION` |
| Lasso Regression | `LASSO_REGRESSION` |
| Random Forest | `RANDOM_FOREST_REGRESSION` |
| Gradient Boosted Trees | `GBT_REGRESSION` |
| XGBoost | `XGBOOST_REGRESSION` |
| LightGBM | `LIGHTGBM_REGRESSION` |

## Required Reference Files

Read these before using the raw JSON patch parameters:

- [Per-feature preprocessing schema](../../references/feature_preprocessing_reference.md) — schema tables for `feature_preprocessing_patch` (numeric, categorical, text).
- [Algorithm settings schema](../../references/algorithm_settings_reference.md) — hyperparameter key reference for `algorithm_settings_patch`.
- [Feature generation schema](../../references/feature_generation_reference.md) — `feature_generation` sub-block structure for interaction and transformation features.

## Guardrails

- Never reject or overwrite the treatment or target role accidentally.
- State clearly when treatment/control semantics are changed.
- Re-open raw settings after edits that touch treatment configuration.
