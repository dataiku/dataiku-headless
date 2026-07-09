---
name: machine-learning-clustering
description: Tune clustering analyses in Dataiku DSS after initial create-plus-guess. Use when an agent must modify clustering algorithms, cluster counts, feature roles, or raw clustering settings.
---

# Clustering Analysis Updates

Use this child skill after the analysis has already been created.

## Workflow

1. Read raw settings with `get_ml_analysis_settings`.
2. Inspect the compact overview with `get_ml_analysis_summary` if useful.
3. Update the task with `update_clustering_analysis`.
4. Train with `train_ml_analysis`.
5. Compare models with `list_ml_analysis_models` and `get_ml_model_details`.

## Preferred Mutations

- Adjust enabled clustering algorithms.
- Set `n_clusters` when using cluster-count-based algorithms.
- Change clustering metric.
- Reject noisy identifier or sparse categorical features.
- Use raw `algorithm_settings_patch` and `feature_preprocessing_patch` only when simpler inputs are insufficient.

## Algorithm Identifiers

Always use these exact strings for the `algorithms` parameter of `update_clustering_analysis`.

| Algorithm | Correct identifier |
|---|---|
| K-Means | `KMEANS` |
| Mini-Batch K-Means | `MINIBATCH_KMEANS` |
| Agglomerative / Ward | `WARD` |
| Spectral Clustering | `SPECTRAL` |
| DBSCAN | `DBSCAN` |
| HDBSCAN | `HDBSCAN` |
| Two-Step | `TWO_STEP` |
| Isolation Forest | `ISOLATION_FOREST` |

## Clustering-Specific Preprocessing

Clustering analyses have two additional preprocessing blocks not present in prediction tasks.

### `preprocessing.reduce`

PCA-based dimensionality reduction applied before clustering.

| Key | Values | Notes |
|---|---|---|
| `enable` | bool | Enable PCA reduction |
| `disable` | bool | Explicitly disable (set `true` to turn off) |
| `kept_variance` | float 0–1 | Proportion of variance to retain (e.g., `0.9`) |

### `preprocessing.outliers`

Controls outlier handling before clustering.

| Key | Values | Notes |
|---|---|---|
| `method` | `CLUSTER`, `DROP` | `CLUSTER` assigns outliers to nearest cluster; `DROP` removes them |
| `min_cum_ratio` | float | Minimum cumulative size ratio for a cluster to be considered valid |
| `min_n` | int | Minimum number of points for a cluster to be considered valid |

Modify these blocks via `algorithm_settings_patch` with key `"reduce"` or `"outliers"` against the raw settings, or patch `preprocessing` directly after reading raw settings.

## Required Reference Files

Read these before using the raw JSON patch parameters:

- [Per-feature preprocessing schema](../../references/feature_preprocessing_reference.md) — schema tables for `feature_preprocessing_patch` (numeric, categorical, text).
- [Algorithm settings schema](../../references/algorithm_settings_reference.md) — hyperparameter key reference for `algorithm_settings_patch`.
- [Feature generation schema](../../references/feature_generation_reference.md) — `feature_generation` sub-block structure for interaction and transformation features.

## Guardrails

- Do not reject all usable features.
- Treat free-text and identifiers as likely reject candidates unless the existing analysis shows value.
- After changing cluster count or algorithms, retrain before making claims about model quality.
