---
name: prepare-regexp-extractor
description: "Observed JSON patterns for the RegexpExtractor prepare/shaker processor."
---

# RegexpExtractor Processor

Extract substrings from string column with Java regex; one output column per capture group (named/numbered) plus optional match-flag column. SQL pushdown conditional: named groups, 10+ capture groups, `found_col`, or `extractAllOccurrences` block plain-SQL translation (Snowflake UDF only).

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `column` | yes | `string<column_name>` | Any existing column name | Input column to extract from. |
| `pattern` | yes | `string<regex>` | A Java regex with unnamed `(...)` or named `(?<name>...)` capture groups | Not anchored. Output columns=`prefix`+groupName (named) or `prefix`+`1`..`N` (unnamed). |
| `prefix` | yes | `string<any>` | Any string (may be empty) | Output column name prefix; null normalized to empty string. |
| `found_col` | no | `boolean` | `true` \| `false` | `true`=add boolean column `prefix`+`found`. Default `false`. Blocks plain-SQL pushdown. |
| `extractAllOccurrences` | no | `boolean` | `true` \| `false` | `true`=each group output becomes array of all matches instead of single string. Default `false`. Blocks plain-SQL pushdown. |

## Canonical Variant

```json
{
  "type": "RegexpExtractor",
  "params": {
    "column": "asset_code",
    "pattern": "(?<letters>[A-Za-z]+)[-_]?(?<digits>[0-9]+)",
    "prefix": "asset_",
    "found_col": true,
    "extractAllOccurrences": false
  }
}
```
