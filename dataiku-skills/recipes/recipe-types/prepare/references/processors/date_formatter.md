---
name: prepare-date-formatter
description: "Observed JSON patterns for the DateFormatter prepare/shaker processor."
---

# DateFormatter Processor

Reformat parsed ISO 8601 datetime to string via Java `SimpleDateFormat` pattern.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `inCol` | yes | `string<column_name>` | Any valid source column name | Input col; DSS temporal meaning (Date/DateTimeNoTz/DateOnly); unparseable values skipped. |
| `outCol` | no | `string<column_name>` \| `""` | Any valid output column name \| empty string | Empty/unset=in-place (overwrite `inCol`); non-empty=new column. |
| `format` | yes | `string<java_date_pattern>` | Any valid Java `SimpleDateFormat` pattern (for example `yyyy-MM-dd HH:mm:ss`) | Output format. Non-ISO-8601 result=DSS treats as unparsed string. |
| `lang` | no | `enum` \| `string<locale_code>` | `auto` \| `en_US` \| `fr_FR` | Locale for textual parts (month/day names). `auto`=`en_US`. |
| `timezone_id` | conditional | See [shared timezone params](../shared_timezone_params.md). | See [shared timezone params](../shared_timezone_params.md). | Shared timezone param; default `UTC`. Only applies when the input value carries timezone info. |
| `timezone_src` | conditional | See [shared timezone params](../shared_timezone_params.md). | See [shared timezone params](../shared_timezone_params.md). | Shared timezone param; required when `timezone_id` is `extract_from_column` or `extract_from_ip`. |

## Canonical Variant

```json
{
  "type": "DateFormatter",
  "params": {
    "inCol": "iso_datetime_parsed",
    "outCol": "iso_datetime_formatted",
    "format": "yyyy-MM-dd HH:mm:ss",
    "timezone_id": "UTC",
    "lang": "en_US"
  }
}
```
