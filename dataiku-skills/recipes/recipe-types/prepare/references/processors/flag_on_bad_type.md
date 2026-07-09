---
name: prepare-flag-on-bad-type
description: "Observed JSON patterns for the FlagOnBadType prepare/shaker processor."
---

# FlagOnBadType Processor

Flag invalid rows by checking whether values match a selected meaning.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `appliesTo` | yes | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param controlling column selection mode. |
| `columns` | yes | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param. |
| `appliesToPattern` | conditional | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param; required when `appliesTo = PATTERN`. |
| `action` | yes | `enum` | `FLAG` | Output behavior for this processor. |
| `flagColumn` | yes | `string<column_name>` | Any valid output flag column name | Column created/updated with `1` for matching invalid rows. |
| `type` | yes | `enum` | See `Supported type values` below. | Meaning validity rule to check against selected columns. Observed in live payloads: `LongMeaning`, `DoubleMeaning`. |
| `considerEmptyAsInvalid` | yes | `boolean` | `true` \| `false` | Whether empty cells are treated as invalid for the selected meaning. |
| `booleanMode` | yes | `enum` | `AND` \| `OR` | Multi-column aggregation mode when multiple columns are selected. |

## Supported type values

```text
Text
DoubleMeaning
LongMeaning
Boolean
Date
DateOnly
DatetimeNoTz
JSONObjectMeaning
JSONArrayMeaning
FreeText
IPAddress
QueryString
URL
UserAgent
Email
Temperature
BagOfWordsMeaning
Gender
Measure
CurrencyMeaning
CurrencyAmountMeaning
DateSource
FrenchDoubleMeaning
Latitude
Longitude
GeoPoint
GeometryMeaning
CountryMeaning
USStateMeaning
```

## Canonical Variants

### Flag rows where one integer column is invalid

```json
{
  "type": "FlagOnBadType",
  "params": {
    "considerEmptyAsInvalid": false,
    "booleanMode": "AND",
    "columns": ["signup_unix"],
    "action": "FLAG",
    "appliesTo": "SINGLE_COLUMN",
    "flagColumn": "signup_unix_flagged",
    "type": "LongMeaning"
  }
}
```

### Flag rows when either selected decimal column is invalid

```json
{
  "type": "FlagOnBadType",
  "params": {
    "considerEmptyAsInvalid": true,
    "booleanMode": "OR",
    "columns": ["age", "score"],
    "action": "FLAG",
    "appliesTo": "COLUMNS",
    "flagColumn": "age_score_or_flagged",
    "type": "DoubleMeaning"
  }
}
```

### Flag rows when all selected decimal columns are invalid

```json
{
  "type": "FlagOnBadType",
  "params": {
    "considerEmptyAsInvalid": true,
    "booleanMode": "AND",
    "columns": ["age", "score"],
    "action": "FLAG",
    "appliesTo": "COLUMNS",
    "flagColumn": "age_score_and_flagged",
    "type": "DoubleMeaning"
  }
}
```

## Update Guidance

1. Read existing payload first and keep unrelated top-level keys untouched.
2. Modify only target `steps[]` entries for `FlagOnBadType`.
3. Keep `flagColumn` stable if downstream steps reference it.
4. Keep scope params coherent (`appliesTo`, `columns`, `appliesToPattern`).

## References

- Dataiku DSS: Flag invalid rows (Options)  
  https://doc.dataiku.com/dss/latest/preparation/processors/flag-on-meaning.html#flag-invalid-rows
