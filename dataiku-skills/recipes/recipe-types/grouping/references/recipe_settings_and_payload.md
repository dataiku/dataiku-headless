---
name: grouping-recipe-settings-and-payload-reference
description: "Settings and payload reference for grouping recipes, including keys, aggregation values, filters, and custom aggregate expressions."
---

# Grouping Recipe Settings And Payload Reference

Use this reference for `grouping` payload edits (`get_recipe_settings` + `set_recipe_settings` action `set_payload`).

## Payload Model

A grouping recipe payload is usually composed of these blocks:

- `keys`: group-by dimensions.
- `values`: aggregation definitions over input columns (or custom expressions).
- `globalCount`: include total row count per group.
- `computedColumns`: optional computed columns available before aggregation.
- `preFilter`: filter before grouping.
- `postFilter`: filter after grouping.
- `outputColumnNameOverrides`: optional output-column rename map.
- `engineParams` and `engineType`: execution/runtime settings.

Top-level payload matrix:

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `keys` | yes | `list<object>` | Grouping dimension definitions. |
| `values` | yes | `list<object>` | Aggregation metric definitions. |
| `globalCount` | no | `boolean` | Adds a count column when enabled. |
| `computedColumns` | no | `list<object>` | Computed columns created before aggregation. |
| `preFilter` | no | `object` | Filter block applied before grouping. |
| `postFilter` | no | `object` | Filter block applied after grouping. |
| `outputColumnNameOverrides` | no | `object<string,string>` | Optional output column renames. |
| `engineParams` | no | `object` | Engine/runtime settings; preserve unless intentionally changing behavior. |
| `engineType` | no | `string` | Optional engine selector (for example `DSS`). |
| `selectAllColumns` | no | `boolean` | DSS-controlled selection behavior flag. |
| `enlargeYourBits` | no | `boolean` | DSS-controlled numeric precision behavior flag. |

## `keys[]` Matrix

`keys[]` entries represent group-by columns. In observed payloads, they include metric flags as booleans but those flags remain disabled for keys.

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `column` | yes | `string<column_name>` | Input column used as a grouping key. |
| `type` | yes | `string<meaning_or_storage_type>` | Key output type. |
| `$idx` | no | `integer` | DSS UI/index metadata. |
| `$selected` | no | `boolean` | DSS UI metadata. |
| Metric flags (`count`, `sum`, `avg`, `min`, `max`, `median`, `stddev`, `first`, `last`, `concat`, `concatDistinct`, `countDistinct`, `sum2`, `firstLastNotNull`) | no | `boolean` | Keep disabled in `keys[]`. |

## `values[]` Matrix

`values[]` entries define aggregation metrics. A value can be column-based (using `column`) or custom-expression-based (using `customExpr` + `customName`).

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `column` | conditional | `string<column_name>` | Required for column-based aggregations. |
| `type` | yes | `string<meaning_or_storage_type>` | Output type for the aggregate column. |
| `$idx` | no | `integer` | DSS UI/index metadata. |
| `$selected` | no | `boolean` | DSS UI metadata. |
| Aggregation flags (`count`, `countDistinct`, `sum`, `sum2`, `avg`, `min`, `max`, `median`, `stddev`, `first`, `last`, `firstLastNotNull`, `concat`, `concatDistinct`) | conditional | `boolean` | Enable one or more for selected column-based metrics. |
| `orderColumn` | conditional | `string<column_name>` | Required for deterministic `first`/`last`/`firstLastNotNull`. |
| `customExpr` | conditional | `string<any>` | Custom aggregate expression when not using a direct source `column`. |
| `customName` | conditional | `string<column_name>` | Output column name for `customExpr`. |

## `computedColumns[]` Matrix

Use computed columns when the aggregation should be based on derived values.

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `mode` | yes | `enum` | `GREL` \| `SQL` | Expression engine. Prefer `enum`. |
| `name` | yes | `string<column_name>` | Any valid output column name | Computed column name. |
| `expr` | yes | `string<any>` | Any formula/SQL expression | Computed column expression. |
| `type` | yes | `string<meaning_or_storage_type>` | Any valid output type | Computed column type. |

## Filter Integration

Grouping filters can be applied at two points:

1. Before aggregation: `preFilter`.
2. After aggregation: `postFilter`.

Filter block references:

- [Filter payload reference](../../sampling/references/filter_payload.md)
- [Visual conditions params](../../references/visual_conditions_params.md)

## Output Naming Notes

Default output column names typically follow `<source_column>_<agg>` naming (for example `amount_sum`, `amount_avg`), plus `count` when `globalCount=true`.

When custom naming is needed:

- use `customName` for custom expression metrics;
- or set explicit mappings in `outputColumnNameOverrides`.

## Canonical Payload Examples

### Single key with average and global count

```json
{
  "keys": [
    {"column": "country", "type": "string", "count": false, "sum": false, "avg": false}
  ],
  "values": [
    {"column": "age", "type": "double", "avg": true, "count": false, "sum": false}
  ],
  "globalCount": true,
  "computedColumns": [],
  "preFilter": {"distinct": false, "enabled": false},
  "postFilter": {"distinct": false, "enabled": false},
  "outputColumnNameOverrides": {}
}
```

### Multi-aggregation with deterministic first/last

```json
{
  "keys": [
    {"column": "status", "type": "string"},
    {"column": "age_band", "type": "string"}
  ],
  "values": [
    {"column": "signup_date", "type": "dateonly", "first": true, "last": true, "orderColumn": "id"},
    {
      "column": "event_count",
      "type": "double",
      "count": true,
      "countDistinct": true,
      "sum": true,
      "avg": true,
      "min": true,
      "max": true,
      "median": true,
      "stddev": true
    }
  ],
  "globalCount": true
}
```

### Computed column plus custom aggregate expression

```json
{
  "keys": [
    {"column": "country", "type": "string"}
  ],
  "computedColumns": [
    {"mode": "GREL", "name": "email_len", "expr": "length(email)", "type": "int"}
  ],
  "values": [
    {"column": "email_len", "type": "int", "min": true},
    {"customExpr": "min('score')", "customName": "custom_aggr", "type": "DOUBLE"}
  ],
  "globalCount": true
}
```
