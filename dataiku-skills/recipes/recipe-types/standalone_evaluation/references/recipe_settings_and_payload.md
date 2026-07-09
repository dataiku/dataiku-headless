---
name: standalone-evaluation-settings-and-payload-reference
description: "Observed params and payload structure for standalone_evaluation recipes."
---

# standalone_evaluation Settings And Payload Reference

Use this reference for `standalone_evaluation` edits.

## Observed Settings Shape

- `params` holds execution environment settings
- `payload` controls prediction type, column mapping, performance computation, drift behavior, and sampling

Observed top-level `params` keys:

- `envSelection`
- `containerSelection`

Observed top-level `payload` keys:

- `predictionType`
- `predictionVariable`
- `targetVariable`
- `probas`
- `classes`
- `activeClassifierThreshold`
- `autoOptimizeThreshold`
- `isProbaAware`
- `dontComputePerformance`
- `treatPerfMetricsFailureAsError`
- `trainDataType`
- `modelType`
- `hasModel`
- `metricParams`
- `customEvaluationMetrics`
- `labels`
- `selection`
- `referenceDatasetSelection`
- `features`
- `dataDriftColumnHandling`
- `driftConfidenceLevel`
- `treatDriftFailureAsError`
- `hasTextDrift`
- `textDriftParams`
- `hasImageDrift`
- `imageDriftParams`
- `limitSampling`
- `sparkParams`
- `trainDataParams`
- `modelParams`

## Params Notes

- `params.envSelection`: code environment. Preserve unless the user explicitly asks to change it.
- `params.containerSelection`: execution container. Preserve unless the user explicitly asks to change it.

## Payload Matrix

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `predictionType` | yes | `enum` | `BINARY_CLASSIFICATION`, `MULTICLASS`, or `REGRESSION`. |
| `predictionVariable` | yes | `string` | Column containing the model's predictions. |
| `targetVariable` | no | `string` | Ground-truth column. Omit or set `dontComputePerformance: true` if no ground truth is available. |
| `probas` | no | `list<object>` | For probabilistic classification: `[{"value": "<col>", "key": "<class>"}]` mapping probability columns to class labels. E.g. `proba_1.0` → `"1.0"`. |
| `classes` | no | `list<string>` | Class labels for classification (e.g. `["0.0", "1.0"]`). Leave empty if not needed. |
| `activeClassifierThreshold` | no | `float` | Decision threshold for binary classification. Default `0.5`. |
| `autoOptimizeThreshold` | no | `boolean` | Whether DSS should auto-optimize the decision threshold. Default `true`. |
| `isProbaAware` | no | `boolean` | Set `true` when probability columns are present. |
| `dontComputePerformance` | no | `boolean` | Set `true` to run drift-only mode when no ground-truth column is available. Default `false`. |
| `treatPerfMetricsFailureAsError` | no | `boolean` | Whether a failure to compute performance metrics aborts the run. Default `true`. |
| `trainDataType` | no | `enum` | Set to `"EXTERNAL"` for externally produced predictions. |
| `modelType` | no | `enum` | Set to `"EXTERNAL"` for externally trained models. |
| `hasModel` | no | `boolean` | Set `true` when representing a model evaluation (vs. pure dataset drift). |
| `metricParams` | no | `object` | Classification metric parameters: `thresholdOptimizationMetric`, `classAveragingMethod`, `liftPoint`, `costMatrixWeights`, `customMetrics`. Preserve unless explicitly changing metric behavior. |
| `customEvaluationMetrics` | no | `list<object>` | Custom metric definitions. Empty list is valid. |
| `labels` | no | `list<object>` | Label definitions for semantic tagging of evaluations. Empty list is valid. |
| `selection` | no | `object` | Sampling for the main input dataset. Preserve unless the user explicitly asks to change sampling behavior. |
| `referenceDatasetSelection` | no | `object` | Sampling for the reference/training dataset (used for drift). Preserve unless the user explicitly asks to change sampling behavior. |
| `features` | no | `list<object>` | Feature drift configuration. Usually empty for external models (DSS infers from schema). |
| `dataDriftColumnHandling` | no | `object` | Per-column drift override settings. Usually empty. |
| `driftConfidenceLevel` | no | `float` | Statistical confidence level for drift detection. Default `0.95`. |
| `treatDriftFailureAsError` | no | `boolean` | Whether drift computation failure aborts the run. Default `true`. |
| `hasTextDrift` | no | `boolean` | Whether text drift detection is enabled. Default `false`. |
| `textDriftParams` | no | `object` | Text drift settings: `embeddingModelId`. Preserve unless explicitly changing. |
| `hasImageDrift` | no | `boolean` | Whether image drift detection is enabled. Default `false`. |
| `limitSampling` | no | `boolean` | Whether to limit input to the 20,000-row sampling cap. Default `true`. |
| `sparkParams` | no | `object` | Spark execution settings. Preserve unless explicitly changing. |
| `trainDataParams` | no | `object` | Additional training data parameters. Usually empty (`{}`). |
| `modelParams` | no | `object` | Additional model parameters. Usually empty (`{}`). |

## Canonical Settings Example (Trimmed)

This is the observed payload from a manually-created binary classification recipe in drift-only mode (no ground truth).

```json
{
  "params": {
    "envSelection": {
      "envMode": "EXPLICIT_ENV",
      "envName": "<env_name>"
    },
    "containerSelection": {
      "containerMode": "INHERIT"
    }
  },
  "payload": {
    "predictionType": "BINARY_CLASSIFICATION",
    "predictionVariable": "prediction",
    "targetVariable": "DEFAULT_NEW",
    "probas": [
      {"value": "proba_0.0", "key": "0.0"},
      {"value": "proba_1.0", "key": "1.0"}
    ],
    "classes": [],
    "activeClassifierThreshold": 0.5,
    "autoOptimizeThreshold": true,
    "isProbaAware": true,
    "dontComputePerformance": false,
    "treatPerfMetricsFailureAsError": true,
    "trainDataType": "EXTERNAL",
    "modelType": "EXTERNAL",
    "hasModel": true,
    "metricParams": {
      "thresholdOptimizationMetric": "F1",
      "classAveragingMethod": "MACRO",
      "liftPoint": 0.4,
      "netUpliftPoint": 0.5,
      "causalWeighting": "NO_WEIGHTING",
      "costMatrixWeights": {"fpGain": -0.3, "tpGain": 1, "fnGain": 0, "tnGain": 0},
      "customMetrics": []
    },
    "customEvaluationMetrics": [],
    "labels": [],
    "selection": {
      "samplingMethod": "FULL",
      "maxRecords": 10000,
      "filter": {"enabled": false, "distinct": false}
    },
    "referenceDatasetSelection": {
      "samplingMethod": "FULL",
      "maxRecords": 10000,
      "filter": {"enabled": false, "distinct": false}
    },
    "features": [],
    "dataDriftColumnHandling": {},
    "driftConfidenceLevel": 0.95,
    "treatDriftFailureAsError": true,
    "hasTextDrift": false,
    "textDriftParams": {
      "embeddingModelId": "openai:<connection>:text-embedding-3-small"
    },
    "hasImageDrift": false,
    "limitSampling": true,
    "trainDataParams": {},
    "modelParams": {}
  }
}
```

## Common Configuration Patterns

**Drift-only mode (no ground truth):**
- Set `dontComputePerformance: true`
- Omit `targetVariable` or leave it pointing to a column that doesn't exist
- Wire in a reference dataset (role `reference`) for drift comparison

**Performance mode (with ground truth):**
- Set `dontComputePerformance: false` (default)
- Set `targetVariable` to the ground-truth column name
- Ensure the input dataset contains that column with actual labels
