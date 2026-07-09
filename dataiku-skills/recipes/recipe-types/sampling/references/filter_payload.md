---
name: sampling-filter-payload-reference
description: "Filter payload reference for visual recipe filter sections (sampling and join included)."
---

# Filter Payload Reference

Use this reference for recipe payload filter sections (`get_recipe_settings` + `set_recipe_settings` action `set_payload`).

This shape is reusable across recipe types with compatible filter blocks (for example sampling payload filters and join pre/post filters).

## Payload Model

Typical filter payload fields:

- `enabled`: enable/disable filtering.
- `distinct`: optional distinct toggle.
- `uiData`: filter builder metadata (rules/formula/SQL modes).
- `expression`: formula or SQL expression for expression-based modes.
- `$status`: DSS translation/validation metadata (DSS-managed).

Envelope fields reference:

| Field | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `enabled` | yes | `boolean` | `true` \| `false` | Main filter toggle. |
| `distinct` | no | `boolean` | `true` \| `false` | Distinct filtering toggle. |
| `uiData` | conditional | `object` | See `uiData` matrix below | Usually present for rules mode and UI-edited payloads. |
| `expression` | conditional | `string<any>` | Formula/SQL expression | Required for `CUSTOM` or `SQL` modes. |
| `$status` | no | `object` | DSS-generated metadata | Preserve if present unless DSS regenerates it. |

### `uiData` Param Matrix

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `mode` | yes | `enum` | `&&` \| `\|\|` \| `CUSTOM` \| `SQL` | Filter mode selector. `&&`/`\|\|` are rules-mode combinators. |
| `$filterOptions` | yes | `enum` | `rules` \| `CUSTOM` \| `SQL` | UI mode option code. |
| `$latestOperator` | no | `enum` | Observed: `&&`, `\|\|` | Last selected boolean operator in UI. |
| `conditions` | no | `list<object>` | List of rule condition objects | Primarily used in rules mode. See shared condition schema. |

### Visual Conditions Reference
When `uiData.$filterOptions = "rules"`, always read [Visual conditions params](../../references/visual_conditions_params.md) to build `uiData.conditions[]`.

Use `operator` values exactly as listed there — copy the token verbatim, including spacing.

### `$status` Fields Observed

| Field | Domain | Allowed values | Notes |
| --- | --- | --- | --- |
| `validated` | `boolean` | `true` \| `false` | Validation status in observed payloads. |
| `ok` | `boolean` | `true` \| `false` | Translation validity flag. |
| `fullyTranslated` | `boolean` | `true` \| `false` | SQL/full translation availability. |
| `sql` | `string<any>` | Any SQL text | Present when DSS can produce SQL translation. |
| `message` | `string<any>` | Any text | Validation/translation message content. |

## Filter Mode Matrix

| Mode | Required payload fields | Notes |
| --- | --- | --- |
| Rules | `enabled=true`, `uiData.mode in {"&&","||"}`, `uiData.$filterOptions="rules"`, `uiData.conditions[]` | Preferred default when the filter can be expressed with visual conditions. UI rule-based filtering with AND/OR condition combinator. |
| Formula | `enabled=true`, `uiData.mode="CUSTOM"`, `uiData.$filterOptions="CUSTOM"`, `expression` | Formula expression filtering. |
| SQL | `enabled=true`, `uiData.mode="SQL"`, `uiData.$filterOptions="SQL"`, `expression` | SQL expression filtering. |
| Disabled | `enabled=false` | No row filtering. |

## Canonical Variants

### Disabled filter payload

```json
{
  "distinct": false,
  "enabled": false
}
```

### Rules-based filter payload

```json
{
  "uiData": {
    "mode": "&&",
    "$latestOperator": "&&",
    "$filterOptions": "rules",
    "conditions": [
      {
        "input": "status",
        "operator": "== [string]",
        "string": "active"
      }
    ]
  },
  "$status": {},
  "distinct": false,
  "enabled": true
}
```

### Rules-based numeric range payload

```json
{
  "uiData": {
    "mode": "&&",
    "$latestOperator": "&&",
    "$filterOptions": "rules",
    "conditions": [
      {
        "input": "age",
        "operator": ">< [number]",
        "num": 0,
        "num2": 120
      }
    ]
  },
  "$status": {},
  "distinct": false,
  "enabled": true
}
```

### Rules-based IN-list payload

```json
{
  "uiData": {
    "mode": "&&",
    "$latestOperator": "&&",
    "$filterOptions": "rules",
    "conditions": [
      {
        "input": "country",
        "operator": "in [string]",
        "items": [
          {"string": "US"},
          {"string": "GB"},
          {"string": "CA"}
        ]
      }
    ]
  },
  "$status": {},
  "distinct": false,
  "enabled": true
}
```

### Rules-based regex payload

```json
{
  "uiData": {
    "mode": "&&",
    "$latestOperator": "&&",
    "$filterOptions": "rules",
    "conditions": [
      {
        "input": "country",
        "operator": "regex",
        "string": "^U.*"
      }
    ]
  },
  "$status": {},
  "distinct": false,
  "enabled": true
}
```

### Rules-based OR (`||`) payload

```json
{
  "uiData": {
    "mode": "||",
    "$latestOperator": "||",
    "$filterOptions": "rules",
    "conditions": [
      {
        "input": "country",
        "operator": "== [string]",
        "string": "US"
      },
      {
        "input": "country",
        "operator": "== [string]",
        "string": "GB"
      }
    ]
  },
  "$status": {},
  "distinct": false,
  "enabled": true
}
```

### Formula/SQL-based filter payload

```json
{
  "uiData": {
    "mode": "CUSTOM",
    "$filterOptions": "CUSTOM"
  },
  "expression": "numval(\"score\") > 0",
  "$status": {},
  "distinct": false,
  "enabled": true
}
```

### SQL-based filter payload

```json
{
  "uiData": {
    "mode": "SQL",
    "$filterOptions": "SQL"
  },
  "expression": "score > 0 AND status = 'active'",
  "$status": {},
  "distinct": false,
  "enabled": true
}
```

## Filter Update Rule

1. Read current payload with `get_recipe_settings`.
2. Edit only filter-related fields (`enabled`, `uiData`, `expression`, `distinct`).
3. Prefer rules-mode payloads when the filter can be expressed with visual conditions.
4. Prefer full payload round-trip writes (`set_payload` with `merge=false`).
5. For narrow nested patches, use `merge=true, deep_merge=true`.
