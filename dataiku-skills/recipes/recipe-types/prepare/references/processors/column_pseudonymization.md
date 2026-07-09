---
name: prepare-column-pseudonymization
description: "Observed JSON patterns for the ColumnPseudonymization prepare/shaker processor."
---

# ColumnPseudonymization Processor

Pseudonymize values in selected columns by hashing `cell_value + pepper + salt_value`.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `appliesTo` | yes | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param controlling column selection mode. |
| `columns` | yes | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param. Keep list coherent with `appliesTo`. |
| `appliesToPattern` | conditional | See [shared scope params](../shared_scope_params.md). | See [shared scope params](../shared_scope_params.md). | Shared scope param; required when `appliesTo = PATTERN`. |
| `algorithm` | yes | `enum` | `SHA256` \| `SHA512` \| `MD5` | Hash algorithm. |
| `saltColumn` | no | `string<column_name>` | Any valid column name | Per-row salt source column added before hashing. |
| `pepper` | no | `string<any>` | Any static text value (including empty string) | Static pepper value added before hashing. |
| `ignoreEmpty` | yes | `boolean` | `true` \| `false` | Whether empty input values are ignored/skipped. |

## Canonical Variants

### Single-column pseudonymization with SHA-256

```json
{
  "type": "ColumnPseudonymization",
  "params": {
    "pepper": "blah",
    "columns": ["long_text"],
    "ignoreEmpty": false,
    "appliesTo": "SINGLE_COLUMN",
    "saltColumn": "id",
    "algorithm": "SHA256"
  }
}
```

### Multi-column pseudonymization with SHA-512 and empty-value ignore

```json
{
  "type": "ColumnPseudonymization",
  "params": {
    "pepper": "blah",
    "columns": ["long_text", "fake_email"],
    "ignoreEmpty": true,
    "appliesTo": "COLUMNS",
    "saltColumn": "id",
    "algorithm": "SHA512"
  }
}
```

### All-columns pseudonymization with MD5

```json
{
  "type": "ColumnPseudonymization",
  "params": {
    "pepper": "blah",
    "columns": ["long_text", "fake_email"],
    "ignoreEmpty": false,
    "appliesTo": "ALL",
    "saltColumn": "id",
    "algorithm": "MD5"
  }
}
```

## Update Guidance

1. Read existing payload first and keep unrelated top-level keys untouched.
2. Modify only target `steps[]` entries for `ColumnPseudonymization`.
3. Keep `saltColumn` and `pepper` stable across datasets when hashed values must match for joins/lookups.
4. Keep scope params coherent (`appliesTo`, `columns`, `appliesToPattern`).

## References

- Dataiku DSS: Column pseudonymization (Options)  
  https://doc.dataiku.com/dss/latest/preparation/processors/column-pseudonymization.html#column-pseudonymization
