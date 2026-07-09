---
name: prepare-create-column-with-grel
description: "Observed JSON patterns for the CreateColumnWithGREL (formula) prepare/shaker processor."
---

# CreateColumnWithGREL Processor

Compute new columns using formulas based on other columns. The formula language provides Math functions, String manipulation functions, Date handling functions, and Boolean and conditional expressions for rules creation.

This processor is a fallback for logic that cannot be expressed more safely with other, more targeted prepare processors. It should not be the first choice for common cleaning, parsing, and normalization tasks.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `expression` | yes | `string<formula_expression>` | Any valid DSS formula expression | Read [shared formula language](../dataiku_formula_language.md) before writing/updating this value. |
| `column` | yes | `string<column_name>` | Any valid output column name | Output column created or overwritten by the formula result. |
| `errorColumn` | no | `string<column_name>` \| `""` | Any valid error column name \| empty string | When non-empty, evaluation errors are written to this column. Leave it empty by default because non-empty error columns can block SQL execution/pushdown. |

## Canonical Variants

### Numeric arithmetic

```json
{
  "type": "CreateColumnWithGREL",
  "params": {
    "expression": "age + 3",
    "column": "age_plus_3",
    "errorColumn": ""
  }
}
```

### Boolean-style branching with `if`

```json
{
  "type": "CreateColumnWithGREL",
  "params": {
    "expression": "if(age<35, \"true\", \"false\")",
    "column": "age_below_35",
    "errorColumn": ""
  }
}
```

### Type-safe numeric conversion for columns with spaces

```json
{
  "type": "CreateColumnWithGREL",
  "params": {
    "expression": "numval(\"event count\")*10",
    "column": "event_count_times_10",
    "errorColumn": ""
  }
}
```

### String comparison

```json
{
  "type": "CreateColumnWithGREL",
  "params": {
    "expression": "if(is_active==\"yes\",\"it's active\", \"nope\")",
    "column": "is_active_yes",
    "errorColumn": ""
  }
}
```

### Concatenation

```json
{
  "type": "CreateColumnWithGREL",
  "params": {
    "expression": "concat(id, full_name)",
    "column": "id_full_name_concat",
    "errorColumn": ""
  }
}
```

## Update Guidance

1. Read existing payload first and keep unrelated top-level keys untouched.
2. Modify only target `steps[]` entries for `CreateColumnWithGREL`.
3. Keep `column` unique per step sequence unless intentional overwrite is desired.
4. Confirm that a dedicated processor is not a better fit before adding or keeping a GREL step.
5. Prefer simple formulas that match the transformation intent; do not add extra error-handling logic unless the user asks for it or the data inspection clearly requires it.
6. Leave `errorColumn` empty unless the user explicitly accepts reduced SQL compatibility for this recipe.
7. Remember step order: formulas can reference columns created by prior steps.
8. After updating, build the recipe output and inspect the produced columns for accuracy before adding dependent downstream steps.

## References

- Dataiku DSS: Formula processor (Options)  
  https://doc.dataiku.com/dss/latest/preparation/processors/formula.html#formula
- Dataiku DSS: Formula language reference  
  https://doc.dataiku.com/dss/latest/formula/index.html
