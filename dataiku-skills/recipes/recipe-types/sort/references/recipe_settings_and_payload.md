---
name: sort-recipe-settings-and-payload-reference
description: "Settings and payload reference for sort recipes, including ordering keys, ranking flags, and optional prefilter/computed columns."
---

# Sort Recipe Settings And Payload Reference

Use this reference for `sort` payload edits (`get_recipe_settings` + `set_recipe_settings` action `set_payload`).

## Observed Settings Shape

In these recipes:

- `payload` controls behavior.
- `params` is empty.

Observed top-level payload keys:

- `orders`
- `rowNumber`
- `rank`
- `denseRank`
- `preFilter`
- `computedColumns`
- `outputColumnNameOverrides`
- `engineParams`

## Order Preservation for Certain Dataset Backends

Some output dataset backends (for example SQL-backed outputs) may not preserve the write order produced by Sort.

Practical handling:

- treat sort ordering as guaranteed only when output storage preserves order;
- recommend using an ouput storage option that preserves order (e.g. server filesystem, S3, Google Cloud Storage, Azure Blob Storage, HDFS);
- if downstream steps need a persisted ordering key, enable `rowNumber=true` and use that column as read-order key downstream.

## Payload Matrix

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `orders` | yes | `list<object>` | Sort key definitions and direction. |
| `rowNumber` | no | `boolean` | Add row number column. |
| `rank` | no | `boolean` | Add rank column. |
| `denseRank` | no | `boolean` | Add dense-rank column. |
| `preFilter` | no | `object` | Filter applied before sorting. |
| `computedColumns` | no | `list<object>` | Computed columns available before sorting/filtering. |
| `outputColumnNameOverrides` | no | `object<string,string>` | Optional output renames (empty in observed recipes). |
| `engineParams` | no | `object` | Engine/runtime settings; preserve unless explicitly changing execution behavior. |

## `orders[]` Matrix

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `column` | yes | `string<column_name>` | Column used for sorting. |
| `desc` | no | `boolean` | Descending sort when true, ascending when false. |

## `computedColumns[]` Matrix

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `mode` | yes | `enum` | `GREL` \| `SQL` | Expression engine. |
| `name` | yes | `string<column_name>` | Any valid output column name | Computed column name. |
| `expr` | yes | `string<any>` | Any formula/SQL expression | Computed column expression text. |
| `type` | yes | `string<meaning_or_storage_type>` | Any valid output type | Computed column type. |

## Filter Integration

Sort filtering in observed recipes is pre-sort:

1. Before sorting: `preFilter`.

Filter block references:

- [Filter payload reference](../../sampling/references/filter_payload.md)
- [Visual conditions params](../../references/visual_conditions_params.md)

## Canonical Payload Examples (Trimmed)

### Basic descending sort

```json
{
  "orders": [
    {"column": "id", "desc": true}
  ],
  "rowNumber": false,
  "rank": false,
  "denseRank": false,
  "preFilter": {"enabled": false, "distinct": false}
}
```

### Multi-key sort with ranking columns

```json
{
  "orders": [
    {"column": "state", "desc": false},
    {"column": "interest_rate", "desc": false}
  ],
  "rowNumber": true,
  "rank": true,
  "denseRank": true,
  "preFilter": {"enabled": false, "distinct": false}
}
```

### Sort with row number as persisted ordering key

```json
{
  "orders": [
    {"column": "interest_rate", "desc": false}
  ],
  "rowNumber": true,
  "rank": false,
  "denseRank": false,
  "preFilter": {"enabled": false, "distinct": false}
}
```

### Sort with prefilter and computed column

```json
{
  "orders": [
    {"column": "interest_rate", "desc": false}
  ],
  "preFilter": {"enabled": true, "distinct": true},
  "computedColumns": [
    {"mode": "GREL", "name": "monthly_income_plus_2", "expr": "monthly_income+2", "type": "double"}
  ],
  "rowNumber": false,
  "rank": false,
  "denseRank": false
}
```

## Recommended Update Pattern

1. Read current settings with `get_recipe_settings`.
2. Copy current payload.
3. Edit only intended blocks (`orders`, ranking flags, prefilter, computed columns).
4. Write payload with `set_recipe_settings` action `set_payload`.
5. Re-read settings to confirm only intended keys changed.
