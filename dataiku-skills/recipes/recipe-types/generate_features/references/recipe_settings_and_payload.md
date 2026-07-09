---
name: generate-features-recipe-settings-and-payload-reference
description: "Settings and payload reference for generate_features recipes, including relationships, virtual inputs, selected feature families, and time-window context."
---

# Generate Features Recipe Settings And Payload Reference

Use this reference for `generate_features` payload edits (`get_recipe_settings` + `set_recipe_settings` action `set_payload`).

## Observed Settings Shape

In these recipes:

- `payload` controls behavior.
- `params` is `null`.

Observed top-level payload keys:

- `relationships`
- `virtualInputs`
- `features`
- `cutoffTime`
- `engineParams`

## Payload Matrix

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `relationships` | no | `list<object>` | Inter-table relationship definitions (empty for single-input case). |
| `virtualInputs` | yes | `list<object>` | Per-input column selections and optional time-window config. |
| `features` | yes | `list<enum>` | Feature families to generate. |
| `cutoffTime` | no | `object` | Cutoff mode configuration (observed `{}` and `{ "mode": "COLUMN" }`). |
| `engineParams` | no | `object` | Engine/runtime settings; preserve unless explicitly changing execution behavior. |

## `relationships[]` Matrix (Observed)

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `table1` | yes | `integer` | Left table index (matches `virtualInputs[].index`). |
| `table2` | yes | `integer` | Right table index (matches `virtualInputs[].index`). |
| `type` | yes | `enum` | Observed: `ONE_TO_MANY`, `ONE_TO_ONE`, `MANY_TO_ONE`. |
| `on` | yes | `list<object>` | Join conditions between table columns. |

Observed `on[]` condition fields include:

- `column1` / `column2` (`name`, `table`)
- `type` (observed `EQ`)
- `dateDiffUnit`, `windowFrom`, `windowTo`
- `maxMatches`, `caseInsensitive`, `maxDistance`, `normalizeText`, `strict`

## `virtualInputs[]` Matrix (Observed)

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `index` | yes | `integer` | Input table index used by relationships/conditions. |
| `originLabel` | no | `string` | Input dataset label. |
| `selectedColumns` | yes | `list<object>` | Selected columns with variable typing metadata. |
| `outputColumnsSelectionMode` | optional | `enum` | Observed: `MANUAL` (omitted in one virtual input). |
| `timeIndexColumn` | optional | `string<column_name>` | Time column for windowed feature generation. |
| `timeWindows` | no | `list<object>` | Time windows for temporal features (can be empty). |

`selectedColumns[]` fields:

- `name`
- `variableType` (observed values include `NUMERIC`, `CATEGORY`, `DATE`)

`timeWindows[]` fields:

- `windowUnit` (observed: `YEAR`, `MONTH`)
- `from`
- `to`

## `features[]` Observed Values

Observed feature families include:

- `COUNT`, `AVG`, `MAX`, `MIN`, `SUM`, `DISTINCT`
- `DAY_OF_MONTH`, `DAY_OF_WEEK`, `MONTH_OF_YEAR`, `HOUR_OF_DAY`, `WEEK_OF_YEAR`, `YEAR`
- `CHARACTER_COUNT`, `WORD_COUNT`

## Canonical Payload Examples (Trimmed)

### Single-input baseline (no relationships)

```json
{
  "relationships": [],
  "features": [
    "COUNT",
    "AVG",
    "MAX",
    "MIN",
    "SUM",
    "DISTINCT"
  ],
  "cutoffTime": {},
  "virtualInputs": [
    {
      "index": 0,
      "originLabel": "customer_info_for_window",
      "outputColumnsSelectionMode": "MANUAL",
      "selectedColumns": [
        {"name": "id", "variableType": "NUMERIC"},
        {"name": "status", "variableType": "CATEGORY"},
        {"name": "date_of_birth", "variableType": "DATE"}
      ],
      "timeWindows": []
    }
  ]
}
```

### Two-input ONE_TO_MANY with two key conditions

```json
{
  "relationships": [
    {
      "table1": 0,
      "table2": 1,
      "type": "ONE_TO_MANY",
      "on": [
        {"column1": {"table": 0, "name": "id"}, "column2": {"table": 1, "name": "ID"}, "type": "EQ"},
        {"column1": {"table": 0, "name": "status"}, "column2": {"table": 1, "name": "STATUS"}, "type": "EQ"}
      ]
    }
  ],
  "cutoffTime": {"mode": "COLUMN"}
}
```

### Two-input with temporal windows

```json
{
  "relationships": [
    {"table1": 0, "table2": 1, "type": "ONE_TO_ONE"}
  ],
  "virtualInputs": [
    {
      "index": 0,
      "timeIndexColumn": "date_of_birth",
      "timeWindows": []
    },
    {
      "index": 1,
      "timeIndexColumn": "random_date",
      "timeWindows": [
        {"windowUnit": "YEAR", "from": 30, "to": 0}
      ]
    }
  ],
  "cutoffTime": {"mode": "COLUMN"}
}
```

## Recommended Update Pattern

1. Read current settings with `get_recipe_settings`.
2. Copy current payload.
3. Edit only intended blocks (`relationships`, `virtualInputs`, `features`, `cutoffTime`).
4. Write payload with `set_recipe_settings` action `set_payload`.
5. Re-read settings to confirm only intended keys changed.
