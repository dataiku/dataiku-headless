---
name: prepare-filter-on-bad-type
description: "Observed JSON patterns for the FilterOnBadType prepare/shaker processor."
---

# FilterOnBadType Processor

Filter invalid rows/cells by checking whether values match a selected meaning.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `appliesTo` | yes | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param controlling column selection mode. |
| `columns` | yes | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param. |
| `appliesToPattern` | conditional | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param; required when `appliesTo = PATTERN`. |
| `action` | yes | `enum` | `KEEP_ROW` \| `REMOVE_ROW` \| `CLEAR_CELL` \| `DONTCLEAR_CELL` \| `FLAG` | Row-level filtering, cell-clearing, or `FLAG` (add an indicator column instead of filtering). |
| `flagColumn` | conditional | `string<column_name>` | Any valid output column name | Indicator column written when `action` is `FLAG`; required for that action. |
| `type` | yes | `enum` | See `Supported type values` below. | Meaning validity rule to check against selected columns. Observed in live payloads: `LongMeaning`, `DoubleMeaning`, `JSONArrayMeaning`. |
| `considerEmptyAsInvalid` | yes | `boolean` | `true` \| `false` | Whether empty cells are treated as invalid for the selected meaning. |
| `booleanMode` | yes | `enum` | `AND` \| `OR` | Multi-column aggregation mode. |

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

### Clear invalid cells in one integer column

```json
{
  "type": "FilterOnBadType",
  "params": {
    "considerEmptyAsInvalid": false,
    "booleanMode": "AND",
    "columns": ["signup_unix"],
    "action": "CLEAR_CELL",
    "appliesTo": "SINGLE_COLUMN",
    "type": "LongMeaning"
  }
}
```

### Remove rows with invalid integer values (including empty cells)

```json
{
  "type": "FilterOnBadType",
  "params": {
    "considerEmptyAsInvalid": true,
    "booleanMode": "AND",
    "columns": ["signup_unix"],
    "action": "REMOVE_ROW",
    "appliesTo": "SINGLE_COLUMN",
    "type": "LongMeaning"
  }
}
```

### Clear non-matching cells across multiple decimal columns

```json
{
  "type": "FilterOnBadType",
  "params": {
    "considerEmptyAsInvalid": false,
    "booleanMode": "AND",
    "columns": ["event_count", "score"],
    "action": "DONTCLEAR_CELL",
    "appliesTo": "COLUMNS",
    "type": "DoubleMeaning"
  }
}
```

### Keep rows matching array meaning (including empty cells)

```json
{
  "type": "FilterOnBadType",
  "params": {
    "considerEmptyAsInvalid": true,
    "booleanMode": "AND",
    "columns": ["tags"],
    "action": "KEEP_ROW",
    "appliesTo": "SINGLE_COLUMN",
    "type": "JSONArrayMeaning"
  }
}
```

## Update Guidance

1. Read existing payload first and keep unrelated top-level keys untouched.
2. Modify only target `steps[]` entries for `FilterOnBadType`.
3. Keep `action` coherent with intent (row filtering vs cell clearing).
4. Keep scope params coherent (`appliesTo`, `columns`, `appliesToPattern`).

## References

- Dataiku DSS: Filter invalid rows/cells (Options)  
  https://doc.dataiku.com/dss/latest/preparation/processors/filter-on-meaning.html#filter-invalid-rows-cells
