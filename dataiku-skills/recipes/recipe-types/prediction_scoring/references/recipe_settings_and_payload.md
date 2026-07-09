---
name: prediction-scoring-recipe-settings-and-payload-reference
description: "Settings and payload reference for prediction scoring recipes, including saved-model wiring and family-specific scoring controls."
---

# Prediction Scoring Recipe Settings And Payload Reference

Use this reference for `prediction_scoring` recipe edits (`get_recipe_settings` + `set_recipe_settings`).

## Observed Settings Shape

In these recipes:

- `payload` controls scoring behavior.
- `params` only contains `containerSelection`.

The Prediction Scoring recipe supports the following model families:

- `BINARY_CLASSIFICATION`
- `MULTICLASS`
- `REGRESSION`
- `TIMESERIES_FORECAST`
- `CAUSAL_BINARY_CLASSIFICATION`

## Inputs And Outputs

### Input Roles

| Role | Required | Domain | Notes |
| --- | --- | --- | --- |
| `model` | yes | `saved_model_ref` | One saved model reference. In observed recipes this is a DSS saved model id such as `gjxIcQce`. |
| `main` | yes | `dataset_ref` | One input dataset name. |

Observed input item shape:

```json
{
  "model": {
    "items": [
      {"ref": "gjxIcQce", "deps": []}
    ]
  },
  "main": {
    "items": [
      {"ref": "titanic_to_score", "deps": []}
    ]
  }
}
```

### Output Roles

| Role | Required | Domain | Notes |
| --- | --- | --- | --- |
| `main` | yes | `dataset_ref` | One scored output dataset. |

Observed output item shape:

```json
{
  "main": {
    "items": [
      {"ref": "titanic_to_score_scored", "appendMode": false}
    ]
  }
}
```

## Params Matrix

Observed `params` keys:

- `containerSelection`

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `containerSelection` | no | `object` | Container execution selection block. Preserve unless the user explicitly requests execution-routing changes. |

Observed baseline:

```json
{
  "containerSelection": {
    "containerMode": "INHERIT"
  }
}
```

## Payload Model

Common top-level payload blocks observed across prediction scoring recipes:

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `backendType` | yes | `enum/string` | Observed: `PY_MEMORY`. |
| `filterInputColumns` | no | `boolean` | If `true`, only columns in `keptInputColumns` are passed through scoring. |
| `keptInputColumns` | no | `list<string>` | Observed as `[]` or a selected subset for forecasting. |
| `outputModelMetadata` | no | `boolean` | Observed: `false`. |
| `pythonBatchSize` | no | `integer` | Observed: `100000`. |
| `sparkParams` | no | `object` | Spark execution block; preserve unless explicitly changing runtime behavior. |
| `predictionType` | yes | `enum/string` | Observed: `BINARY_CLASSIFICATION`, `MULTICLASS`, `REGRESSION`, `TIMESERIES_FORECAST`, `CAUSAL_BINARY_CLASSIFICATION`. |
| `savedModelType` | yes | `enum/string` | Observed: `DSS_MANAGED`. |
| `sqlPipelineParams` | no | `object` | SQL pipeline block; preserve unless explicitly changing runtime behavior. |
| `batchSize` | no | `integer` | Observed: `100`. |
| `outputProbabilities` | no | `boolean` | Observed: `true` in all live recipes. |
| `outputProbaPercentiles` | no | `boolean` | Observed: `false`. |
| `forcedClassifierThreshold` | no | `number` | Observed: `0`. Used with `overrideModelSpecifiedThreshold`. |
| `overrideModelSpecifiedThreshold` | no | `boolean` | Observed: `false`. |
| `pastTimestepsToInclude` | no | `integer` | Observed: `-1`. Preserve unless intentionally changing time-series windowing behavior. |
| `mlFlowOutputStyle` | no | `enum/string` | Observed: `PARSED`. |
| `needsInputDataFolder` | no | `boolean` | Observed: `false`. |
| `refitModel` | no | `boolean` | Observed: `false`. |
| `outputExplanations` | no | `boolean` | Observed: `false`. |
| `individualExplanationParams` | no | `object` | Explanation settings block. |
| `gpuConfig` | no | `object` | GPU execution block; preserve unless explicitly changing runtime behavior. |
| `forceOriginalEngine` | no | `boolean` | Observed: `false`. |
| `assignmentThreshold` | no | `number` | Observed: `0`. |
| `assignTreatment` | conditional | `boolean` | Causal scoring control. Observed `true` for causal recipes. |
| `computePropensity` | conditional | `boolean` | Causal scoring control. Observed `true` for causal recipes. |
| `treatmentAssignmentMode` | conditional | `enum/string` | Observed: `SAMPLE_RATIO_APPROX`. |
| `treatmentRatio` | conditional | `number` | Observed: `0`. |
| `predictionLength` | conditional | `integer` | Forecasting horizon. Observed: `10` for the time-series recipes. |

## Family-Specific Notes

### Binary Classification

Observed baseline:

```json
{
  "predictionType": "BINARY_CLASSIFICATION",
  "filterInputColumns": false,
  "keptInputColumns": [],
  "outputProbabilities": true,
  "outputProbaPercentiles": false,
  "forcedClassifierThreshold": 0,
  "overrideModelSpecifiedThreshold": false,
  "outputExplanations": false,
  "outputModelMetadata": false,
  "refitModel": false,
  "backendType": "PY_MEMORY"
}
```

Observed output columns included:

- `prediction`
- probability columns such as `proba_0`, `proba_1`

### Multiclass

Observed baseline:

```json
{
  "predictionType": "MULTICLASS",
  "filterInputColumns": false,
  "keptInputColumns": [],
  "outputProbabilities": true,
  "outputProbaPercentiles": false,
  "forcedClassifierThreshold": 0,
  "overrideModelSpecifiedThreshold": false,
  "outputExplanations": false,
  "outputModelMetadata": false,
  "backendType": "PY_MEMORY"
}
```

Observed output columns included:

- `prediction`
- one probability column per class such as `proba_1`, `proba_2`, `proba_3`

Observed alternate variant:

- `filterInputColumns=true` with a narrowed `keptInputColumns` list
- `outputProbabilities=false`
- `outputExplanations=true`
- `outputModelMetadata=true`

That variant produced:

- `prediction`
- `explanations`
- model metadata columns such as `smmd_savedModelId`, `smmd_modelVersion`, `smmd_fullModelId`, `smmd_predictionTime`

### Regression

Observed baseline:

```json
{
  "predictionType": "REGRESSION",
  "filterInputColumns": false,
  "keptInputColumns": [],
  "outputProbabilities": true,
  "outputProbaPercentiles": false,
  "outputExplanations": false,
  "outputModelMetadata": false,
  "backendType": "PY_MEMORY"
}
```

Observed output columns included:

- `prediction`

Observed alternate variant:

- `outputExplanations=true`
- `outputModelMetadata=true`

That variant produced:

- `prediction`
- `explanations`
- model metadata columns such as `smmd_savedModelId`, `smmd_modelVersion`, `smmd_fullModelId`, `smmd_predictionTime`

### Time Series Forecasting

Observed baseline:

```json
{
  "predictionType": "TIMESERIES_FORECAST",
  "filterInputColumns": true,
  "keptInputColumns": ["date", "orders"],
  "predictionLength": 10,
  "outputProbabilities": true,
  "outputModelMetadata": false,
  "backendType": "PY_MEMORY"
}
```

Observed output columns included:

- `forecast`
- quantile columns such as `quantile_01` through `quantile_09`

### Causal Prediction

Observed baseline:

```json
{
  "predictionType": "CAUSAL_BINARY_CLASSIFICATION",
  "filterInputColumns": false,
  "keptInputColumns": [],
  "assignTreatment": true,
  "computePropensity": true,
  "treatmentAssignmentMode": "SAMPLE_RATIO_APPROX",
  "treatmentRatio": 0,
  "outputProbabilities": true,
  "outputModelMetadata": false,
  "backendType": "PY_MEMORY"
}
```

Observed output columns included:

- `predicted_effect`
- `propensity`
- `treatment_recommended`

## Runtime Blocks To Preserve

Unless the user explicitly requests engine changes, preserve these nested objects unchanged:

- `sparkParams`
- `sqlPipelineParams`
- `gpuConfig`
- `individualExplanationParams`
- `containerSelection`

Observed `sparkParams` baseline:

```json
{
  "pipelineAllowMerge": true,
  "sparkPreparedDFStorageLevel": "MEMORY_AND_DISK",
  "pipelineAllowStart": true,
  "sparkExecutionEngine": "SPARK_SUBMIT",
  "sparkConf": {
    "inheritConf": "default",
    "conf": []
  },
  "sparkRepartitionNonHDFS": 1,
  "sparkUseGlobalMetastore": false
}
```

## Recommended Update Pattern

1. Read current settings with `get_recipe_settings`.
2. If changing scoring behavior, copy the current `payload` and edit only intended keys.
3. If rewiring the recipe, use `set_inputs` for `model` / `main` and `set_outputs` for `main`.
4. Use `set_params` only for focused `containerSelection` changes.
5. Re-read settings and validate both payload and I/O roles before running the recipe.
