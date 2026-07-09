---
name: machine-learning-prediction
description: Tune prediction analyses in Dataiku DSS after initial create-plus-guess. Use when an agent must modify prediction metrics, algorithms, splits, weighting, diagnostics, hyperparameter search behavior, feature roles, or raw modeling/preprocessing settings.
---

# Prediction Analysis Updates

## Workflow

1. `get_ml_analysis_settings` (raw) and optionally `get_ml_analysis_summary` (compact overview).
2. `update_prediction_analysis` — use first-class controls (metric, algorithms, split, weighting, search strategy/validation/budget, diagnostics) before falling back to raw `algorithm_settings_patch` / `feature_preprocessing_patch`.
3. `train_ml_analysis`.
4. `list_ml_analysis_models` → `get_ml_model_details` on the best.
5. Iterate on the same analysis; avoid creating near-duplicate analyses.

## Algorithm Identifiers

Always use these exact strings for the `algorithms` parameter. DSS rejects unknown identifiers.

### Classification

| Algorithm | Identifier |
| --- | --- |
| Logistic Regression | `LOGISTIC_REGRESSION` |
| Random Forest | `RANDOM_FOREST_CLASSIFICATION` |
| Gradient Boosted Trees | `GBT_CLASSIFICATION` |
| XGBoost | `XGBOOST_CLASSIFICATION` |
| LightGBM | `LIGHTGBM_CLASSIFICATION` |
| Decision Tree | `DECISION_TREE_CLASSIFICATION` |
| Extra Trees | `EXTRA_TREES` |
| SGD | `SGD_CLASSIFICATION` |
| SVM / SVC | `SVC_CLASSIFICATION` |
| Deep Neural Network | `DEEP_NEURAL_NETWORK_CLASSIFICATION` |
| Neural Network | `NEURAL_NETWORK` |
| KNN | `KNN` |
| TabICL | `TABICL_CLASSIFICATION` |
| Keras (custom code) | `KERAS_CODE` |

### Regression

| Algorithm | Identifier |
| --- | --- |
| Ridge Regression | `RIDGE_REGRESSION` |
| Lasso Regression | `LASSO_REGRESSION` |
| Least Squares | `LEASTSQUARE_REGRESSION` |
| Random Forest | `RANDOM_FOREST_REGRESSION` |
| Gradient Boosted Trees | `GBT_REGRESSION` |
| XGBoost | `XGBOOST_REGRESSION` |
| LightGBM | `LIGHTGBM_REGRESSION` |
| Decision Tree | `DECISION_TREE_REGRESSION` |
| SGD | `SGD_REGRESSION` |
| Deep Neural Network | `DEEP_NEURAL_NETWORK_REGRESSION` |
| SVM | `SVM_REGRESSION` |
| LARS | `LARS` |

## Feature Reduction

Control with `feature_reduction_method` in `update_prediction_analysis`.

| Method | Description | When to use |
|---|---|---|
| `NONE` | No automatic reduction | Default; full control via `included_features`/`rejected_features` |
| `RANDOM_FOREST` | Quick RF, keeps top N by importance | Best general-purpose choice |
| `LASSO` | L1 regularization; zeroes out weak features | Sparse linear relationships |
| `PCA` | Uncorrelated principal components | Highly correlated or very wide datasets |
| `ICA` | Statistically independent components | Mixed-signal data (e.g. sensors) |
| `CORRELATION` | Filters by absolute correlation with target | Fast linear first pass |

- `feature_reduction_n_features` (int): target features/components to keep — applies to `RANDOM_FOREST`, `PCA`, `ICA`, `CORRELATION`.
- `feature_reduction_variance_proportion` (float 0–1): PCA only — keep enough components to explain this fraction of variance. Takes precedence over `feature_reduction_n_features` for PCA.

## Required Reference Files

Read before using raw JSON patch parameters:
- [Per-feature preprocessing schema](../../references/feature_preprocessing_reference.md) — `feature_preprocessing_patch`
- [Algorithm settings schema](../../references/algorithm_settings_reference.md) — `algorithm_settings_patch`
- [Feature generation schema](../../references/feature_generation_reference.md) — `feature_generation` sub-block

## Guardrails

- Do not reject the target column.
- Do not mix `metric` and `custom_metric_code` in one update call.
- Re-read raw settings after raw DSS patch updates.
- Train as a separate step from settings changes.
