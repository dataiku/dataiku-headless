---
name: prepare-filter-on-value
description: "Observed JSON patterns for the FilterOnValue prepare/shaker processor."
---

# FilterOnValue Processor

Keep/remove/clear rows and cells whose selected column values match one or more specified values.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `appliesTo` | yes | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param. |
| `columns` | conditional | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param; required non-empty when `appliesTo` is `SINGLE_COLUMN` or `COLUMNS`. |
| `appliesToPattern` | conditional | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param; required when `appliesTo` is `PATTERN`. |
| `action` | yes | `enum` | `KEEP_ROW` \| `REMOVE_ROW` \| `CLEAR_CELL` \| `DONTCLEAR_CELL` | `KEEP_ROW`/`REMOVE_ROW`=change row count; `CLEAR_CELL`/`DONTCLEAR_CELL`=blank cells only. |
| `booleanMode` | no | `enum` | `AND` \| `OR` | Combines match checks across selected columns for row-level actions: `AND`=all match; `OR`=any matches. |
| `values` | yes | `list<string<any>>` | Any list of text values/patterns | Cell matches if matches one or more entries. `matchingMode` `PATTERN`=entries are regex. |
| `matchingMode` | no | `enum` | `FULL_STRING` \| `SUBSTRING` \| `PATTERN` | Match strategy: `FULL_STRING`=complete value; `SUBSTRING`; `PATTERN`=regex. |
| `normalizationMode` | no | `enum` | `EXACT` \| `LOWERCASE` \| `NORMALIZED` | `EXACT`=case-sensitive; `LOWERCASE`=ignore case; `NORMALIZED`=ignore accents (only valid with `FULL_STRING`). |
| `exclude` | no | `boolean` | `true` \| `false` | `true`=invert match. |
| `processNullOrEmptyValues` | no | `boolean` | `true` \| `false` | `true`=empty/null cells treated as `""` and may match. |

## Canonical Variants

### Remove rows matching a value (case-insensitive)

```json
{
  "type": "FilterOnValue",
  "params": {
    "columns": ["category"],
    "booleanMode": "AND",
    "normalizationMode": "LOWERCASE",
    "values": ["toys"],
    "matchingMode": "FULL_STRING",
    "appliesTo": "SINGLE_COLUMN",
    "action": "REMOVE_ROW",
    "exclude": false,
    "processNullOrEmptyValues": false
  }
}
```

### Keep only rows whose substring matches across multiple columns

```json
{
  "type": "FilterOnValue",
  "params": {
    "columns": ["category", "full_name"],
    "booleanMode": "OR",
    "normalizationMode": "EXACT",
    "values": ["book"],
    "matchingMode": "SUBSTRING",
    "appliesTo": "COLUMNS",
    "action": "KEEP_ROW",
    "exclude": false,
    "processNullOrEmptyValues": false
  }
}
```
