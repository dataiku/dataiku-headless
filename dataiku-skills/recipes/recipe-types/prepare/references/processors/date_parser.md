---
name: prepare-date-parser
description: "Observed JSON patterns for the DateParser prepare/shaker processor."
---

# DateParser Processor

Parse strings containing dates in any format into the standard ISO 8601 format (`yyyy-MM-ddTHH:mm:ss.SSSZ`).

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `appliesTo` | yes | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param. |
| `columns` | yes | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param. |
| `appliesToPattern` | conditional | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param; required when `appliesTo` is `PATTERN`. |
| `outCol` | no | `string<column_name>` | Any valid output column name | Leave empty/unset to parse in place. |
| `formats` | yes | `list<string<java_date_pattern>>` | Any valid Java date format pattern(s) | Uses Java `SimpleDateFormat`-style patterns. |
| `lang` | yes | `enum` \| `string<locale_code>` | `auto` \| any valid locale code (for example `en_US`, `fr_FR`) | Locale for parsing textual date parts (month/day names). |
| `timezone_id` | yes | See [shared timezone params](../shared_timezone_params.md). | See [shared timezone params](../shared_timezone_params.md). | Shared timezone param. |
| `timezone_src` | conditional | See [shared timezone params](../shared_timezone_params.md). | See [shared timezone params](../shared_timezone_params.md). | Shared timezone param; required when `timezone_id` is `extract_from_column` or `extract_from_ip`. |
| `outType` | yes | `object<{name:enum,type:enum}>` | `{"name":"out","type":"date"}` \| `{"name":"out","type":"dateonly"}` \| `{"name":"out","type":"datetimenotz"}` | Output date type: datetime with timezone, date only, or datetime without timezone. |

## Canonical Variants

### Parse to datetime with timezone

```json
{
  "type": "DateParser",
  "params": {
    "appliesTo": "SINGLE_COLUMN",
    "columns": ["signup_date"],
    "formats": ["yyyy-MM-dd"],
    "lang": "en_US",
    "outType": {"name": "out", "type": "date"},
    "timezone_id": "UTC"
  }
}
```

### Parse to date-only in a new output column

```json
{
  "type": "DateParser",
  "params": {
    "appliesTo": "SINGLE_COLUMN",
    "columns": ["signup_date_string"],
    "formats": ["MM/dd/yyyy", "dd-MM-yyyy", "yyyy-MM-dd"],
    "lang": "auto",
    "outCol": "signup_date_string_parsed_date_only",
    "outType": {"name": "out", "type": "dateonly"},
    "timezone_id": "UTC"
  }
}
```

### Parse to datetime without timezone

```json
{
  "type": "DateParser",
  "params": {
    "appliesTo": "SINGLE_COLUMN",
    "columns": ["signup_date_string"],
    "formats": ["MM/dd/yyyy", "dd-MM-yyyy", "yyyy-MM-dd"],
    "lang": "fr_FR",
    "outCol": "signup_date_string_parsed_no_tz_fr",
    "outType": {"name": "out", "type": "datetimenotz"},
    "timezone_id": "UTC"
  }
}
```

## Update Guidance

1. Read existing payload first and keep unrelated top-level keys untouched.
2. Modify only target `steps[]` entries for `DateParser`.
3. Keep `formats`, `lang`, and `timezone_id` coherent with the actual source date strings.
4. Set `timezone_src` whenever timezone is extracted from another column or IP column.

## References

- Dataiku DSS: Parse to standard date format (Options)  
  https://doc.dataiku.com/dss/latest/preparation/processors/date-parser.html#parse-to-standard-date-format
