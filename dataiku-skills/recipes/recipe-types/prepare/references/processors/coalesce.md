---
name: prepare-coalesce
description: "Observed JSON patterns for the Coalesce prepare/shaker processor."
---

# Coalesce Processor

Return the first non-empty value across selected columns, optionally with a fallback default value.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `appliesTo` | yes | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param controlling column selection mode. |
| `columns` | yes | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Ordered input columns to coalesce. |
| `appliesToPattern` | conditional | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param; required when `appliesTo` is `PATTERN`. |
| `outputColumn` | yes | `string<column_name>` | Any valid output column name | Column containing coalesced result. |
| `useDefaultValue` | yes | `boolean` | `true` \| `false` | Enables fallback default value when no source column has a value. |
| `defaultValue` | conditional | `string<any>` | Any string value | Required when `useDefaultValue=true`; fallback value for rows where all sources are empty/null. |

## Canonical Variants

### Coalesce without fallback default

```json
{
  "type": "Coalesce",
  "params": {
    "outputColumn": "email_coalesced",
    "columns": ["email", "fake_email"],
    "appliesTo": "COLUMNS",
    "useDefaultValue": false
  }
}
```

### Coalesce with fallback default value

```json
{
  "type": "Coalesce",
  "params": {
    "outputColumn": "email_coalesced_with_default",
    "defaultValue": "example@gmail.com",
    "columns": ["email", "fake_email"],
    "appliesTo": "COLUMNS",
    "useDefaultValue": true
  }
}
```

## Update Guidance

1. Read existing payload first and keep unrelated top-level keys untouched.
2. Modify only target `steps[]` entries for `Coalesce`.
3. Keep `columns` ordered by fallback priority (first preferred, then backups).
4. Keep `useDefaultValue` and `defaultValue` coherent (`defaultValue` only when fallback is enabled).

## References

- Dataiku DSS: Coalesce (Options)  
  https://doc.dataiku.com/dss/latest/preparation/processors/coalesce.html
