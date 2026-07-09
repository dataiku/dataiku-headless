---
name: prepare-columns-concat
description: "Observed JSON patterns for the ColumnsConcat prepare/shaker processor."
---

# ColumnsConcat Processor

Concatenate values across columns using a delimiter string and produce a single output column.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `columns` | yes | `list<string<column_name>>` | Any valid ordered list of input column names | Input columns to concatenate, in order. |
| `join` | yes | `string<any>` | Any delimiter string (including empty string) | Delimiter inserted between concatenated values. |
| `outputColumn` | yes | `string<column_name>` | Any valid output column name | Column containing concatenated output values. |

## Canonical Variants

### Concatenate two columns with underscore delimiter

```json
{
  "type": "ColumnsConcat",
  "params": {
    "outputColumn": "id_full_name",
    "columns": ["id", "full_name"],
    "join": "_"
  }
}
```

### Concatenate three columns with space delimiter

```json
{
  "type": "ColumnsConcat",
  "params": {
    "outputColumn": "person_label",
    "columns": ["id", "full_name", "country"],
    "join": " "
  }
}
```

### Concatenate with no delimiter

```json
{
  "type": "ColumnsConcat",
  "params": {
    "outputColumn": "id_full_name_compact",
    "columns": ["id", "full_name"],
    "join": ""
  }
}
```

## Update Guidance

1. Read existing payload first and keep unrelated top-level keys untouched.
2. Modify only target `steps[]` entries for `ColumnsConcat`.
3. Keep `columns` ordering intentional, since output value order follows input order.
4. Keep `outputColumn` stable if downstream steps reference it.

## References

- Dataiku DSS: Concatenate columns (Options)  
  https://doc.dataiku.com/dss/latest/preparation/processors/columns-concat.html#concatenate-columns
