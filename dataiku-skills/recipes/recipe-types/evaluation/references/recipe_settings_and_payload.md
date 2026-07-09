---
name: evaluation-settings-and-payload-reference
description: "Observed params and payload structure for evaluation recipes."
---

# evaluation Settings And Payload Reference

Use this reference for `evaluation` edits.

## Observed Settings Shape

- `params` holds execution environment settings
- `payload` controls which metrics to compute, which columns to output, drift behavior, scoring behavior, and sampling

Observed top-level `params` keys:

- `containerSelection`

Observed top-level `payload` keys:

- `predictionType`
- `taskType`
- `savedModelType`
- `modelVersionId`
- `metrics`
- `customMetrics`
- `customEvaluationMetrics`
- `possibleCustomMetrics`
- `labels`
- `outputs`
- `outputProbabilities`
- `outputProbaPercentiles`
- `outputExplanations`
- `individualExplanationParams`
- `outputModelMetadata`
- `skipScoring`
- `filterInputColumns`
- `keptInputColumns`
- `dontComputePerformance`
- `treatPerfMetricsFailureAsError`
- `overrideModelSpecifiedThreshold`
- `forcedClassifierThreshold`
- `dataDriftColumnHandling`
- `driftConfidenceLevel`
- `treatDriftFailureAsError`
- `hasTextDrift`
- `textDriftParams`
- `hasImageDrift`
- `imageDriftParams`
- `limitSampling`
- `selection`
- `backendType`
- `sparkParams`
- `sqlPipelineParams`
- `gpuConfig`
- `batchSize`
- `pythonBatchSize`

## Params Notes

- `params.containerSelection`: execution container. Preserve unless the user explicitly asks to change it.
- Unlike most recipe types, `evaluation` does not have a `params.envSelection` — the code env is inherited from the saved model.

## Payload Matrix

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `predictionType` | yes | `enum` | `BINARY_CLASSIFICATION`, `MULTICLASS`, or `REGRESSION`. Matches the saved model type. |
| `taskType` | yes | `enum` | `PREDICTION`. |
| `savedModelType` | yes | `enum` | `DSS_MANAGED` for DSS visual ML models. |
| `modelVersionId` | no | `string` | ID of a specific model version to evaluate. Empty string (`""`) means the active version. |
| `metrics` | no | `list<string>` | Metrics to compute. Observed: `precision`, `recall`, `auc`, `averagePrecision`, `f1`, `accuracy`, `mcc`, `hammingLoss`, `logLoss`, `lift`, `calibrationLoss`, `customScore`, `costMatrixGain`. |
| `customMetrics` | no | `list<object>` | Custom metric definitions. Empty list is valid. |
| `customEvaluationMetrics` | no | `list<object>` | Additional custom evaluation metric definitions. Empty list is valid. |
| `labels` | no | `list<object>` | Label definitions for semantic tagging of evaluations. Empty list is valid. |
| `outputs` | no | `list<string>` | Extra columns to include in the per-row output dataset. Observed: `["prediction_correct"]`. |
| `outputProbabilities` | no | `boolean` | Include probability columns in the per-row output. Default `true`. |
| `outputProbaPercentiles` | no | `boolean` | Include probability percentile columns. Default `false`. |
| `outputExplanations` | no | `boolean` | Include individual prediction explanations. Default `false`. |
| `individualExplanationParams` | no | `object` | Explanation computation settings (method, number of explanations, etc.). Preserve unless explicitly changing. |
| `outputModelMetadata` | no | `boolean` | Include model metadata columns in output. Default `false`. |
| `skipScoring` | no | `boolean` | Skip the scoring step and only compute metrics on a pre-scored dataset. Default `false`. |
| `filterInputColumns` | no | `boolean` | Whether to drop input columns not in `keptInputColumns`. Default `false`. |
| `keptInputColumns` | no | `list<string>` | Columns to pass through when `filterInputColumns` is `true`. |
| `dontComputePerformance` | no | `boolean` | Skip performance metrics (e.g. for drift-only mode). Default `false`. |
| `treatPerfMetricsFailureAsError` | no | `boolean` | Whether performance metric failure aborts the run. Default `true`. |
| `overrideModelSpecifiedThreshold` | no | `boolean` | Use `forcedClassifierThreshold` instead of the model's threshold. Default `false`. |
| `forcedClassifierThreshold` | no | `float` | Override threshold value. Only used when `overrideModelSpecifiedThreshold: true`. |
| `dataDriftColumnHandling` | no | `object` | Per-column drift override settings. Usually empty (`{}`). |
| `driftConfidenceLevel` | no | `float` | Statistical confidence level for drift detection. Default `0.95`. |
| `treatDriftFailureAsError` | no | `boolean` | Whether drift computation failure aborts the run. Default `true`. |
| `hasTextDrift` | no | `boolean` | Whether text drift detection is enabled. Default `false`. |
| `textDriftParams` | no | `object` | Text drift settings: `embeddingModelId`. Preserve unless explicitly changing. |
| `hasImageDrift` | no | `boolean` | Whether image drift detection is enabled. Default `false`. |
| `limitSampling` | no | `boolean` | Whether to limit input to the sampling cap. Default `true`. |
| `selection` | no | `object` | Input row sampling/filter settings. Preserve unless the user explicitly asks to change sampling behavior. |
| `backendType` | no | `enum` | Execution backend. Observed: `PY_MEMORY`. Preserve unless explicitly changing. |
| `sparkParams` | no | `object` | Spark execution settings. Preserve unless explicitly changing. |
| `sqlPipelineParams` | no | `object` | SQL pipeline settings. Preserve unless explicitly changing. |
| `gpuConfig` | no | `object` | GPU settings. Preserve unless explicitly changing. |
| `batchSize` | no | `integer` | Scoring batch size. Default `100`. |
| `pythonBatchSize` | no | `integer` | Python backend scoring batch size. Default `100000`. |

## Canonical Settings Example (Trimmed)

Observed from a binary classification evaluation recipe with eval store + metrics dataset outputs.

```json
{
  "params": {
    "containerSelection": {
      "containerMode": "INHERIT"
    }
  },
  "payload": {
    "predictionType": "BINARY_CLASSIFICATION",
    "taskType": "PREDICTION",
    "savedModelType": "DSS_MANAGED",
    "modelVersionId": "",
    "metrics": [
      "precision", "recall", "auc", "averagePrecision",
      "f1", "accuracy", "mcc", "hammingLoss", "logLoss",
      "lift", "calibrationLoss", "customScore", "costMatrixGain"
    ],
    "customMetrics": [],
    "customEvaluationMetrics": [],
    "labels": [],
    "outputs": ["prediction_correct"],
    "outputProbabilities": true,
    "outputProbaPercentiles": false,
    "outputExplanations": false,
    "outputModelMetadata": false,
    "skipScoring": false,
    "filterInputColumns": false,
    "keptInputColumns": [],
    "dontComputePerformance": false,
    "treatPerfMetricsFailureAsError": true,
    "overrideModelSpecifiedThreshold": false,
    "forcedClassifierThreshold": 0.0,
    "dataDriftColumnHandling": {},
    "driftConfidenceLevel": 0.95,
    "treatDriftFailureAsError": true,
    "hasTextDrift": false,
    "textDriftParams": {
      "embeddingModelId": "openai:<connection>:text-embedding-3-small"
    },
    "hasImageDrift": false,
    "limitSampling": true,
    "selection": {
      "samplingMethod": "FULL",
      "maxRecords": 10000,
      "filter": {"enabled": false, "distinct": false}
    },
    "backendType": "PY_MEMORY",
    "batchSize": 100,
    "pythonBatchSize": 100000
  }
}
```
