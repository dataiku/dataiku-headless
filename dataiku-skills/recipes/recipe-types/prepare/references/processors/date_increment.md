---
name: prepare-date-increment
description: "Observed JSON patterns for the DateIncrement prepare/shaker processor."
---

# DateIncrement Processor

Increment a date column by a static value or by a value from another column.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `inCol` | yes | `string<column_name>` | Any valid input date column name | Input date/timestamp column to increment. |
| `outCol` | yes | `string<column_name>` | Any valid output column name | Output column containing incremented date values. |
| `datePart` | yes | `enum` | `SECOND` \| `MINUTE` \| `HOUR` \| `DAY` \| `WEEK` \| `MONTH` \| `QUARTER` \| `YEAR` | Date unit used for incrementing. |
| `incrementBy` | yes | `enum` | `STATIC` \| `COLUMN` | Increment source mode: fixed value or value from another column. |
| `increment` | conditional | `integer` | Any integer value | Used when `incrementBy = STATIC`; may appear in payloads with `COLUMN` mode but is not applied. |
| `valueCol` | conditional | `string<column_name>` | Any valid numeric input column name | Required when `incrementBy = COLUMN`; column supplying per-row increment value. |

## Canonical Variants

### Static increment by days

```json
{
  "type": "DateIncrement",
  "params": {
    "inCol": "last_login",
    "outCol": "last_login_plus_10_days",
    "datePart": "DAY",
    "incrementBy": "STATIC",
    "increment": 10
  }
}
```

### Increment using values from another column

```json
{
  "type": "DateIncrement",
  "params": {
    "inCol": "last_login",
    "outCol": "last_login_plus_age_column_months",
    "datePart": "MONTH",
    "incrementBy": "COLUMN",
    "increment": 10,
    "valueCol": "age"
  }
}
```

## Update Guidance

1. Read existing payload first and keep unrelated top-level keys untouched.
2. Modify only target `steps[]` entries for `DateIncrement`.
3. Keep `incrementBy`, `increment`, and `valueCol` coherent (`increment` for `STATIC`, `valueCol` for `COLUMN`).
4. Validate that `datePart` matches the intended granularity before execution.
