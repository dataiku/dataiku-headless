---
name: pivot-recipe-settings-and-payload-reference
description: "Settings and payload reference for pivot recipes, including pivot key/value blocks, value limits, identifiers, and aggregate columns."
---

# Pivot Recipe Settings And Payload Reference

Use this reference for `pivot` payload edits (`get_recipe_settings` + `set_recipe_settings` action `set_payload`).

## Observed Settings Shape

In these recipes:

- `payload` controls behavior.
- `params` is empty.

Observed top-level payload keys:

- `pivots`
- `identifierColumnsSelection`
- `explicitIdentifiers`
- `otherColumns`
- `computedColumns`
- `preFilter`
- `schemaComputation`
- `modalitySlugification`
- `$withModalityMaxLength`
- `modalityMaxLength`
- `sortModalities`
- `customAggregates`
- `engineParams`
- `enginesPreferences`

## Payload Matrix

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `pivots` | yes | `list<object>` | Pivot definitions (keys, values, modality limits). |
| `identifierColumnsSelection` | no | `enum` | Observed values: `EXPLICIT`, `ALL_BUT_USED`. |
| `explicitIdentifiers` | no | `list<string<column_name>>` | Explicit identifier columns (used with `EXPLICIT`). |
| `otherColumns` | no | `list<object>` | Aggregates outside pivoted modality columns. |
| `computedColumns` | no | `list<object>` | Computed columns available before pivot processing. |
| `preFilter` | no | `object` | Filter before pivot computation. |
| `schemaComputation` | no | `enum` | Observed values: `ONLY_IF_NO_METADATA`, `ALWAYS`. |
| `modalitySlugification` | no | `enum` | Observed values: `NONE`, `SOFT_SLUGIFY`. |
| `$withModalityMaxLength` | no | `boolean` | Enables modality output-name max length handling. |
| `modalityMaxLength` | conditional | `integer` | Observed value: `100` when max length handling is enabled. |
| `sortModalities` | no | `boolean` | Sort pivot modalities toggle. |
| `customAggregates` | no | `list<object>` | Custom aggregates block (empty in observed recipes). |
| `engineParams` | no | `object` | Engine/runtime settings; preserve unless explicitly changing execution behavior. |
| `enginesPreferences` | no | `object` | Engine preference overrides (empty in observed recipes). |

## `pivots[]` Matrix

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `keyColumns` | yes | `list<string<column_name>>` | Columns used as pivot dimensions/modalities. |
| `valueColumns` | no | `list<object>` | Aggregates to compute per modality. |
| `valueLimit` | yes | `enum` | Observed values: `NO_LIMIT`, `TOP_N`, `AT_LEAST_N_OCC`, `EXPLICIT`. |
| `globalCount` | no | `boolean` | Add count per pivot cell when enabled. |
| `topnLimit` | conditional | `integer` | Used with `valueLimit=TOP_N`. |
| `minOccLimit` | conditional | `integer` | Used with `valueLimit=AT_LEAST_N_OCC`. |
| `explicitValues` | conditional | `list<list<string>>` | Explicit modality values when `valueLimit=EXPLICIT`. |

## `pivots[].valueColumns[]` Matrix

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `column` | yes | `string<column_name>` | Source column for aggregation. |
| `type` | yes | `string<meaning_or_storage_type>` | Output type hint. |
| `$agg` | yes | `enum` | Observed examples: `count`, `countDistinct`, `avg`, `min`, `max`, `sum`, `stddev`, `concat`, `first`, `last`. |
| Aggregate flags (`count`, `countDistinct`, `avg`, `min`, `max`, `sum`, `stddev`, `concat`, `first`, `last`) | conditional | `boolean` | Boolean flags associated with selected aggregation. |
| `concatDistinct` | conditional | `boolean` | Distinct concat behavior. |
| `concatSeparator` | conditional | `string` | Delimiter for concat outputs. |
| `orderColumn` | conditional | `string<column_name>` | Ordering column for first/last variants. |
| `firstLastNotNull` | conditional | `boolean` | First/last null-handling option. |

## `otherColumns[]` Matrix

`otherColumns[]` applies non-pivot aggregates retained in output.

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `column` | yes | `string<column_name>` | Source column. |
| `type` | yes | `string<meaning_or_storage_type>` | Output type hint. |
| Aggregate flags (`count`, `countDistinct`, `avg`, `min`, `max`, `sum`, `stddev`, `concat`, `first`, `last`) | conditional | `boolean` | Selected non-pivot aggregate flags. |
| `orderColumn` | conditional | `string<column_name>` | For order-sensitive first/last aggregates. |
| `concatSeparator` | conditional | `string` | Delimiter for concat outputs. |

## `computedColumns[]` Matrix

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `mode` | yes | `enum` | `GREL` \| `SQL` | Expression engine. |
| `name` | yes | `string<column_name>` | Any valid output column name | Computed column name. |
| `expr` | yes | `string<any>` | Any formula/SQL expression | Computed column expression text. |
| `type` | yes | `string<meaning_or_storage_type>` | Any valid output type | Computed column type. |

## Filter Integration

Pivot filtering in observed recipes is pre-pivot:

1. Before pivot computation: `preFilter`.

Filter block references:

- [Filter payload reference](../../sampling/references/filter_payload.md)
- [Visual conditions params](../../references/visual_conditions_params.md)

## Canonical Payload Examples (Trimmed)

### Basic pivot with average and global count

```json
{
  "identifierColumnsSelection": "EXPLICIT",
  "explicitIdentifiers": ["id"],
  "pivots": [
    {
      "valueLimit": "NO_LIMIT",
      "globalCount": true,
      "keyColumns": ["status", "state"],
      "valueColumns": [
        {"column": "interest_rate", "$agg": "avg", "avg": true, "type": "double"}
      ]
    }
  ]
}
```

### Pivot with multiple value aggregates and otherColumns

```json
{
  "identifierColumnsSelection": "EXPLICIT",
  "explicitIdentifiers": ["id"],
  "schemaComputation": "ALWAYS",
  "modalitySlugification": "SOFT_SLUGIFY",
  "$withModalityMaxLength": true,
  "modalityMaxLength": 100,
  "otherColumns": [
    {"column": "monthly_income", "avg": true, "type": "double"},
    {"column": "default", "count": true, "countDistinct": true, "sum": true, "avg": true, "min": true, "max": true, "stddev": true, "concat": true, "first": true, "last": true, "orderColumn": "id", "concatSeparator": ",", "type": "double"}
  ],
  "pivots": [
    {
      "valueLimit": "TOP_N",
      "topnLimit": 20,
      "globalCount": false,
      "keyColumns": ["status"],
      "valueColumns": [
        {"column": "monthly_income", "$agg": "count", "count": true, "type": "double"},
        {"column": "default", "$agg": "min", "min": true, "type": "double"},
        {"column": "state", "$agg": "countDistinct", "countDistinct": true, "type": "string"}
      ]
    }
  ]
}
```

### Pivot with prefilter and computed column

```json
{
  "identifierColumnsSelection": "ALL_BUT_USED",
  "explicitIdentifiers": [],
  "preFilter": {"enabled": true, "distinct": true},
  "computedColumns": [
    {"mode": "GREL", "name": "monthly_income_plus_10k", "expr": "monthly_income+10000", "type": "double"}
  ],
  "pivots": [
    {
      "valueLimit": "AT_LEAST_N_OCC",
      "minOccLimit": 5,
      "globalCount": true,
      "keyColumns": ["state"],
      "valueColumns": []
    }
  ]
}
```

### Pivot with explicit modality list

```json
{
  "identifierColumnsSelection": "EXPLICIT",
  "explicitIdentifiers": ["id"],
  "pivots": [
    {
      "valueLimit": "EXPLICIT",
      "globalCount": true,
      "keyColumns": ["state"],
      "explicitValues": [["MA"], ["CA"], ["NY"]],
      "valueColumns": []
    }
  ]
}
```

## Recommended Update Pattern

1. Read current settings with `get_recipe_settings`.
2. Copy current payload.
3. Edit only intended blocks (`pivots`, identifier settings, other columns, computed columns, prefilter).
4. Write payload with `set_recipe_settings` action `set_payload`.
5. Re-read settings to confirm only intended keys changed.
