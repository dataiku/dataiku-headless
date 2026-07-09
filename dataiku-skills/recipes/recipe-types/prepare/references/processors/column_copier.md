---
name: prepare-column-copier
description: "Observed JSON patterns for the ColumnCopier prepare/shaker processor."
---

# ColumnCopier Processor

Copy values from one column to another column.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `inputColumn` | yes | `string<column_name>` | Any valid source column name | Source column to copy from. |
| `outputColumn` | yes | `string<column_name>` | Any valid destination column name | Destination column to copy into. |

## Canonical Variant

```json
{
  "type": "ColumnCopier",
  "params": {
    "outputColumn": "status_copy",
    "inputColumn": "status"
  }
}
```

## Update Guidance

1. Read existing payload first and keep unrelated top-level keys untouched.
2. Modify only target `steps[]` entries for `ColumnCopier`.
3. Keep `outputColumn` distinct unless intentional overwrite of an existing column is desired.
4. Ensure downstream steps reference the copied column name (`outputColumn`) where appropriate.

## References

- Dataiku DSS: Copy a column (Options)  
  https://doc.dataiku.com/dss/latest/preparation/processors/column-copy.html
