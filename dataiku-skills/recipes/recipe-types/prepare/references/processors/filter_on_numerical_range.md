---
name: prepare-filter-on-numerical-range
description: "Observed JSON patterns for the FilterOnNumericalRange prepare/shaker processor."
---

# FilterOnNumericalRange Processor

Filter rows that contain numbers within a numerical range. Alternatively, this processor can clear content from matching cells instead of filtering entire rows.

The boundaries of the numerical range are inclusive. A value is considered out of range if it isn't a valid numerical value.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `appliesTo` | yes | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param. |
| `columns` | yes | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param. |
| `appliesToPattern` | conditional | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param; required when `appliesTo` is `PATTERN`. |
| `action` | yes | `enum` | `KEEP_ROW` \| `REMOVE_ROW` \| `CLEAR_CELL` \| `DONTCLEAR_CELL` | Action to apply when values are in range. |
| `booleanMode` | yes | `enum` | `AND` \| `OR` | Combines match checks across selected columns. |
| `min` | yes | `number` | Any numeric value | Inclusive lower boundary of the numerical range. |
| `max` | yes | `number` | Any numeric value | Inclusive upper boundary of the numerical range. |
| `includeEmptyValues` | yes | `boolean` | `true` \| `false` | Whether empty values participate in range evaluation. |

## Canonical Variants

### Keep rows where values are in range

```json
{
  "type": "FilterOnNumericalRange",
  "params": {
    "action": "KEEP_ROW",
    "appliesTo": "SINGLE_COLUMN",
    "booleanMode": "AND",
    "columns": ["age"],
    "min": 1.0,
    "max": 100.0,
    "includeEmptyValues": false
  }
}
```

### Remove rows where values are in range

```json
{
  "type": "FilterOnNumericalRange",
  "params": {
    "action": "REMOVE_ROW",
    "appliesTo": "COLUMNS",
    "booleanMode": "OR",
    "columns": ["age", "score"],
    "min": 5.0,
    "max": 6.0,
    "includeEmptyValues": false
  }
}
```

### Clear matching cells in range

```json
{
  "type": "FilterOnNumericalRange",
  "params": {
    "action": "CLEAR_CELL",
    "appliesTo": "COLUMNS",
    "booleanMode": "AND",
    "columns": ["age", "score"],
    "min": 10.0,
    "max": 20.0,
    "includeEmptyValues": false
  }
}
```

### Clear cells outside range

```json
{
  "type": "FilterOnNumericalRange",
  "params": {
    "action": "DONTCLEAR_CELL",
    "appliesTo": "SINGLE_COLUMN",
    "booleanMode": "OR",
    "columns": ["event_count", "score"],
    "min": 20.0,
    "max": 40.0,
    "includeEmptyValues": false
  }
}
```

## Update Guidance

1. Read existing payload first and keep unrelated top-level keys untouched.
2. Modify only target `steps[]` entries for `FilterOnNumericalRange`.
3. Confirm `action` semantics before execution (`KEEP_ROW`/`REMOVE_ROW` vs `CLEAR_CELL`/`DONTCLEAR_CELL`).
4. Keep `appliesTo`, `columns`, and `booleanMode` consistent with intended multi-column behavior.
