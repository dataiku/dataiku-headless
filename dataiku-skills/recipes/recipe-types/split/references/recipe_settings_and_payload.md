---
name: split-recipe-settings-and-payload-reference
description: "Settings and payload reference for split recipes, including mode-specific split definitions and fallback output behavior."
---

# Split Recipe Settings And Payload Reference

Use this reference for `split` payload edits (`get_recipe_settings` + `set_recipe_settings` action `set_payload`).

## Observed Settings Shape

In these recipes:

- `payload` controls behavior.
- `params` is empty.

Observed top-level payload keys:

- `mode`
- `defaultOutputIndex`
- split blocks: `valueSplits`, `rangeSplits`, `randomSplits`, `randomColumns`, `randomColumnsSplits`, `filterSplits`, `centileOrders`, `centileSplits`
- `preFilter`
- `computedColumns`
- `writeComputedColumnsInOutput`
- `seed`
- `engineParams`
- optional: `engineType`, `rangeSetTime`, `centileShuffle`, `centileTDigest`

## Payload Matrix

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `mode` | yes | `enum` | Observed values: `VALUES`, `RANGE`, `RANDOM`, `RANDOM_COLUMNS`, `FILTERS`, `CENTILE`. |
| `defaultOutputIndex` | yes | `integer` | Fallback output index for unmatched rows. |
| `preFilter` | no | `object` | Filter before split dispatch. |
| `computedColumns` | no | `list<object>` | Computed columns available before split filters/conditions. |
| `writeComputedColumnsInOutput` | no | `boolean` | Whether computed columns are written to outputs. |
| `column` | conditional | `string<column_name>` | **Required when `mode` is `VALUES`** — names the dispatch column. Builds fail without it. |
| `seed` | no | `integer` | Random seed for random/centile-related modes. |
| `engineParams` | no | `object` | Engine/runtime settings; preserve unless explicitly changing execution behavior. |
| `engineType` | no | `string` | Optional engine selector (observed: `DSS` in one recipe). |
| `rangeSetTime` | no | `boolean` | Range-mode date/time behavior flag. |
| `centileShuffle` | no | `boolean` | Centile mode shuffle flag. |
| `centileTDigest` | no | `boolean` | Centile mode TDigest flag. |

## Mode-Specific Blocks

| Mode | Active block(s) | Notes |
| --- | --- | --- |
| `VALUES` | `valueSplits` + top-level `column` | Split by exact values in selected `column`. **Requires a top-level `"column"` key** naming the dispatch column — builds will fail without it. |
| `RANGE` | `rangeSplits` | Split by numeric/date range filters. |
| `RANDOM` | `randomSplits` | Random split by shares. |
| `RANDOM_COLUMNS` | `randomColumns`, `randomColumnsSplits` | Random split by column-based grouping and shares. |
| `FILTERS` | `filterSplits` | Split by explicit filter rules per output. |
| `CENTILE` | `centileOrders`, `centileSplits` | Split by centile order + shares. |

## Split Entry Matrices

### `valueSplits[]`

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `outputIndex` | yes | `integer` | Output dataset index. |
| `value` | yes | `string<any>` | Match value for dispatch. |
| `caseSensitive` | no | `boolean` | Case-sensitive matching toggle. |

### `rangeSplits[]`

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `outputIndex` | yes | `integer` | Output dataset index. |
| `filter` | yes | `object` | Range filter block. |

### `randomSplits[]`, `randomColumnsSplits[]`, `centileSplits[]`

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `outputIndex` | yes | `integer` | Output dataset index. |
| `share` | yes | `number` | Share/percentage allocation for output. |

### `filterSplits[]`

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `outputIndex` | yes | `integer` | Output dataset index. |
| `filter` | yes | `object` | Filter block for that split output. |

### `centileOrders[]`

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `column` | yes | `string<column_name>` | Column used for centile ordering. |
| `desc` | no | `boolean` | Descending order when true. |

## `computedColumns[]` Matrix

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `mode` | yes | `enum` | `GREL` \| `SQL` | Expression engine. |
| `name` | yes | `string<column_name>` | Any valid output column name | Computed column name. |
| `expr` | yes | `string<any>` | Any formula/SQL expression | Computed column expression text. |
| `type` | yes | `string<meaning_or_storage_type>` | Any valid output type | Computed column type. |

## Filter Integration

Split filters can be applied at multiple points:

1. Before split dispatch: `preFilter`.
2. Within mode-specific split entries: `rangeSplits[].filter`, `filterSplits[].filter`.

Filter block references:

- [Filter payload reference](../../sampling/references/filter_payload.md)
- [Visual conditions params](../../references/visual_conditions_params.md)

## Canonical Payload Examples (Trimmed)

### Values split

> **Required**: include a top-level `"column"` key naming the dispatch column.

```json
{
  "mode": "VALUES",
  "column": "status",
  "defaultOutputIndex": 1,
  "valueSplits": [
    {"outputIndex": 0, "value": "accepted", "caseSensitive": false},
    {"outputIndex": 1, "value": "rejected", "caseSensitive": false}
  ],
  "preFilter": {"enabled": false, "distinct": false}
}
```

### Random split with explicit fallback to a third output dataset

```json
{
  "mode": "RANDOM",
  "defaultOutputIndex": 2,
  "seed": 1337,
  "randomSplits": [
    {"outputIndex": 0, "share": 80},
    {"outputIndex": 1, "share": 10}
  ],
  "preFilter": {"enabled": false, "distinct": false}
}
```

### Filters split with computed column

```json
{
  "mode": "FILTERS",
  "defaultOutputIndex": 1,
  "computedColumns": [
    {"mode": "GREL", "name": "interest_rate_plus_2", "expr": "interest_rate+2", "type": "double"}
  ],
  "writeComputedColumnsInOutput": false,
  "preFilter": {"enabled": true, "distinct": true},
  "filterSplits": [
    {"outputIndex": 0, "filter": {"enabled": true, "distinct": false}}
  ]
}
```

### Centile split

```json
{
  "mode": "CENTILE",
  "defaultOutputIndex": 1,
  "centileOrders": [{"column": "interest_rate", "desc": false}],
  "centileSplits": [{"outputIndex": 0, "share": 50}],
  "centileShuffle": false,
  "centileTDigest": false
}
```

## Recommended Update Pattern

1. Read current settings with `get_recipe_settings`.
2. Copy current payload.
3. Edit only intended blocks (`mode`, active mode split arrays, `defaultOutputIndex`, filters, computed columns).
4. Write payload with `set_recipe_settings` action `set_payload`.
5. Re-read settings to confirm only intended keys changed.
