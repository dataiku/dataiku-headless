---
name: topn-recipe-settings-and-payload-reference
description: "Settings and payload reference for topn recipes, including row-count controls, grouping keys, ordering, and optional ranking/filter/computed-column blocks."
---

# TopN Recipe Settings And Payload Reference

Use this reference for `topn` payload edits (`get_recipe_settings` + `set_recipe_settings` action `set_payload`).

## Observed Settings Shape

In these recipes:

- `payload` controls behavior.
- `params` is `null`.

Observed top-level payload keys:

- `preFilter`
- `retrievedColumnsSelectionMode`
- `firstRows`
- `lastRows`
- `duplicateCount`
- `keys`
- `orders`
- `retrievedColumns`
- `computedColumns`
- `rowNumber`
- `rank`
- `denseRank`
- `outputColumnNameOverrides`
- `engineParams`

## Payload Matrix

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `firstRows` | no | `integer>=0` | Number of top rows to keep. |
| `lastRows` | no | `integer>=0` | Number of bottom rows to keep. |
| `duplicateCount` | no | `boolean` | Tie handling toggle (observed with both first+last rows). |
| `keys` | no | `list<string<column_name>>` | Grouping keys. Empty list means global topn. |
| `orders` | yes | `list<object>` | Ordering definitions used to rank rows. |
| `retrievedColumnsSelectionMode` | no | `enum` | Observed: `ALL`, `EXPLICIT`. |
| `retrievedColumns` | yes | `list<string<column_name>>` | Output columns (all or explicit subset). |
| `rowNumber` | no | `boolean` | Add row-number output column. |
| `rank` | no | `boolean` | Add rank output column. |
| `denseRank` | no | `boolean` | Add dense-rank output column. |
| `preFilter` | no | `object` | Pre-topn filter block. |
| `computedColumns` | no | `list<object>` | Computed columns available for filtering/ranking/output. |
| `outputColumnNameOverrides` | no | `object<string,string>` | Optional output renames (empty in observed recipes). |
| `engineParams` | no | `object` | Engine/runtime settings; preserve unless explicitly changing execution behavior. |

## `orders[]` Matrix

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `column` | yes | `string<column_name>` | Ordering column. |
| `desc` | no | `boolean` | Descending when true, ascending when false. |

## `computedColumns[]` Matrix

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `mode` | yes | `enum` | `GREL` \| `SQL` | Expression engine. |
| `name` | yes | `string<column_name>` | Any valid output column name | Computed column name. |
| `expr` | yes | `string<any>` | Any formula/SQL expression | Computed column expression text. |
| `type` | yes | `string<meaning_or_storage_type>` | Any valid output type | Computed column type. |

## Output Behavior Notes

- Observed recipes use one output or two outputs.
- In one recipe, two outputs were present (`topn_3`, `topn_remaining_rows`), representing kept rows and remaining rows.

## Filter Integration

TopN filtering in observed recipes is pre-topn:

1. Before ranking/selection: `preFilter`.

Filter block references:

- [Filter payload reference](../../sampling/references/filter_payload.md)
- [Visual conditions params](../../references/visual_conditions_params.md)

## Canonical Payload Examples (Trimmed)

### Global top rows

```json
{
  "firstRows": 5,
  "lastRows": 0,
  "duplicateCount": false,
  "keys": [],
  "orders": [
    {"column": "interest_rate", "desc": true}
  ],
  "retrievedColumnsSelectionMode": "ALL",
  "rowNumber": false,
  "rank": false,
  "denseRank": false,
  "preFilter": {"enabled": false, "distinct": false}
}
```

### Per-group top and bottom rows with rank outputs

```json
{
  "firstRows": 10,
  "lastRows": 10,
  "duplicateCount": true,
  "keys": ["state"],
  "orders": [
    {"column": "monthly_income", "desc": true}
  ],
  "rowNumber": true,
  "rank": true,
  "denseRank": true,
  "retrievedColumnsSelectionMode": "ALL",
  "preFilter": {"enabled": false, "distinct": false}
}
```

### Explicit output columns with ascending order

```json
{
  "firstRows": 5,
  "lastRows": 0,
  "keys": [],
  "orders": [
    {"column": "monthly_income", "desc": false}
  ],
  "retrievedColumnsSelectionMode": "EXPLICIT",
  "retrievedColumns": [
    "id",
    "status",
    "date_of_birth",
    "monthly_income",
    "state",
    "interest_rate",
    "default"
  ],
  "rowNumber": false,
  "rank": false,
  "denseRank": false
}
```

### TopN with prefilter and computed column

```json
{
  "firstRows": 10,
  "lastRows": 0,
  "orders": [
    {"column": "interest_rate", "desc": true}
  ],
  "preFilter": {"enabled": true, "distinct": false},
  "computedColumns": [
    {"mode": "GREL", "name": "interest_rate_plus_5", "expr": "interest_rate+5", "type": "double"}
  ],
  "retrievedColumnsSelectionMode": "ALL"
}
```

## Recommended Update Pattern

1. Read current settings with `get_recipe_settings`.
2. Copy current payload.
3. Edit only intended blocks (`firstRows/lastRows`, `keys`, `orders`, rank flags, filter/computed columns).
4. Write payload with `set_recipe_settings` action `set_payload`.
5. Re-read settings to confirm only intended keys changed.
