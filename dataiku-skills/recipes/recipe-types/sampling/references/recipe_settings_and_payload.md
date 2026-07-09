---
name: sampling-recipe-settings-and-payload-reference
description: "Settings and payload reference for sampling recipes."
---

# Sampling Recipe Settings And Payload Reference

Use this reference for `sampling` edits with `get_recipe_settings` + `set_recipe_settings` actions (`set_params` and `set_payload`).

## Settings Model

Sampling configuration is split across:

- `params.selection`: sampling strategy and controls.
- `params.engineParams`: execution engine controls (preserve unless intentionally changing engine behavior).
- `payload`: optional row filter block.

Top-level settings keys:

| Key | Required | Domain | Notes |
| --- | --- | --- | --- |
| `params.selection` | yes | `object` | Main sampling behavior block. |
| `params.engineParams` | no | `object` | Engine/runtime controls; usually preserved. |
| `payload` | no | `object` | Filter payload section. Read [filter payload reference](filter_payload.md) when editing. |

## `params.selection` Parameter Matrix

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `samplingMethod` | yes | `enum` | `FULL` \| `HEAD_SEQUENTIAL` \| `RANDOM_FIXED_RATIO` \| `RANDOM_FIXED_NB` \| `COLUMN_BASED` \| `CLASS_REBALANCE_TARGET_NB_APPROX` \| `CLASS_REBALANCE_TARGET_RATIO_APPROX` \| `COLUMN_ORDERED` | Sampling strategy selector. |
| `maxRecords` | conditional | `number` | Any non-negative number, observed sentinel `-1` | Used by count-based methods. |
| `targetRatio` | conditional | `number` | Typical range `(0,1]` | Used by ratio-based methods. |
| `column` | conditional | `string<column_name>` | Any valid input column | Required for column-dependent methods. |
| `seed` | conditional | `integer` | Any integer | Reproducibility seed for random/rebalancing methods. |
| `ascending` | no | `boolean` | `true` \| `false` | Sort direction for `COLUMN_ORDERED`. |
| `partitionSelectionMethod` | no | `enum` | Observed: `ALL` | Partition scope selector. |
| `latestPartitionsN` | no | `integer` | Positive integer | Partition helper. |
| `ordering` | no | `object` | `{enabled, rules}` | Ordering metadata block. |
| `useMemTable` | no | `boolean` | `true` \| `false` | DSS execution hint. |
| `withinFirstN` | no | `integer` | Any integer | Additional row cap control. |
| `maxReadUncompressedBytes` | no | `integer` | Any integer | Read-size cap control. |
| `filter` | no | `object` | `{distinct, enabled}` | Internal selection filter block; prefer `payload.enabled` as the effective filter toggle. |

## Sampling Method Matrix

| `samplingMethod` | Required fields | Optional fields | Notes |
| --- | --- | --- | --- |
| `FULL` | none | `maxRecords=-1`, `targetRatio` placeholder | Keep all rows. |
| `HEAD_SEQUENTIAL` | `maxRecords` | none | First N rows. |
| `RANDOM_FIXED_RATIO` | `targetRatio` | `seed` | Random sample by ratio. |
| `RANDOM_FIXED_NB` | `maxRecords` | `seed` | Random sample by approximate count. |
| `COLUMN_BASED` | `column`, `maxRecords` | `seed` | Sample by values in one column. |
| `CLASS_REBALANCE_TARGET_NB_APPROX` | `column`, `maxRecords` | `seed` | Class rebalance by target count. |
| `CLASS_REBALANCE_TARGET_RATIO_APPROX` | `column`, `targetRatio` | `seed` | Class rebalance by target ratio. |
| `COLUMN_ORDERED` | `column`, `maxRecords` | `ascending` | Ordered top/bottom N sample. |

## Canonical Settings Template

```json
{
  "params": {
    "selection": {
      "samplingMethod": "FULL",
      "maxRecords": -1,
      "targetRatio": 0.02,
      "useMemTable": false,
      "filter": {"distinct": false, "enabled": false},
      "partitionSelectionMethod": "ALL",
      "latestPartitionsN": 1,
      "ordering": {"enabled": false, "rules": []},
      "ascending": true,
      "withinFirstN": -1,
      "maxReadUncompressedBytes": -1
    },
    "engineParams": {}
  },
  "payload": {
    "distinct": false,
    "enabled": false
  }
}
```

## Canonical Selection Examples

### Full dataset (no sampling)

```json
{
  "selection": {
    "samplingMethod": "FULL",
    "maxRecords": -1,
    "targetRatio": 0.02,
    "useMemTable": false,
    "filter": {"distinct": false, "enabled": false},
    "partitionSelectionMethod": "ALL",
    "latestPartitionsN": 1,
    "ordering": {"enabled": false, "rules": []},
    "ascending": true,
    "withinFirstN": -1,
    "maxReadUncompressedBytes": -1
  }
}
```

### Head sample (first 100 rows)

```json
{
  "selection": {
    "samplingMethod": "HEAD_SEQUENTIAL",
    "maxRecords": 100,
    "targetRatio": 0.02,
    "useMemTable": false,
    "filter": {"distinct": false, "enabled": false},
    "partitionSelectionMethod": "ALL",
    "latestPartitionsN": 1,
    "ordering": {"enabled": false, "rules": []},
    "ascending": true,
    "withinFirstN": -1,
    "maxReadUncompressedBytes": -1
  }
}
```

### Random ratio sample (50%) with seed

```json
{
  "selection": {
    "samplingMethod": "RANDOM_FIXED_RATIO",
    "targetRatio": 0.5,
    "seed": 42,
    "maxRecords": -1,
    "useMemTable": false,
    "filter": {"distinct": false, "enabled": false},
    "partitionSelectionMethod": "ALL",
    "latestPartitionsN": 1,
    "ordering": {"enabled": false, "rules": []},
    "ascending": true,
    "withinFirstN": -1,
    "maxReadUncompressedBytes": -1
  }
}
```

### Class rebalance by target count

```json
{
  "selection": {
    "samplingMethod": "CLASS_REBALANCE_TARGET_NB_APPROX",
    "column": "country",
    "maxRecords": 10,
    "seed": 31,
    "targetRatio": 0.02,
    "useMemTable": false,
    "filter": {"distinct": false, "enabled": false},
    "partitionSelectionMethod": "ALL",
    "latestPartitionsN": 1,
    "ordering": {"enabled": false, "rules": []},
    "ascending": true,
    "withinFirstN": -1,
    "maxReadUncompressedBytes": -1
  }
}
```

### Column-ordered sample (top 50 by one column)

```json
{
  "selection": {
    "samplingMethod": "COLUMN_ORDERED",
    "column": "age",
    "maxRecords": 50,
    "ascending": true,
    "targetRatio": 0.02,
    "useMemTable": false,
    "filter": {"distinct": false, "enabled": false},
    "partitionSelectionMethod": "ALL",
    "latestPartitionsN": 1,
    "ordering": {"enabled": false, "rules": []},
    "withinFirstN": -1,
    "maxReadUncompressedBytes": -1
  }
}
```
