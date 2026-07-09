---
name: prepare-unix-timestamp-parser
description: "Observed JSON patterns for the UNIXTimestampParser prepare/shaker processor."
---

# UNIXTimestampParser

Convert a Unix timestamp column to a date/datetime column.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `inCol` | yes | `string<column_name>` | Any valid input column name | Input column containing Unix timestamp values. |
| `outCol` | yes | `string<column_name>` | Any valid output column name | Output date/datetime column name. |
| `milliseconds` | yes | `boolean` | `true` \| `false` | `false`: interpret input as seconds since epoch. `true`: interpret input as milliseconds since epoch. |

## Canonical Variants

### Parse Unix timestamp in seconds

```json
{
  "type": "UNIXTimestampParser",
  "params": {
    "inCol": "signup_unix",
    "outCol": "signup_unix_date",
    "milliseconds": false
  }
}
```

### Parse Unix timestamp in milliseconds

```json
{
  "type": "UNIXTimestampParser",
  "params": {
    "inCol": "signup_unix",
    "outCol": "signup_unix_date",
    "milliseconds": true
  }
}
```

## Update Guidance

1. Read existing payload first and keep unrelated top-level keys untouched.
2. Modify only target `steps[]` entries for `UNIXTimestampParser`.
3. Set `milliseconds` correctly for source epoch precision to avoid date shifts.
4. Keep `outCol` unique if preserving both raw and parsed timestamp columns.

## References

- Dataiku DSS: Convert a Unix timestamp to a date (Options)  
  https://doc.dataiku.com/dss/latest/preparation/processors/unixtimestamp-parser.html#convert-a-unix-timestamp-to-a-date
