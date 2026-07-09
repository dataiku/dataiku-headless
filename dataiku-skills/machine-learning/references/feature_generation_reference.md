---
name: ml-feature-generation-reference
description: "Feature generation block schema reference for use with feature_generation patches in ML task types."
---

# Feature Generation Reference

The `feature_generation` block in `preprocessing` controls automatic feature interactions and transformations computed before model training. It is part of the raw settings returned by `get_ml_analysis_settings` under `mltask_settings.preprocessing.feature_generation`.

Modify it via `feature_preprocessing_patch` is not appropriate — instead write directly to `preprocessing.feature_generation` using a raw patch approach (read current settings, mutate the relevant sub-block, save via `set_recipe_settings` equivalent or by re-reading and patching).

## Shared Sub-blocks (All Task Types)

### `pairwise_linear`

Generates pairwise linear interaction features between numeric inputs.

| Key | Values | Notes |
|---|---|---|
| `behavior` | `DISABLED`, `ENABLED` | Whether to generate pairwise linear combinations |

### `polynomial_combinations`

Generates polynomial feature combinations.

| Key | Values | Notes |
|---|---|---|
| `behavior` | `DISABLED`, `ENABLED` | Whether to generate polynomial combinations |

### `manual_interactions`

Explicit user-defined interaction terms.

| Key | Values | Notes |
|---|---|---|
| `interactions` | array | List of manually specified interactions |

### `numericals_clustering`

Clusters numeric features and adds cluster assignment as a derived feature.

| Key | Values | Notes |
|---|---|---|
| `behavior` | `DISABLED`, `ENABLED` | Whether to apply numerical clustering |
| `k` | int | Number of clusters |
| `all_features` | bool | Use all numeric features |
| `input_features` | array of strings | Specific features to use when `all_features=false` |

### `categoricals_count_transformer`

Adds count-based features from categorical columns.

| Key | Values | Notes |
|---|---|---|
| `behavior` | `DISABLED`, `ENABLED` | Whether to apply count transformation |
| `all_features` | bool | Use all categorical features |
| `input_features` | array of strings | Specific features to use when `all_features=false` |

## Time Series Extensions

Time series analyses have two additional sub-blocks: `shifts` and `windows`.

### `shifts`

Lag features — past values of target or external features shifted relative to the forecast point.

Structure: `shifts` is an object keyed by feature name. Each value has:

| Key | Values | Notes |
|---|---|---|
| `from_forecast` | array of ints | Shift offsets relative to forecast origin (negative = past) |
| `from_horizon` | array of ints | Shift offsets relative to forecast horizon end |
| `from_horizon_mode` | `MANUAL`, `AUTO` | Whether horizon shifts are auto-selected or manually set |
| `from_horizon_auto` | array | Auto-selected horizon shifts (populated by DSS when `AUTO`) |

### `auto_shifts_params`

Controls automatic shift selection behavior.

| Key | Values | Notes |
|---|---|---|
| `max_selected_horizon_shifts` | int | Max number of auto-selected horizon shifts |
| `min_horizon_shift_past_only` | int | Minimum shift for past-only features (negative) |
| `max_horizon_shift_past_only` | int | Maximum shift for past-only features (negative) |
| `min_horizon_shift_known_in_advance` | int | Minimum shift for known-in-advance features |
| `max_horizon_shift_known_in_advance` | int | Maximum shift for known-in-advance features |

### `windows`

Rolling window aggregation features.

Each entry in the `windows` array:

| Key | Values | Notes |
|---|---|---|
| `length` | int | Window size in time steps |
| `shift` | int | Offset of window start relative to forecast origin |
| `is_from_forecast` | bool | Whether shift is relative to forecast origin |
| `operations_map` | object | Keyed by feature name; each value is an array of `{operation, enabled}` |

Supported `operation` values: `MEAN`, `MEDIAN`, `STD`, `MIN`, `MAX`, `FREQUENCY`.

### `windows_rescale_numericals`

| Key | Values | Notes |
|---|---|---|
| `windows_rescale_numericals` | bool | Rescale numeric window features |
| `windows_max_categories` | int | Max categories for window frequency features |
