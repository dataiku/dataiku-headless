---
name: clustering-scoring-recipe-settings-and-payload-reference
description: "Settings and payload reference for clustering scoring recipes, including saved-model wiring and scoring payload controls."
---

# Clustering Scoring Recipe Settings And Payload Reference

Use this reference for `clustering_scoring` recipe edits (`get_recipe_settings` + `set_recipe_settings`).

## Observed Settings Shape

In these recipes:

- `payload` controls scoring behavior.
- `params` only contains `containerSelection`.

## Inputs And Outputs

### Input Roles

| Role | Required | Domain | Notes |
| --- | --- | --- | --- |
| `model` | yes | `saved_model_ref` | One saved clustering model reference. In observed recipes this is a DSS saved model id such as `WhnOSgUQ`. |
| `main` | yes | `dataset_ref` | One input dataset name. |

Observed input item shape:

```json
{
  "model": {
    "items": [
      {"ref": "WhnOSgUQ", "deps": []}
    ]
  },
  "main": {
    "items": [
      {"ref": "titanic", "deps": []}
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
      {"ref": "titanic_clustering_scored", "appendMode": false}
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

## Payload Matrix

Observed top-level payload keys:

- `backendType`
- `filterInputColumns`
- `keptInputColumns`
- `outputModelMetadata`
- `pythonBatchSize`
- `removeOutliers`
- `sparkParams`

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `backendType` | yes | `enum/string` | Observed: `PY_MEMORY`. |
| `filterInputColumns` | no | `boolean` | If `true`, only columns in `keptInputColumns` are passed through scoring. |
| `keptInputColumns` | no | `list<string>` | Observed baseline: `[]`. |
| `outputModelMetadata` | no | `boolean` | Observed: `false`. |
| `pythonBatchSize` | no | `integer` | Observed: `100000`. |
| `removeOutliers` | no | `boolean` | Observed: `false`. |
| `sparkParams` | no | `object` | Spark execution block; preserve unless explicitly changing runtime behavior. |

Observed baseline payload:

```json
{
  "pythonBatchSize": 100000,
  "keptInputColumns": [],
  "outputModelMetadata": false,
  "backendType": "PY_MEMORY",
  "filterInputColumns": false,
  "removeOutliers": false,
  "sparkParams": {
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
}
```

## Observed Output Shape

The clustering scoring output keeps the input columns and adds:

- `cluster_labels`

Use output schema or sample validation to confirm the scored dataset still contains the expected assignment column after edits.

## Runtime Blocks To Preserve

Unless the user explicitly requests engine changes, preserve these nested objects unchanged:

- `sparkParams`
- `containerSelection`

## Recommended Update Pattern

1. Read current settings with `get_recipe_settings`.
2. If changing scoring behavior, copy the current `payload` and edit only intended keys.
3. If rewiring the recipe, use `set_inputs` for `model` / `main` and `set_outputs` for `main`.
4. Use `set_params` only for focused `containerSelection` changes.
5. Re-read settings and validate both payload and I/O roles before running the recipe.
