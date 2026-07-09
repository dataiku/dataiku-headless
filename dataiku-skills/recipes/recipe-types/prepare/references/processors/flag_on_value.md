---
name: prepare-flag-on-value
description: "Observed JSON patterns for the FlagOnValue prepare/shaker processor."
---

# FlagOnValue Processor

Flag rows from a dataset that contain specific values by creating a column containing `1` for all matching (in-range) rows. Unmatched rows are left empty.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `normalizationMode` | yes | `enum` | `EXACT` \| `LOWERCASE` \| `NORMALIZED` | `LOWERCASE` enables case-insensitive behavior; `NORMALIZED` appeared in pattern-scoped matching. |
| `booleanMode` | yes | `enum` | `AND` \| `OR` | Combines multiple conditions. |
| `columns` | yes | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param. |
| `values` | yes | `list<string<any>>` | Any text values/patterns | When `matchingMode = PATTERN`, values are treated as regex-like patterns. |
| `matchingMode` | yes | `enum` | `FULL_STRING` \| `SUBSTRING` \| `PATTERN` | Match strategy. |
| `action` | yes | `enum` | `FLAG` | Output behavior is flag-only in observed payloads. |
| `appliesTo` | yes | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param. |
| `appliesToPattern` | conditional | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param; required when `appliesTo` is `PATTERN`. |
| `exclude` | yes | `boolean` | `true` \| `false` | Inverts match logic when `true` (flag non-matches). |
| `flagColumn` | yes | `string<column_name>` | Any valid output column name | Column created/updated by this step. |
| `processNullOrEmptyValues` | yes | `boolean` | `true` \| `false` | Whether null/empty values participate in match evaluation. |

## Canonical Variants

### Full-string equality on one column

```json
{
  "type": "FlagOnValue",
  "params": {
    "normalizationMode": "EXACT",
    "booleanMode": "AND",
    "columns": ["event_code"],
    "values": ["abc123"],
    "matchingMode": "FULL_STRING",
    "action": "FLAG",
    "appliesTo": "SINGLE_COLUMN",
    "exclude": false,
    "flagColumn": "event_code_is_abc123",
    "processNullOrEmptyValues": false
  }
}
```

### Regex/pattern match on one column

```json
{
  "type": "FlagOnValue",
  "params": {
    "normalizationMode": "EXACT",
    "booleanMode": "AND",
    "columns": ["session_id"],
    "values": ["800$"],
    "matchingMode": "PATTERN",
    "action": "FLAG",
    "appliesTo": "SINGLE_COLUMN",
    "exclude": false,
    "flagColumn": "session_id_ends_800",
    "processNullOrEmptyValues": false
  }
}
```

### Substring match requiring multiple columns

```json
{
  "type": "FlagOnValue",
  "params": {
    "normalizationMode": "EXACT",
    "booleanMode": "AND",
    "columns": ["id", "age"],
    "values": [".0"],
    "matchingMode": "SUBSTRING",
    "action": "FLAG",
    "appliesTo": "COLUMNS",
    "exclude": false,
    "flagColumn": "id_and_age_contain_dot_zero",
    "processNullOrEmptyValues": false
  }
}
```

### Any-column scan with OR logic

```json
{
  "type": "FlagOnValue",
  "params": {
    "normalizationMode": "EXACT",
    "booleanMode": "OR",
    "columns": [],
    "values": ["2024"],
    "matchingMode": "SUBSTRING",
    "action": "FLAG",
    "appliesTo": "ALL",
    "exclude": false,
    "flagColumn": "any_col_contains_2024",
    "processNullOrEmptyValues": false
  }
}
```

### Column-name pattern scope

```json
{
  "type": "FlagOnValue",
  "params": {
    "normalizationMode": "NORMALIZED",
    "booleanMode": "OR",
    "columns": [],
    "values": ["2022"],
    "matchingMode": "SUBSTRING",
    "action": "FLAG",
    "appliesTo": "PATTERN",
    "appliesToPattern": ".*date.*",
    "exclude": false,
    "flagColumn": "any_date_cols_contain_2022",
    "processNullOrEmptyValues": false
  }
}
```

## Update Guidance

1. Read existing payload first and keep unrelated top-level keys untouched.
2. Modify only target `steps[]` entries for `FlagOnValue`.
3. Preserve `metaType`, `preview`, and `disabled` unless the change explicitly targets those behaviors.
4. If toggling `appliesTo` to `ALL`, set `columns` to `[]` to match observed payload behavior.
