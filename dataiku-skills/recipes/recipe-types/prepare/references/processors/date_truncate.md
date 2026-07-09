---
name: prepare-date-truncate
description: "Observed JSON patterns for the DateTruncate prepare/shaker processor."
---

# DateTruncate Processor

Truncate parsed datetime to chosen calendar granularity (year/month/day/hour/minute/second).

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `inCol` | yes | `string<column_name>` | Any valid source column name | Input col; parseable date/datetime (DSS temporal meaning); unparseable rows skipped. |
| `outCol` | no | `string<column_name>` \| `""` | Any valid output column name \| empty string | Empty/unset=in-place (overwrite `inCol`); non-empty=new column. |
| `datePart` | yes | `enum` | `YEAR` \| `MONTH` \| `DAY` \| `HOUR` \| `MINUTE` \| `SECOND` | Truncation granularity. `HOUR`/`MINUTE`/`SECOND` throw at runtime on date-only col with no time component. |

## Canonical Variant

```json
{
  "type": "DateTruncate",
  "params": {
    "inCol": "iso_datetime_parsed",
    "outCol": "iso_datetime_month",
    "datePart": "MONTH"
  }
}
```
