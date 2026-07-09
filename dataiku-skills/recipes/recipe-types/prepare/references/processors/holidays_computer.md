---
name: prepare-holidays-computer
description: "Observed JSON patterns for the HolidaysComputer prepare/shaker processor."
---

# HolidaysComputer Processor

Flag bank holidays, school holidays, and weekends from a date column, with optional holiday reasons and zones.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `inCol` | yes | `string<column_name>` | Any valid input date column name | Input date column used for holiday computation. |
| `outColPrefix` | yes | `string<any>` | Any output prefix string | Prefix for generated output columns. |
| `calendar_id` | yes | `enum` | `AE` \| `DE` \| `ES` \| `FR` \| `IN` \| `OM` \| `SA` \| `US` \| `extract_from_column` | Holiday calendar selection mode (`extract_from_column` uses per-row country code from `calendar_src`). |
| `calendar_src` | conditional | `string<column_name>` | Any valid column name | Required when `calendar_id = extract_from_column`. |
| `timezone_id` | yes | See [shared timezone params](../shared_timezone_params.md). | See [shared timezone params](../shared_timezone_params.md) \| `use_preferred_timezone` | Timezone handling for holiday computation. |
| `timezone_src` | conditional | See [shared timezone params](../shared_timezone_params.md). | See [shared timezone params](../shared_timezone_params.md). | Required when `timezone_id = extract_from_column`. |
| `flagBankHolidays` | yes | `boolean` | `true` \| `false` | Whether bank holidays are flagged. |
| `flagSchoolHolidays` | yes | `boolean` | `true` \| `false` | Whether school holidays are flagged. |
| `flagWeekends` | yes | `boolean` | `true` \| `false` | Whether weekends are flagged. |
| `extractReasons` | yes | `boolean` | `true` \| `false` | Whether holiday reason labels are extracted. |
| `extractZones` | yes | `boolean` | `true` \| `false` | Whether holiday zone information is extracted. |

## Canonical Variants

### French bank and school holidays with zones

```json
{
  "type": "HolidaysComputer",
  "params": {
    "inCol": "last_login",
    "outColPrefix": "holiday_fr_",
    "calendar_id": "FR",
    "timezone_id": "use_preferred_timezone",
    "flagBankHolidays": true,
    "flagSchoolHolidays": true,
    "flagWeekends": false,
    "extractReasons": false,
    "extractZones": true
  }
}
```

### US bank holidays plus weekends and reasons

```json
{
  "type": "HolidaysComputer",
  "params": {
    "inCol": "last_login",
    "outColPrefix": "holiday_us_",
    "calendar_id": "US",
    "timezone_id": "UTC",
    "flagBankHolidays": true,
    "flagSchoolHolidays": false,
    "flagWeekends": true,
    "extractReasons": true,
    "extractZones": false
  }
}
```

### Calendar and timezone from columns

```json
{
  "type": "HolidaysComputer",
  "params": {
    "inCol": "last_login",
    "outColPrefix": "holiday_country_",
    "calendar_id": "extract_from_column",
    "calendar_src": "country",
    "timezone_id": "extract_from_column",
    "timezone_src": "timezone",
    "flagBankHolidays": true,
    "flagSchoolHolidays": false,
    "flagWeekends": false,
    "extractReasons": false,
    "extractZones": false
  }
}
```

## Update Guidance

1. Read existing payload first and keep unrelated top-level keys untouched.
2. Modify only target `steps[]` entries for `HolidaysComputer`.
3. Keep `calendar_id` and `calendar_src` coherent (`calendar_src` only when `calendar_id = extract_from_column`).
4. Keep `timezone_id` and `timezone_src` coherent (`timezone_src` only when `timezone_id = extract_from_column`).

## References

- Dataiku DSS: Flag holidays (Options)  
  https://doc.dataiku.com/dss/latest/preparation/processors/holidays-computer.html#flag-holidays
