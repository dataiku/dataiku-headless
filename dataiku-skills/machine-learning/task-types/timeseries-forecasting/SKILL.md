---
name: machine-learning-timeseries-forecasting
description: Tune time series forecasting analyses in Dataiku DSS after initial create-plus-guess. Use when an agent must modify forecast horizon, time-step settings, identifiers, algorithms, feature roles, or raw forecasting settings.
---

# Time Series Forecasting Updates

Use this child skill after the analysis has already been created.

## Workflow

1. Read raw settings with `get_ml_analysis_settings`.
2. Confirm target variable, time variable, time step, horizon, and identifiers.
3. Update the task with `update_timeseries_forecasting_analysis`.
4. Train with `train_ml_analysis`.
5. Compare trained models and inspect details with `get_ml_model_details`.

## Preferred Mutations

- Reguess target, time variable, or time series identifiers when the current structure is wrong.
- Tune forecast horizon and time-step settings with the dedicated DSS methods.
- Change forecasting metric and enabled algorithms.
- Keep target/time/identifier columns protected when changing feature roles.
- Use raw `algorithm_settings_patch` and `feature_preprocessing_patch` for advanced tuning.
- Use the `feature_generation` block in raw settings to configure lag shifts and rolling windows.

## Algorithm Identifiers

Always use these exact strings for the `algorithms` parameter of `update_timeseries_forecasting_analysis`.

### Dedicated Time Series Algorithms

| Algorithm | Correct identifier |
|---|---|
| Trivial Identity (baseline) | `TRIVIAL_IDENTITY_TIMESERIES` |
| Seasonal Naive | `SEASONAL_NAIVE` |
| Auto ARIMA | `AUTO_ARIMA` |
| Seasonal LOESS (STL) | `SEASONAL_LOESS` |
| Prophet | `PROPHET` |
| GluonTS NPTS | `GLUONTS_NPTS_FORECASTER` |
| GluonTS DeepAR (PyTorch) | `GLUONTS_TORCH_DEEPAR` |
| GluonTS Simple Feed-Forward (PyTorch) | `GLUONTS_TORCH_SIMPLE_FEEDFORWARD` |
| N-HiTS | `NHITS_TIMESERIES` |
| Temporal Fusion Transformer | `TFT_TIMESERIES` |

### ML-Based Algorithms (use historical features as inputs)

| Algorithm | Correct identifier |
|---|---|
| Random Forest | `RANDOM_FOREST_REGRESSION` |
| LightGBM | `LIGHTGBM_REGRESSION` |
| XGBoost | `XGBOOST_REGRESSION` |
| Ridge Regression | `RIDGE_REGRESSION` |
| Gradient Boosted Trees | `GBT_REGRESSION` |

## Required Reference Files

Read these before using the raw JSON patch parameters:

- [Per-feature preprocessing schema](../../references/feature_preprocessing_reference.md) — schema tables for `feature_preprocessing_patch` (numeric, categorical, text).
- [Algorithm settings schema](../../references/algorithm_settings_reference.md) — hyperparameter key reference for `algorithm_settings_patch`.
- [Feature generation schema](../../references/feature_generation_reference.md) — `feature_generation` sub-block structure. For time series, pay particular attention to the `shifts` and `windows` sections, which control lag features and rolling aggregations — key levers for ML-based forecasting algorithms.

## Guardrails

- Do not reject the target, time variable, or time series identifiers.
- Re-open raw settings after reguess or time-step changes.
- Be explicit when changing horizon or timestamp handling because those alter evaluation behavior materially.
