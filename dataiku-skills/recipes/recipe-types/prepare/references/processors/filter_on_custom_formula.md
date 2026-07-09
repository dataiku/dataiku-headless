---
name: prepare-filter-on-custom-formula
description: "Observed JSON patterns for the FilterOnCustomFormula prepare/shaker processor."
---

# FilterOnCustomFormula Processor

Filter rows or clear cell values based on a formula expression. The row/cell matches if the result of the formula is considered as "truish," which includes: a true boolean, a number (integer or decimal) that is not 0, and the string "true".


## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `expression` | yes | `string<formula_expression>` | Any valid DSS formula expression | Read [shared formula language](../dataiku_formula_language.md) before writing/updating this value. |
| `action` | yes | `enum` | `KEEP_ROW` \| `REMOVE_ROW` \| `CLEAR_CELL` \| `DONTCLEAR_CELL` | Row-level filtering or cell-clearing mode. |
| `clearColumn` | conditional | `string<column_name>` | Any valid target column name | Required for `CLEAR_CELL` and `DONTCLEAR_CELL`; ignored for row actions. |

## Canonical Variants

### Keep matching rows

```json
{
  "type": "FilterOnCustomFormula",
  "params": {
    "expression": "contains(full_name, round(id))",
    "action": "KEEP_ROW"
  }
}
```

### Remove matching rows

```json
{
  "type": "FilterOnCustomFormula",
  "params": {
    "expression": "contains(country, \"GB\")",
    "action": "REMOVE_ROW"
  }
}
```

### Clear cells where formula is true

```json
{
  "type": "FilterOnCustomFormula",
  "params": {
    "expression": "age>65",
    "action": "CLEAR_CELL",
    "clearColumn": "score"
  }
}
```

### Clear cells where formula is false

```json
{
  "type": "FilterOnCustomFormula",
  "params": {
    "expression": "age<60",
    "action": "DONTCLEAR_CELL",
    "clearColumn": "score"
  }
}
```

## Update Guidance

1. Read existing payload first and keep unrelated top-level keys untouched.
2. Modify only target `steps[]` entries for `FilterOnCustomFormula`.
3. Set `clearColumn` only for cell-clearing actions (`CLEAR_CELL`, `DONTCLEAR_CELL`).
4. Validate whether the formula should keep/remove rows or clear cells before persisting updates.

## References

- Dataiku DSS: Filter rows/cells with formula (Options)  
  https://doc.dataiku.com/dss/latest/preparation/processors/filter-on-formula.html#filter-rows-cells-with-formula
- Dataiku DSS: Formula language reference  
  https://doc.dataiku.com/dss/latest/formula/index.html
