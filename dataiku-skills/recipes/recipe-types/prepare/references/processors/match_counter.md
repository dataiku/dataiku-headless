---
name: prepare-match-counter
description: "Observed JSON patterns for the MatchCounter prepare/shaker processor."
---

# MatchCounter Processor

Count the number of occurrences of a pattern in the specified column.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `inCol` | yes | `string<column_name>` | Any valid input column name | Input column to scan for matches. |
| `pattern` | yes | `string<any>` | Any text value or regex-like text | Interpretation depends on `matchingMode`. |
| `matchingMode` | yes | `enum` | `FULL_STRING` \| `PATTERN` \| `SUBSTRING` | Match strategy for `pattern`. |
| `normalizationMode` | yes | `enum` | `EXACT` \| `LOWERCASE` \| `NORMALIZED` | Normalization strategy before matching. |
| `outCol` | yes | `string<column_name>` | Any valid output column name | Column where the occurrence count is written. |

## Canonical Variants

### Substring count

```json
{
  "type": "MatchCounter",
  "params": {
    "inCol": "long_text",
    "pattern": "ep",
    "matchingMode": "SUBSTRING",
    "normalizationMode": "EXACT",
    "outCol": "long_text_ep_count"
  }
}
```

### Regex-like pattern count

```json
{
  "type": "MatchCounter",
  "params": {
    "inCol": "full_name",
    "pattern": "\\d{1}",
    "matchingMode": "PATTERN",
    "normalizationMode": "LOWERCASE",
    "outCol": "full_name_digit_count"
  }
}
```

### Full-string count with normalized matching

```json
{
  "type": "MatchCounter",
  "params": {
    "inCol": "country",
    "pattern": "US",
    "matchingMode": "FULL_STRING",
    "normalizationMode": "NORMALIZED",
    "outCol": "country_us_count"
  }
}
```

## Update Guidance

1. Read existing payload first and keep unrelated top-level keys untouched.
2. Modify only target `steps[]` entries for `MatchCounter`.
3. Keep `outCol` unique per counting rule to avoid overwriting counts from earlier steps.
4. Use `matchingMode` and `normalizationMode` as an intentional pair to avoid silent behavior changes.

## References

- Dataiku DSS: Count occurrences (Options)  
  https://doc.dataiku.com/dss/latest/preparation/processors/count-matches.html
