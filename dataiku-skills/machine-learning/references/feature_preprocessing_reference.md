---
name: ml-feature-preprocessing-reference
description: "Per-feature preprocessing schema reference for use with feature_preprocessing_patch in all ML task types."
---

# Per-Feature Preprocessing Reference

Use this reference when constructing a `feature_preprocessing_patch` JSON object for any ML task type (prediction, clustering, causal prediction, time series forecasting).

`feature_preprocessing_patch` is a JSON object keyed by feature name. Each value is merged into that feature's existing preprocessing settings — supply only the keys you want to change.

The valid keys differ by feature type (`type` field in `get_ml_analysis_settings`).

## Numeric Features (`"type": "NUMERIC"`)

| Key | Valid values | Notes |
|---|---|---|
| `numerical_handling` | `REGULAR`, `BINARIZE`, `QUANTILE_BIN` | `QUANTILE_BIN` discretizes into equal-frequency bins |
| `rescaling` | `AVGSTD`, `MINMAX`, `NONE` | Standardize / normalize values |
| `missing_handling` | `NONE`, `IMPUTE`, `DROP_ROW`, `KEEP_NAN_OR_IMPUTE` | How nulls are handled |
| `missing_impute_with` | `MEAN`, `MEDIAN`, `MODE`, `CONSTANT` | Strategy when imputing |
| `impute_constant_value` | float | Value used when `missing_impute_with=CONSTANT` |
| `generate_derivative` | `true` / `false` | Generate squared and square-root derived features |
| `quantile_bin_nb_bins` | int | Number of bins for `QUANTILE_BIN` (default 4) |

## Categorical Features (`"type": "CATEGORY"`)

| Key | Valid values | Notes |
|---|---|---|
| `category_handling` | `DUMMIFY`, `FLAG_PRESENCE`, `HASHING`, `ORDINAL`, `IMPACT`, `FREQUENCY` | Encoding method |
| `missing_handling` | `NONE`, `IMPUTE` | How nulls are handled |
| `missing_impute_with` | `MODE` | Impute with most frequent value |
| `dummy_clip` | `MAX_NB_CATEGORIES`, `CUMULATIVE_PROPORTION`, `MIN_SAMPLES` | How to clip rare categories |
| `max_nb_categories` | int | Keep top N categories (for `MAX_NB_CATEGORIES`) |
| `cumulative_proportion` | float 0–1 | Keep categories covering this proportion of rows |
| `min_samples` | int | Drop categories with fewer than N samples |
| `dummy_drop` | `NONE`, `AUTO`, `DROP` | Whether to drop one dummy column to avoid multicollinearity |

## Text Features (`"type": "TEXT"`)

| Key | Valid values | Notes |
|---|---|---|
| `text_handling` | `TOKENIZE_HASHING`, `TOKENIZE_HASHING_SVD`, `TOKENIZE_COUNT_VECTORIZER` | Vectorization method |
| `ngramMinSize` | int | Minimum n-gram size (default 1) |
| `ngramMaxSize` | int | Maximum n-gram size |
| `maxWords` | int | Vocabulary size cap (0 = unlimited) |
| `hashSize` | int | Feature hash space size for hashing methods |
| `stopWordsMode` | `NONE`, `BASIC` | Whether to filter common stop words |

## Example

Switch `Age` to min-max scaling with derivatives, and encode `Sex` with impact encoding:

```json
{
  "Age": {"rescaling": "MINMAX", "generate_derivative": true},
  "Sex": {"category_handling": "IMPACT"}
}
```
