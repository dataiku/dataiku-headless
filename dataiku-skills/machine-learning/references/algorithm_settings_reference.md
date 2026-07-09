---
name: ml-algorithm-settings-reference
description: "Hyperparameter key reference for algorithm_settings_patch across prediction, clustering, and time series ML task types."
---

# Algorithm Settings Reference

Use this reference when constructing an `algorithm_settings_patch` JSON object. The patch is a JSON object keyed by algorithm identifier (same identifiers used in the `algorithms` parameter). Each value is deep-merged into the algorithm's current settings — supply only the keys you want to change.

`get_ml_analysis_settings` returns only **enabled** algorithms in the `mltask_settings.modeling` block. Read those to see the current hyperparameter values before patching.

## Hyperparameter Format

**Pass plain Python lists directly.** The MCP tool automatically coerces them into the DSS grid object format:

```json
"n_estimators": [100, 200, 300]
```

is equivalent to passing the full DSS grid object. The tool preserves existing grid metadata (mode, range, limit) and updates only the candidate values.

**Scalar params must stay scalar.** Only grid-searchable params (those stored as DSS grid objects with a `values` key) accept plain lists. Scalar params like `early_stopping` (bool) or `subsample` (float) must be passed as their scalar type — they will error if sent as a list.

To see which params are grid objects vs scalars for an algorithm, call `get_ml_analysis_settings` and inspect the `mltask_settings.modeling.<algorithm>` block for that algorithm.

## Prediction — Classification & Regression

### `RANDOM_FOREST_CLASSIFICATION` / `RANDOM_FOREST_REGRESSION`

| Key | Type | Notes |
|---|---|---|
| `n_estimators` | int list | Number of trees to try, e.g. `[100, 200]` |
| `max_tree_depth` | int list | Max depth per tree, e.g. `[6, 13]` |
| `min_samples_leaf` | int list | Min samples per leaf |
| `selection_mode` | `"sqrt"`, `"prop"`, `"auto"` | Feature selection mode |
| `max_feature_prop` | float list | Fraction of features when `selection_mode="prop"` |
| `n_jobs` | int | Parallelism (−1 = all cores) |

### `GBT_CLASSIFICATION` / `GBT_REGRESSION`

| Key | Type | Notes |
|---|---|---|
| `n_estimators` | int list | Number of boosting rounds |
| `max_depth` | int list | Max tree depth |
| `min_samples_leaf` | int list | Min samples per leaf |
| `learning_rate` | float list | Step size shrinkage |

### `LIGHTGBM_CLASSIFICATION` / `LIGHTGBM_REGRESSION`

| Key | Type | Notes |
|---|---|---|
| `num_leaves` | int list | Max leaves per tree (complexity driver) |
| `n_estimators` | int list | Number of boosting rounds |
| `learning_rate` | float list | Step size shrinkage |
| `min_child_samples` | int list | Min samples per leaf |
| `colsample_bytree` | float list | Feature fraction per tree |
| `subsample` | float | Row fraction per tree |
| `early_stopping` | bool | Stop early if validation score stops improving |

### `XGBOOST_CLASSIFICATION` / `XGBOOST_REGRESSION`

| Key | Type | Notes |
|---|---|---|
| `max_depth` | int list | Max tree depth |
| `n_estimators` | int | Number of boosting rounds |
| `learning_rate` | float list | Step size shrinkage |
| `subsample` | float list | Row fraction per tree |
| `colsample_bytree` | float list | Feature fraction per tree |
| `early_stopping` | bool | Stop early if validation score stops improving |

### `LOGISTIC_REGRESSION`

| Key | Type | Notes |
|---|---|---|
| `penalty` | `"l1"`, `"l2"` | Regularization type |
| `C` | float list | Inverse regularization strength (higher = less regularization) |
| `multi_class` | `"ovr"`, `"multinomial"` | Multiclass strategy |

### `RIDGE_REGRESSION` / `LASSO_REGRESSION`

| Key | Type | Notes |
|---|---|---|
| `alpha` | float list | Regularization strength |

### `DECISION_TREE_CLASSIFICATION` / `DECISION_TREE_REGRESSION`

| Key | Type | Notes |
|---|---|---|
| `max_depth` | int list | Max tree depth |
| `min_samples_leaf` | int list | Min samples per leaf |
| `criterion` | `"gini"`, `"entropy"` (classification) / `"mse"`, `"mae"` (regression) | Split criterion |

### `NEURAL_NETWORK`

| Key | Type | Notes |
|---|---|---|
| `layer_sizes` | int list list | Sizes of hidden layers, e.g. `[[100], [100, 50]]` |
| `activation` | `"relu"`, `"tanh"`, `"sigmoid"` | Activation function |
| `learning_rate_init` | float list | Initial learning rate |
| `alpha` | float list | L2 regularization term |
| `max_iter` | int | Max training epochs |

---

## Clustering

### `KMEANS` / `MINIBATCH_KMEANS`

| Key | Type | Notes |
|---|---|---|
| `k` | int list | Candidate cluster counts to try |
| `seed` | int | Random seed |
| `n_init` | int | Number of random restarts |

### `WARD` / `SPECTRAL`

| Key | Type | Notes |
|---|---|---|
| `k` | int list | Candidate cluster counts to try |

### `DBSCAN`

| Key | Type | Notes |
|---|---|---|
| `epsilon` | float list | Max distance between points in a cluster |
| `min_sample_ratio` | float | Minimum fraction of points to form a core point |

### `HDBSCAN`

| Key | Type | Notes |
|---|---|---|
| `min_cluster_size_ratio` | float list | Min cluster size as fraction of dataset |

### `TWO_STEP`

| Key | Type | Notes |
|---|---|---|
| `kmeans_k` | int | Number of micro-clusters in first step |
| `n_clusters` | int | Final cluster count |
| `seed` | int | Random seed |

### `ISOLATION_FOREST`

| Key | Type | Notes |
|---|---|---|
| `n_estimators` | int | Number of trees |
| `contamination` | float | Expected fraction of outliers |
| `max_samples` | float | Fraction of samples per tree |

---

## Time Series

### `PROPHET`

| Key | Type | Notes |
|---|---|---|
| `changepoint_prior_scale` | float list | Flexibility of trend changepoints (higher = more flexible) |
| `seasonality_mode` | `"additive"`, `"multiplicative"` | How seasonality interacts with trend |
| `growth` | `"linear"`, `"logistic"` | Trend growth model |
| `n_changepoints` | int | Number of potential changepoints |

### `AUTO_ARIMA`

| Key | Type | Notes |
|---|---|---|
| `m` | int | Seasonal period (e.g. 7 for weekly, 12 for monthly) |
| `information_criterion` | `"aic"`, `"bic"`, `"hqic"` | Model selection criterion |
| `method` | `"lbfgs"`, `"nm"`, `"bfgs"` | Optimization method |

### `GLUONTS_TORCH_DEEPAR` (DeepAR)

| Key | Type | Notes |
|---|---|---|
| `context_length` | int list | Number of past time steps used as input |
| `num_layers` | int list | Number of RNN layers |
| `num_cells` | int list | RNN hidden units |
| `dropout_rate` | float list | Dropout rate |
| `learning_rate` | float list | Training learning rate |
| `epochs` | int | Max training epochs |
| `batch_size` | int | Training batch size |

### `TFT_TIMESERIES` (Temporal Fusion Transformer)

| Key | Type | Notes |
|---|---|---|
| `context_length` | int list | Number of past time steps used as input |
| `hidden_size_factor` | int list | Dimension of hidden layers |
| `learning_rate` | float list | Training learning rate |
| `n_rnn_layers` | int | Number of LSTM layers |
| `n_head` | int | Number of attention heads |
| `max_steps` | int | Max training steps |
| `batch_size` | int | Training batch size |

### `NHITS_TIMESERIES`

| Key | Type | Notes |
|---|---|---|
| `context_length` | int list | Number of past time steps used as input |
| `learning_rate` | float list | Training learning rate |
| `max_steps` | int | Max training steps |
| `batch_size` | int | Training batch size |

---

## Example

Enable only LightGBM and XGBoost on a classification task, and tune their key hyperparameters:

```json
{
  "LIGHTGBM_CLASSIFICATION": {
    "num_leaves": [31, 64, 128],
    "learning_rate": [0.05, 0.1],
    "n_estimators": [100, 200],
    "early_stopping": true
  },
  "XGBOOST_CLASSIFICATION": {
    "max_depth": [3, 5, 7],
    "learning_rate": [0.05, 0.1, 0.2],
    "subsample": [0.8, 1.0]
  }
}
```
