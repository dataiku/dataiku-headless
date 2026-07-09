---
name: prepare-date-components-extractor
description: "Observed JSON patterns for the DateComponentsExtractor prepare/shaker processor."
---

# DateComponentsExtractor Processor

Extract various elements of a ISO-8601 formatted date (yyyy-MM-ddTHH:mm:ss.SSSZ) to other columns.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `column` | yes | `string<column_name>` | Any valid input date column name | Input date/timestamp column to decompose. |
| `timezone_id` | yes | See [shared timezone params](../shared_timezone_params.md). | See [shared timezone params](../shared_timezone_params.md). | Shared timezone param. |
| `timezone_src` | conditional | See [shared timezone params](../shared_timezone_params.md). | See [shared timezone params](../shared_timezone_params.md). | Shared timezone param; required when `timezone_id` is `extract_from_column` or `extract_from_ip`. |
| `outYearColumn` | no | `string<column_name>` | Any valid output column name or empty string | Output column for year element. |
| `outMonthColumn` | no | `string<column_name>` | Any valid output column name or empty string | Output column for month element. |
| `outDayColumn` | no | `string<column_name>` | Any valid output column name or empty string | Output column for day-of-month element. |
| `outDayOfWeekColumn` | no | `string<column_name>` | Any valid output column name or empty string | Output column for day-of-week element. |
| `outHourColumn` | no | `string<column_name>` | Any valid output column name or empty string | Output column for hour element. |
| `outMinuteColumn` | no | `string<column_name>` | Any valid output column name or empty string | Output column for minute element. |
| `outSecondColumn` | no | `string<column_name>` | Any valid output column name or empty string | Output column for second element. |
| `outMSColumn` | no | `string<column_name>` | Any valid output column name or empty string | Output column for millisecond element. |
| `outWeekOfYearColumn` | no | `string<column_name>` | Any valid output column name or empty string | Output column for week-of-year element. |
| `outWeekYearColumn` | no | `string<column_name>` | Any valid output column name or empty string | Output column for week-year element. |
| `outTimestampColumn` | no | `string<column_name>` | Any valid output column name or empty string | Output column for UNIX timestamp element. |

## Canonical Variants

### Extract many elements using static timezone

```json
{
  "type": "DateComponentsExtractor",
  "params": {
    "column": "last_login",
    "timezone_id": "UTC",
    "outYearColumn": "last_login_year",
    "outMonthColumn": "last_login_month",
    "outDayColumn": "last_login_day",
    "outDayOfWeekColumn": "last_login_day_of_week",
    "outHourColumn": "last_login_hour",
    "outMinuteColumn": "last_login_minutes",
    "outSecondColumn": "last_login_seconds",
    "outMSColumn": "last_login_milliseconds",
    "outWeekOfYearColumn": "last_login_week_of_year",
    "outWeekYearColumn": "last_login_week_year",
    "outTimestampColumn": "last_login_timestamp"
  }
}
```

### Extract using timezone from IP column

```json
{
  "type": "DateComponentsExtractor",
  "params": {
    "column": "last_login",
    "timezone_id": "extract_from_ip",
    "timezone_src": "fake_ip_address",
    "outYearColumn": "last_login_year_ip_tz"
  }
}
```

### Extract using timezone from timezone column

```json
{
  "type": "DateComponentsExtractor",
  "params": {
    "column": "last_login",
    "timezone_id": "extract_from_column",
    "timezone_src": "timezone",
    "outDayOfWeekColumn": "last_login_day_of_week_tz_col",
    "outYearColumn": ""
  }
}
```

## Update Guidance

1. Read existing payload first and keep unrelated top-level keys untouched.
2. Modify only target `steps[]` entries for `DateComponentsExtractor`.
3. Ensure timezone mode is coherent: set `timezone_src` whenever timezone is extracted from column/IP.
4. Leave unused output fields empty (or unset) to avoid creating unnecessary columns.
