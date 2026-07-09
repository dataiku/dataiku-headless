---
name: prepare-flag-on-date
description: "Observed JSON patterns for the FlagOnDate prepare/shaker processor."
---

# FlagOnDate Processor

Flag rows from a dataset based on date conditions: static range, relative range, or date-part matching.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `appliesTo` | yes | `enum` | `SINGLE_COLUMN` \| `COLUMNS` \| `PATTERN` \| `ALL` | Column scope: single column, explicit list, name pattern, or all columns. |
| `columns` | yes | `list<string<column_name>>` | Date column name(s) | Date column(s) evaluated by the filter. |
| `appliesToPattern` | conditional | `string<regex>` | Any valid regex-like pattern | Required when `appliesTo` is `PATTERN`; targets matching column names. |
| `action` | yes | `enum` | `FLAG` | Output behavior for this processor in observed payloads. |
| `flagColumn` | yes | `string<column_name>` | Any valid output flag column name | Column created/updated with `1` for matching rows. |
| `filterType` | yes | `enum` | `RANGE` \| `RELATIVE` \| `PART` | Date filter mode. |
| `part` | yes | `string<date_part_constant>` | `YEAR` \| `MONTH_OF_YEAR` \| other DSS-supported date-part constants | Date part used by relative/date-part modes. |
| `values` | conditional | `list<string<any>>` | Any list of date-part values (for example `["07","08"]`) | Required when `filterType = PART`; ignored otherwise. |
| `min` | no | `string<iso_8601_datetime_notz>` | Any ISO-like datetime string (for example `2024-12-01T00:00:00.000`) | Lower bound for static range mode. Inclusive boundary. |
| `max` | no | `string<iso_8601_datetime_notz>` | Any ISO-like datetime string (for example `2024-12-31T23:59:59.000`) | Upper bound for static range mode. Inclusive boundary. |
| `option` | conditional | `object<{last:number,next:number,containsCurrentDatePart:boolean,isUntilNow:boolean}>` | Relative-range option object | Required when `filterType = RELATIVE`. |
| `timezone_id` | yes | See [shared timezone params](../shared_timezone_params.md). | See [shared timezone params](../shared_timezone_params.md). | Timezone parameter for date interpretation. |
| `includeEmptyValues` | yes | `boolean` | `true` \| `false` | Whether empty values are treated as matching. |
| `booleanMode` | yes | `enum` | `AND` \| `OR` | Multi-column aggregation mode. |

## Canonical Variants

### Static range flagging

```json
{
  "type": "FlagOnDate",
  "params": {
    "min": "2024-12-01T00:00:00.000",
    "max": "2024-12-31T23:59:59.000",
    "booleanMode": "AND",
    "columns": ["last_login"],
    "part": "YEAR",
    "values": [],
    "timezone_id": "UTC",
    "action": "FLAG",
    "appliesTo": "SINGLE_COLUMN",
    "includeEmptyValues": false,
    "flagColumn": "last_login_in_dec_2024",
    "filterType": "RANGE"
  }
}
```

### Relative range flagging

```json
{
  "type": "FlagOnDate",
  "params": {
    "columns": ["last_login"],
    "part": "YEAR",
    "values": [],
    "appliesTo": "SINGLE_COLUMN",
    "includeEmptyValues": false,
    "booleanMode": "AND",
    "timezone_id": "UTC",
    "action": "FLAG",
    "flagColumn": "last_login_in_last_2_calendar_years",
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

### Date-part list flagging

```json
{
  "type": "FlagOnDate",
  "params": {
    "columns": ["last_login"],
    "part": "MONTH_OF_YEAR",
    "values": ["07", "08"],
    "appliesTo": "SINGLE_COLUMN",
    "includeEmptyValues": false,
    "booleanMode": "AND",
    "timezone_id": "UTC",
    "action": "FLAG",
    "flagColumn": "last_login_in_any_july_or_aug",
    "filterType": "PART"
  }
}
```

## Update Guidance

1. Read existing payload first and keep unrelated top-level keys untouched.
2. Modify only target `steps[]` entries for `FlagOnDate`.
3. Keep `filterType` coherent with mode-specific params (`option` for `RELATIVE`, `values` for `PART`, boundaries for `RANGE`).
4. Keep `flagColumn` stable if downstream steps reference it.

## References

- Dataiku DSS: Flag rows/cells on date range (Options)  
  https://doc.dataiku.com/dss/latest/preparation/processors/flag-on-date.html#flag-rows-cells-on-date-range
