---
name: prepare-column-renamer
description: "Observed JSON patterns for the ColumnRenamer prepare/shaker processor."
---

# ColumnRenamer Processor

Rename one or more columns using explicit source-to-target mappings.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `renamings` | yes | `list<object<{from:string<column_name>,to:string<column_name>}>>` | Any valid non-empty rename mapping list | Examples: `[{"from":"full_name","to":"name"}]`, `[{"from":"email","to":"user_email"},{"from":"id","to":"user_id"}]`. |

## Canonical Variants

### Single-column rename

```json
{
  "type": "ColumnRenamer",
  "params": {
    "renamings": [
      {"from": "full_name", "to": "name"}
    ]
  }
}
```

### Multi-column rename

```json
{
  "type": "ColumnRenamer",
  "params": {
    "renamings": [
      {"from": "email", "to": "user_email"},
      {"from": "id", "to": "user_id"}
    ]
  }
}
```

## Update Guidance

1. Read existing payload first and keep unrelated top-level keys untouched.
2. Modify only target `steps[]` entries for `ColumnRenamer`.
3. Ensure each `to` name is unique and does not collide with existing columns unless overwrite behavior is intended.
4. Keep `from` names aligned with current upstream schema before execution.
