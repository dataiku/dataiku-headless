---
name: vstack-recipe-settings-and-payload-reference
description: "Settings and payload reference for vstack recipes, including mode-specific schema matching and column selection blocks."
---

# VStack Recipe Settings And Payload Reference

Use this reference for `vstack` payload edits (`get_recipe_settings` + `set_recipe_settings` action `set_payload`).

## Observed Settings Shape

In these recipes:

- `payload` controls behavior.
- `params` is empty.

Observed top-level payload keys:

- `mode`
- `selectedColumns`
- `virtualInputs`
- `postFilter`
- `addOriginColumn`
- `originColumnName`
- `engineParams`
- optional: `copySchemaFromDatasetWithName`, `selectedColumnsIndexes`

## Payload Matrix

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `mode` | yes | `enum` | Observed values: `UNION`, `INTERSECT`, `FROM_DATASET`, `FROM_INDEX`, `REMAP`, `CUSTOM`. |
| `selectedColumns` | yes | `list<string<column_name>>` | Output columns for stacked result. |
| `virtualInputs` | yes | `list<object>` | One entry per input dataset (index/label/filter/mapping). |
| `postFilter` | no | `object` | Optional filter block after stack. |
| `addOriginColumn` | no | `boolean` | Whether to add origin dataset column. |
| `originColumnName` | no | `string<column_name>` | Origin column name (for example `original_dataset`). |
| `engineParams` | no | `object` | Engine/runtime settings; preserve unless explicitly changing execution behavior. |
| `copySchemaFromDatasetWithName` | conditional | `string<dataset_name>` | Schema-source dataset name (seen in `FROM_DATASET`, `FROM_INDEX`, `REMAP`). |
| `selectedColumnsIndexes` | conditional | `list<integer>` | Column-index list used with `FROM_INDEX`. |

## `virtualInputs[]` Matrix

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `index` | yes | `integer` | Input table index; must match input order. |
| `originLabel` | no | `string<any>` | Input display label. |
| `preFilter` | no | `object` | Optional pre-stack filter per input. |
| `columnsMatch` | conditional | `list<string<column_name>>` | Required for `REMAP`; maps each input to output `selectedColumns`. |

## Mode Matrix (Observed)

| Mode | Core behavior | Required/typical companion fields |
| --- | --- | --- |
| `UNION` | Stack inputs by selected columns. | `selectedColumns`, `virtualInputs`. |
| `INTERSECT` | Keep intersected selected columns from inputs. | `selectedColumns`, `virtualInputs`. |
| `FROM_DATASET` | Use a dataset as schema source. | `copySchemaFromDatasetWithName`, `selectedColumns`, optional `addOriginColumn=true`. |
| `FROM_INDEX` | Use selected column indexes as schema projection. | `copySchemaFromDatasetWithName`, `selectedColumnsIndexes`, `selectedColumns`. |
| `REMAP` | Remap per-input source columns into unified output columns. | `selectedColumns`, `virtualInputs[i].columnsMatch`, `copySchemaFromDatasetWithName`. |
| `CUSTOM` | Custom selected output columns. | `selectedColumns`, `virtualInputs`. |

## Filter Integration

Vstack filters can be applied at two points:

1. Before stack on each input: `virtualInputs[i].preFilter`.
2. After stack on output rows: `postFilter`.

Filter block references:

- [Filter payload reference](../../sampling/references/filter_payload.md)
- [Visual conditions params](../../references/visual_conditions_params.md)

## Canonical Payload Examples

### UNION with two inputs

```json
{
  "mode": "UNION",
  "selectedColumns": ["id_a", "group_key", "value_num", "id_b"],
  "virtualInputs": [
    {"index": 0, "originLabel": "join_test_dataset_a", "preFilter": {"enabled": false, "distinct": false}},
    {"index": 1, "originLabel": "join_test_dataset_b", "preFilter": {"enabled": false, "distinct": false}}
  ],
  "postFilter": {"enabled": false, "distinct": false},
  "addOriginColumn": false,
  "originColumnName": "original_dataset"
}
```

### FROM_INDEX with schema source + selected indexes

```json
{
  "mode": "FROM_INDEX",
  "copySchemaFromDatasetWithName": "join_test_dataset_a",
  "selectedColumns": ["id_a", "group_key", "value_num"],
  "selectedColumnsIndexes": [0, 1, 2],
  "virtualInputs": [
    {"index": 0, "originLabel": "join_test_dataset_a_sf", "preFilter": {"distinct": true}},
    {"index": 1, "originLabel": "join_test_dataset_b_sf", "preFilter": {"enabled": true}},
    {"index": 2, "originLabel": "join_test_dataset_c_sf", "preFilter": {}}
  ],
  "postFilter": {"enabled": true, "distinct": true}
}
```

### REMAP with per-input column mapping

```json
{
  "mode": "REMAP",
  "copySchemaFromDatasetWithName": "join_test_dataset_a",
  "selectedColumns": ["id_new", "group_key_new", "value_num_new"],
  "virtualInputs": [
    {
      "index": 0,
      "originLabel": "join_test_dataset_a",
      "columnsMatch": ["id_a", "group_key", "value_num"],
      "preFilter": {"enabled": false, "distinct": false}
    },
    {
      "index": 1,
      "originLabel": "join_test_dataset_b",
      "columnsMatch": ["id_b", "group_key", "value_num"],
      "preFilter": {"enabled": false, "distinct": false}
    }
  ],
  "postFilter": {"enabled": false, "distinct": false},
  "addOriginColumn": false
}
```
