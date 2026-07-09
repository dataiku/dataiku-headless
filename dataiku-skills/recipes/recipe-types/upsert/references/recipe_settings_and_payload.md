---
name: upsert-recipe-settings-and-payload-reference
description: "Settings and payload reference for upsert recipes, including key definitions, upsert modes, and optional filter/computed-column blocks."
---

# Upsert Recipe Settings And Payload Reference

Use this reference for `upsert` payload edits (`get_recipe_settings` + `set_recipe_settings` action `set_payload`).

## Observed Settings Shape

In these recipes:

- `payload` controls behavior.
- `params` is `null`.

Observed top-level payload keys:

- `upsertSQLMode`
- `upsertIndexMode`
- `keys`
- `preFilter`
- `computedColumns`
- `engineParams`

## Payload Matrix

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `upsertSQLMode` | yes | `enum` | Observed: `PREPARE_THEN_REPLACE`. |
| `upsertIndexMode` | yes | `enum` | Observed: `USE_EXISTING`. |
| `keys` | yes | `list<object>` | Upsert key definitions. |
| `preFilter` | no | `object` | Optional pre-upsert filter block. |
| `computedColumns` | no | `list<object>` | Computed columns available before upsert (including for key use). |
| `engineParams` | no | `object` | Engine/runtime settings; preserve unless explicitly changing execution behavior. |

## `keys[]` Matrix

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `column` | yes | `string<column_name>` | Match key column used by upsert. |

## `computedColumns[]` Matrix

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `mode` | yes | `enum` | `GREL` \| `SQL` | Expression engine. |
| `name` | yes | `string<column_name>` | Any valid output column name | Computed column name. |
| `expr` | yes | `string<any>` | Any formula/SQL expression | Computed column expression text. |
| `type` | yes | `string<meaning_or_storage_type>` | Any valid output type | Computed column type. |

## Filter Integration

Upsert filtering in observed recipes is pre-upsert:

1. Before upsert matching: `preFilter`.

Filter block references:

- [Filter payload reference](../../sampling/references/filter_payload.md)
- [Visual conditions params](../../references/visual_conditions_params.md)

## Canonical Payload Examples (Trimmed)

### Baseline upsert with existing index

```json
{
  "upsertSQLMode": "PREPARE_THEN_REPLACE",
  "upsertIndexMode": "USE_EXISTING",
  "keys": [
    {"column": "id"},
    {"column": "full_name"},
    {"column": "last_login"}
  ],
  "preFilter": {"enabled": false, "distinct": false},
  "computedColumns": []
}
```

### Upsert with prefilter and computed key column

```json
{
  "upsertSQLMode": "PREPARE_THEN_REPLACE",
  "upsertIndexMode": "USE_EXISTING",
  "keys": [
    {"column": "id"},
    {"column": "fake_scores_array"},
    {"column": "age_plus_10"}
  ],
  "preFilter": {"enabled": true, "distinct": true},
  "computedColumns": [
    {"mode": "GREL", "name": "age_plus_10", "expr": "age+10", "type": "double"}
  ]
}
```

## Recommended Update Pattern

1. Read current settings with `get_recipe_settings`.
2. Copy current payload.
3. Edit only intended blocks (`keys`, upsert modes, filter/computed columns).
4. Write payload with `set_recipe_settings` action `set_payload`.
5. Re-read settings to confirm only intended keys changed.
