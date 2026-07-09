---
name: prepare-nest-processor
description: "Observed JSON patterns for the NestProcessor prepare/shaker processor."
---

# NestProcessor

Nest selected columns into single JSON-object output column; type embedded JSON+numeric values, keep rest as strings.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `appliesTo` | yes | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param. |
| `columns` | yes | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param. |
| `appliesToPattern` | conditional | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param; required when `appliesTo` is `PATTERN`. |
| `outputColumn` | yes | `string<column_name>` | Any valid output column name | Created JSON-object output column; non-blank. PATTERN/ALL=standalone; else inserted after last selected column. |

## Canonical Variant

```json
{
  "type": "NestProcessor",
  "params": {
    "outputColumn": "nested_object",
    "columns": ["qty", "json_object", "category"],
    "appliesTo": "COLUMNS",
    "appliesToPattern": ""
  }
}
```
