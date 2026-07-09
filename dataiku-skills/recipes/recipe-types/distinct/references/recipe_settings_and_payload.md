---
name: distinct-recipe-settings-and-payload-reference
description: "Settings and payload reference for distinct recipes, including dedup keys, filters, and optional count output."
---

# Distinct Recipe Settings And Payload Reference

Use this reference for `distinct` payload edits (`get_recipe_settings` + `set_recipe_settings` action `set_payload`).

## Observed Settings Shape

In these recipes:

- `payload` controls behavior.
- `params` is empty.

Observed top-level payload keys:

- `keys`
- `selectAllColumns`
- `globalCount`
- `preFilter`
- `postFilter`
- `outputColumnNameOverrides`
- `engineParams`

## Payload Matrix

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `keys` | yes | `list<object>` | Dedup keys. Observed shape: `[{ "column": "..." }]`. Primary dedup selector when `selectAllColumns=false`. |
| `selectAllColumns` | no | `boolean` | When `true`, deduplication is based on all columns (keys are retained in payload but not the primary selector). |
| `globalCount` | no | `boolean` | Adds `count` column when enabled. |
| `preFilter` | no | `object` | Optional filter before dedup. |
| `postFilter` | no | `object` | Optional filter after dedup. |
| `outputColumnNameOverrides` | no | `object<string,string>` | Optional output renames (empty in observed examples). |
| `engineParams` | no | `object` | Engine/runtime settings; preserve unless explicitly changing execution behavior. |

## `keys[]` Matrix

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `column` | yes | `string<column_name>` | Column used as dedup key. |

## `globalCount` Behavior (Observed)

| `globalCount` | Effect |
| --- | --- |
| `false` | Output contains only selected key columns (plus any derived/renamed outputs). |
| `true` | Output includes a `count` column with duplicate-group counts. |

## Filter Integration

Distinct filters can be applied at two points:

1. Before deduplication: `preFilter`.
2. After deduplication: `postFilter`.

Filter block references:

- [Filter payload reference](../../sampling/references/filter_payload.md)
- [Visual conditions params](../../references/visual_conditions_params.md)

## Canonical Payload Examples

### Distinct on selected key columns

```json
{
  "keys": [
    {"column": "ID"},
    {"column": "LOAN_PURPOSE"},
    {"column": "STATUS"},
    {"column": "DEBT_TO_INCOME_RATIO"},
    {"column": "HOME_OWNERSHIP"},
    {"column": "FICO_RANGE"},
    {"column": "OPEN_CREDIT_LINES"},
    {"column": "REVOLVING_CREDIT_BALANCE"},
    {"column": "INQUIRIES_IN_THE_LAST_6_MONTHS"}
  ],
  "selectAllColumns": false,
  "globalCount": false,
  "preFilter": {"enabled": false, "distinct": false},
  "postFilter": {"enabled": false, "distinct": false},
  "outputColumnNameOverrides": {}
}
```

### Distinct with duplicate count

```json
{
  "keys": [
    {"column": "ID"},
    {"column": "AMOUNT_REQUESTED"},
    {"column": "LOAN_PURPOSE"},
    {"column": "LOAN_LENGTH"},
    {"column": "STATUS"},
    {"column": "DEBT_TO_INCOME_RATIO"},
    {"column": "HOME_OWNERSHIP"},
    {"column": "FICO_RANGE"},
    {"column": "OPEN_CREDIT_LINES"},
    {"column": "REVOLVING_CREDIT_BALANCE"},
    {"column": "INQUIRIES_IN_THE_LAST_6_MONTHS"}
  ],
  "selectAllColumns": true,
  "globalCount": true,
  "preFilter": {"enabled": false, "distinct": false},
  "postFilter": {"enabled": false, "distinct": false},
  "outputColumnNameOverrides": {}
}
```

### Distinct with pre- and post-filters enabled

```json
{
  "keys": [
    {"column": "ID"},
    {"column": "AMOUNT_REQUESTED"},
    {"column": "LOAN_PURPOSE"},
    {"column": "LOAN_LENGTH"},
    {"column": "STATUS"},
    {"column": "REVOLVING_CREDIT_BALANCE"},
    {"column": "INQUIRIES_IN_THE_LAST_6_MONTHS"}
  ],
  "selectAllColumns": false,
  "globalCount": false,
  "preFilter": {"enabled": true, "distinct": false},
  "postFilter": {"enabled": true, "distinct": false}
}
```

## Recommended Update Pattern

1. Read current settings with `get_recipe_settings`.
2. Copy current payload.
3. Edit only intended blocks (`keys`, `selectAllColumns`, `globalCount`, filters).
4. Write payload with `set_recipe_settings` action `set_payload`.
5. Re-read settings to confirm only intended keys changed.
