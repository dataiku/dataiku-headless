---
name: prepare-flag-on-custom-formula
description: "Observed JSON patterns for the FlagOnCustomFormula prepare/shaker processor."
---

# FlagOnCustomFormula Processor

Flag rows with a formula by creating a column containing `1` for matching rows. Unmatched rows are left empty.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `expression` | yes | `string<formula_expression>` | Any valid DSS formula expression | Read [shared formula language](../dataiku_formula_language.md) before writing/updating this value. |
| `action` | yes | `enum` | `FLAG` | Output behavior for this processor. |
| `flagColumn` | yes | `string<column_name>` | Any valid output column name | Column created/updated with `1` for matching rows. |

## Canonical Variants

### Flag rows where one column contains another value

```json
{
  "type": "FlagOnCustomFormula",
  "params": {
    "expression": "contains(full_name, round(id))",
    "action": "FLAG",
    "flagColumn": "full_name_contains_id"
  }
}
```

### Flag rows with threshold logic

```json
{
  "type": "FlagOnCustomFormula",
  "params": {
    "expression": "numval(\"score\") > 80",
    "action": "FLAG",
    "flagColumn": "score_gt_80"
  }
}
```

## Update Guidance

1. Read existing payload first and keep unrelated top-level keys untouched.
2. Modify only target `steps[]` entries for `FlagOnCustomFormula`.
3. Keep `flagColumn` stable when downstream steps reference it.
4. Validate expression behavior in preview before full execution.

## References

- Dataiku DSS: Flag rows with formula (Options)  
  https://doc.dataiku.com/dss/latest/preparation/processors/flag-on-formula.html#flag-rows-with-formula
- Dataiku DSS: Formula language reference  
  https://doc.dataiku.com/dss/latest/formula/index.html
