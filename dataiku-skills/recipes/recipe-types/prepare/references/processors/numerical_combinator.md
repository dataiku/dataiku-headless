---
name: prepare-numerical-combinator
description: "Observed JSON patterns for the NumericalCombinator prepare/shaker processor."
---

# NumericalCombinator Processor

Generate pairwise sum/difference/product/quotient columns from selected numeric columns. DSS/Java engine only; not SQL-translatable; no native Spark.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `appliesTo` | yes | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param. Selects the numeric columns combined pairwise; effectively `COLUMNS` / `PATTERN` / `ALL`. |
| `columns` | conditional | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param; required when `appliesTo` is `SINGLE_COLUMN` or `COLUMNS`. Needs at least 2 numeric columns; runtime caps at 19 columns. |
| `appliesToPattern` | conditional | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param; required when `appliesTo` is `PATTERN`. |
| `prefix` | yes | `string<any>` | Any column-name prefix | Prepended to generated names: `prefix` + `<op>_` + leftCol + `_` + rightCol. |
| `add` | no | `boolean` | `true` \| `false` | Generate additions. Default `true`. |
| `sub` | no | `boolean` | `true` \| `false` | Generate subtractions. Default `true`. |
| `mul` | no | `boolean` | `true` \| `false` | Generate multiplications. Default `true`. |
| `div` | no | `boolean` | `true` \| `false` | Generate divisions. Default `true`. Division by zero/empty operand=empty cell. At least one of `add`/`sub`/`mul`/`div` required. |

## Canonical Variant

```json
{
  "type": "NumericalCombinator",
  "params": {
    "add": true,
    "div": true,
    "sub": true,
    "mul": true,
    "columns": ["qty", "price"],
    "prefix": "combo_",
    "appliesTo": "COLUMNS"
  }
}
```
