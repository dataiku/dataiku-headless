---
name: prepare-columns-selector
description: "Observed JSON patterns for the ColumnsSelector prepare/shaker processor."
---

# ColumnsSelector Processor

Keep or remove columns by explicit names or pattern.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `appliesTo` | yes | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param. |
| `columns` | yes | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param. |
| `appliesToPattern` | conditional | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param; required when `appliesTo` is `PATTERN`. |
| `keep` | yes | `boolean` | `true` \| `false` | `false` removes selected columns, `true` keeps selected columns and drops others. |

## Canonical Variants

### Remove one column

```json
{
  "type": "ColumnsSelector",
  "params": {
    "appliesTo": "SINGLE_COLUMN",
    "columns": ["full_name"],
    "keep": false
  }
}
```

### Remove a list of columns

```json
{
  "type": "ColumnsSelector",
  "params": {
    "appliesTo": "COLUMNS",
    "columns": ["country", "score", "age"],
    "keep": false
  }
}
```

### Remove columns by pattern

```json
{
  "type": "ColumnsSelector",
  "params": {
    "appliesTo": "PATTERN",
    "appliesToPattern": "^fake.*",
    "columns": ["full_name"],
    "keep": false
  }
}
```

### Keep only selected columns

```json
{
  "type": "ColumnsSelector",
  "params": {
    "appliesTo": "COLUMNS",
    "columns": ["id", "email", "long_text"],
    "keep": true
  }
}
```

## Update Guidance

1. Read existing payload first and keep unrelated top-level keys untouched.
2. Modify only target `steps[]` entries for `ColumnsSelector`.
3. Confirm `keep` mode explicitly (`true` keep-list vs `false` drop-list) before execution.
4. For pattern mode, validate `appliesToPattern` against actual column names to avoid over-selection.

## References

- Dataiku DSS: Delete/Keep columns by name (Options)  
  https://doc.dataiku.com/dss/latest/preparation/processors/columns-select.html
