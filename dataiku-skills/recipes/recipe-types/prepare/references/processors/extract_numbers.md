---
name: prepare-extract-numbers
description: "Observed JSON patterns for the ExtractNumbers prepare/shaker processor."
---

# ExtractNumbers Processor

Parse numeric values from an alphanumeric text column into one or more decimal columns. SQL translation Snowflake-UDF-only, gated on a recorded `producedColumns` report; without it runs on DSS engine.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `output` | no | `string<column_name>` \| `""` | Any valid output column name or empty string | Output column (single-value or `extractToJson` path; empty=in-place on `input`); or column prefix when `multipleValues`=`true` and `extractToJson`=`false`. |
| `multipleValues` | no | `boolean` | `true` \| `false` | Extract several values. UI default `true`. `false`=only first number into a single `DOUBLE` column. |
| `input` | yes | `string<column_name>` | Any existing column name | Input text column to parse numbers from. |
| `replaceMultipliers` | no | `boolean` | `true` \| `false` | Expand `k`=`1000`, `m`=`1000000`. Default `false`. |
| `delimiter` | no | `enum` | `BEST_GUESS` \| `COMMA` \| `DOT` | Decimal separator. Default `BEST_GUESS`; also strips thousands separators and tolerates a space before `k`/`m`. |
| `extractToJson` | conditional | `boolean` | `true` \| `false` | Extract values into a single JSON-array string column; meaningful only when `multipleValues`=`true`. Default `false`. |

## Canonical Variants

### First number into a new decimal column

```json
{
  "type": "ExtractNumbers",
  "params": {
    "output": "asset_code_number",
    "multipleValues": false,
    "input": "asset_code",
    "replaceMultipliers": false,
    "delimiter": "BEST_GUESS",
    "extractToJson": false
  }
}
```

### All numbers into a single JSON-array column

```json
{
  "type": "ExtractNumbers",
  "params": {
    "output": "asset_code_numbers",
    "multipleValues": true,
    "input": "asset_code",
    "replaceMultipliers": true,
    "delimiter": "BEST_GUESS",
    "extractToJson": true
  }
}
```
