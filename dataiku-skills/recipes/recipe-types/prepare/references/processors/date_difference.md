---
name: prepare-date-difference
description: "Observed JSON patterns for the DateDifference prepare/shaker processor."
---

# DateDifference Processor

Compute the difference between one date column and another reference (another date column, a fixed date, or now).

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `input1` | yes | `string<column_name>` | Any valid input date column name | Primary input date column. |
| `compareTo` | yes | `enum` | `COLUMN` \| `DATE` \| `NOW` | Reference mode for second operand. |
| `input2` | conditional | `string<column_name>` | Any valid input date column name | Required when `compareTo = COLUMN`. In one `DATE` example, this field was present but not applied. |
| `refDate` | conditional | `string<iso8601_datetime>` | Any valid ISO-8601 datetime string | Required when `compareTo = DATE`. |
| `output` | yes | `string<column_name>` | Any valid output column name | Output column containing computed difference. |
| `outputUnit` | yes | `enum` | `DAYS` \| `WEEKS` \| `MONTHS` | Difference output unit (observed values). |
| `timezone_id` | yes | See [shared timezone params](../shared_timezone_params.md). | See [shared timezone params](../shared_timezone_params.md) \| `use_preferred_timezone` | Same timezone mode contract as [HolidaysComputer](holidays_computer.md). Observed value: `use_preferred_timezone`. |
| `timezone_src` | conditional | See [shared timezone params](../shared_timezone_params.md). | See [shared timezone params](../shared_timezone_params.md). | Required when `timezone_id = extract_from_column` or `timezone_id = extract_from_ip` (same contract as `HolidaysComputer`). |
| `reverse` | no | `boolean` | `true` \| `false` | Reverse subtraction direction when true. |
| `excludeWeekends` | no | `boolean` | `true` \| `false` | Exclude weekends from computed duration. |
| `excludeHolidays` | no | `boolean` | `true` \| `false` | Exclude holidays from computed duration. |
| `calendar_id` | conditional | `enum` | `AE` \| `DE` \| `ES` \| `FR` \| `IN` \| `OM` \| `SA` \| `US` \| `extract_from_column` | Same calendar mode contract as [HolidaysComputer](holidays_computer.md). Observed value: `FR`. |
| `calendar_src` | conditional | `string<column_name>` | Any valid column name | Required when `calendar_id = extract_from_column` (same contract as `HolidaysComputer`). |

## Canonical Variants

### Compare to now in days

```json
{
  "type": "DateDifference",
  "params": {
    "output": "signup_date_till_now_days",
    "excludeHolidays": false,
    "excludeWeekends": false,
    "calendar_id": "US",
    "outputUnit": "DAYS",
    "input1": "signup_date",
    "timezone_id": "use_preferred_timezone",
    "compareTo": "NOW",
    "reverse": false
  }
}
```

### Compare to another date column in months

```json
{
  "type": "DateDifference",
  "params": {
    "output": "signup_date_till_last_login_months",
    "excludeHolidays": false,
    "excludeWeekends": false,
    "calendar_id": "US",
    "input2": "last_login",
    "outputUnit": "MONTHS",
    "input1": "signup_date",
    "timezone_id": "use_preferred_timezone",
    "compareTo": "COLUMN",
    "reverse": false
  }
}
```

### Compare to fixed date in weeks with reverse

```json
{
  "type": "DateDifference",
  "params": {
    "output": "signup_date_till_12_31_2025_weeks_reverse",
    "excludeHolidays": false,
    "excludeWeekends": false,
    "calendar_id": "FR",
    "outputUnit": "WEEKS",
    "input1": "signup_date",
    "timezone_id": "use_preferred_timezone",
    "compareTo": "DATE",
    "refDate": "2025-12-31T00:00:00Z",
    "reverse": true
  }
}
```

## Update Guidance

1. Read existing payload first and keep unrelated top-level keys untouched.
2. Modify only target `steps[]` entries for `DateDifference`.
3. Keep `compareTo` coherent with conditional fields:
- `COLUMN` -> provide `input2`;
- `DATE` -> provide `refDate`;
- `NOW` -> do not rely on `input2` or `refDate`.
4. Keep timezone settings coherent (`timezone_id` with conditional `timezone_src`) using the same rules as `HolidaysComputer`.
5. Keep holiday calendar settings coherent (`calendar_id` with conditional `calendar_src`) using the same rules as `HolidaysComputer`.
6. Keep duration settings coherent (`outputUnit`, `reverse`, weekend/holiday exclusion flags, and selected calendar mode).
