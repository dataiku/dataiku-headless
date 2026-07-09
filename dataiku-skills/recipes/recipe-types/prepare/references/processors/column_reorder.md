---
name: prepare-column-reorder
description: "Observed JSON patterns for the ColumnReorder prepare/shaker processor."
---

# ColumnReorder Processor

Move selected columns to a new position (start, end, or relative to a reference column); does not add, remove, or modify any column values.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `columns` | yes | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param; columns to move. |
| `referenceColumn` | conditional | `string<column_name>` \| `""` | An existing column name or empty string | Column to position relative to; required for `BEFORE_COLUMN`/`AFTER_COLUMN`, ignored (empty) for `AT_START`/`AT_END`. |
| `reorderAction` | no | `enum` | `AT_START` \| `BEFORE_COLUMN` \| `AFTER_COLUMN` \| `AT_END` | New position for selected columns. Default `AT_START`. |
| `appliesTo` | yes | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param. |
| `appliesToPattern` | conditional | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param; required when `appliesTo` is `PATTERN`. |

## Canonical Variants

### Move columns to start

```json
{
  "type": "ColumnReorder",
  "params": {
    "columns": ["category", "qty"],
    "referenceColumn": "",
    "reorderAction": "AT_START",
    "appliesTo": "COLUMNS",
    "appliesToPattern": ""
  }
}
```

### Move a column before a reference column

```json
{
  "type": "ColumnReorder",
  "params": {
    "columns": ["qty"],
    "referenceColumn": "category",
    "reorderAction": "BEFORE_COLUMN",
    "appliesTo": "SINGLE_COLUMN",
    "appliesToPattern": ""
  }
}
```
