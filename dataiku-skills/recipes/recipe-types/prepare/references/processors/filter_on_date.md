---
name: prepare-filter-on-date
description: "Observed JSON patterns for the FilterOnDate prepare/shaker processor."
---

# FilterOnDate Processor

Keep/remove/clear rows+cells on date condition: static range, relative window, or date part. Target column must hold parsed ISO 8601 dates; add date-parse step upstream if still text.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `appliesTo` | yes | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param. |
| `columns` | conditional | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param; required non-empty when `appliesTo` is `SINGLE_COLUMN` or `COLUMNS`. |
| `appliesToPattern` | conditional | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param; required when `appliesTo` is `PATTERN`. |
| `action` | yes | `enum` | `KEEP_ROW` \| `REMOVE_ROW` \| `CLEAR_CELL` \| `DONTCLEAR_CELL` | `KEEP_ROW`/`REMOVE_ROW`=change row count; `CLEAR_CELL`/`DONTCLEAR_CELL`=blank cells only. |
| `booleanMode` | no | `enum` | `AND` \| `OR` | Combines match checks across selected columns for row actions: `AND`=all match; `OR`=any matches. |
| `filterType` | yes | `enum` | `RANGE` \| `RELATIVE` \| `PART` | Date filter mode: `RANGE`=fixed range; `RELATIVE`=relative window; `PART`=date-part match. |
| `min` | conditional | `string<iso8601_datetime>` | Any ISO 8601 datetime string (for example `2025-01-01T00:00:00.000`) | Inclusive lower bound for `filterType` `RANGE`; blank=no lower bound. |
| `max` | conditional | `string<iso8601_datetime>` | Any ISO 8601 datetime string (for example `2025-06-30T23:59:59.000`) | Inclusive upper bound for `filterType` `RANGE`; blank=no upper bound. |
| `part` | conditional | `string<date_part_constant>` | `HOUR_OF_DAY` \| `DAY_OF_WEEK` \| `DAY_OF_MONTH` \| `MONTH_OF_YEAR` \| `WEEK_OF_YEAR` \| `QUARTER_OF_YEAR` \| `YEAR` \| `INDIVIDUAL` | Required for `filterType` `PART` (part compared) and `RELATIVE` (window granularity). `HOUR_OF_DAY` never matches date-only column. |
| `values` | conditional | `list<string<any>>` | Integers for non-`INDIVIDUAL` parts; ISO date (`yyyy-MM-dd`) for `part` `INDIVIDUAL` | `filterType` `PART` only; required then. |
| `option` | conditional | `object<{last:integer, next:integer, isUntilNow:boolean, containsCurrentDatePart:boolean}>` | Relative-window option object | `filterType` `RELATIVE` only; required then. |
| `timezone_id` | no | `enum` | `UTC` plus the DSS short timezone list | Timezone parsing+comparing `RANGE` bounds. Default `UTC`. |
| `includeEmptyValues` | no | `boolean` | `true` \| `false` | `true`=blank cell counts as matching; else blank/invalid dates out of range. |

## Canonical Variants

### Remove rows inside a static date range

```json
{
  "type": "FilterOnDate",
  "params": {
    "min": "2025-01-01T00:00:00.000",
    "max": "2025-06-30T23:59:59.000",
    "columns": ["iso_datetime"],
    "booleanMode": "AND",
    "part": "YEAR",
    "values": [],
    "timezone_id": "UTC",
    "appliesTo": "SINGLE_COLUMN",
    "action": "REMOVE_ROW",
    "includeEmptyValues": false,
    "filterType": "RANGE"
  }
}
```

### Keep rows in a relative window

```json
{
  "type": "FilterOnDate",
  "params": {
    "columns": ["iso_datetime"],
    "booleanMode": "AND",
    "part": "YEAR",
    "values": [],
    "timezone_id": "UTC",
    "appliesTo": "SINGLE_COLUMN",
    "action": "KEEP_ROW",
    "includeEmptyValues": false,
    "filterType": "RELATIVE",
    "option": {
      "next": 0,
      "last": 2,
      "containsCurrentDatePart": false,
      "isUntilNow": false
    }
  }
}
```

### Keep rows matching a date part

```json
{
  "type": "FilterOnDate",
  "params": {
    "columns": ["iso_datetime"],
    "booleanMode": "AND",
    "part": "MONTH_OF_YEAR",
    "values": ["7", "8"],
    "timezone_id": "UTC",
    "appliesTo": "SINGLE_COLUMN",
    "action": "KEEP_ROW",
    "includeEmptyValues": false,
    "filterType": "PART"
  }
}
```
