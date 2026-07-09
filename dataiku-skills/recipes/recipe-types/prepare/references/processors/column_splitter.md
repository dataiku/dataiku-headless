---
name: prepare-column-splitter
description: "Observed JSON patterns for the ColumnSplitter prepare/shaker processor."
---

# ColumnSplitter Processor

Split a column into several columns (or an array) on each occurrence of a delimiter.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `inCol` | yes | `string<column_name>` | Any valid input column name | Input column to split. |
| `separator` | yes | `string<any>` | Any delimiter text | Delimiter used to split the input value. |
| `outColPrefix` | yes | `string<any>` | Any output prefix string | Prefix for generated output columns (for example `prefix_0`, `prefix_1`, ...). |
| `target` | yes | `enum` | `COLUMNS` \| `JSON` | Output mode: separate columns or JSON array. |
| `keepEmptyChunks` | yes | `boolean` | `true` \| `false` | Preserves empty chunks between consecutive delimiters when `true`. |
| `limitOutput` | yes | `boolean` | `true` \| `false` | Enables output truncation to first/last N chunks. |
| `limit` | yes | `integer` | Any integer `>= 0` | Number of chunks to keep when `limitOutput=true`; observed `0` when truncation is disabled. |
| `startFrom` | conditional | `enum` | `beginning` \| `end` | Required when `limitOutput=true`; keeps first or last N chunks. |

## Canonical Variants

### Split to multiple columns

```json
{
  "type": "ColumnSplitter",
  "params": {
    "inCol": "signup_date",
    "separator": "-",
    "outColPrefix": "signup_date_",
    "target": "COLUMNS",
    "keepEmptyChunks": false,
    "limitOutput": false,
    "limit": 0
  }
}
```

### Split to JSON array

```json
{
  "type": "ColumnSplitter",
  "params": {
    "inCol": "full_name",
    "separator": " ",
    "outColPrefix": "full_name_",
    "target": "JSON",
    "keepEmptyChunks": true,
    "limitOutput": false,
    "limit": 1,
    "startFrom": "beginning"
  }
}
```

### Truncate to first N chunks

```json
{
  "type": "ColumnSplitter",
  "params": {
    "inCol": "full_name",
    "separator": " ",
    "outColPrefix": "full_name_",
    "target": "COLUMNS",
    "keepEmptyChunks": false,
    "limitOutput": true,
    "limit": 2,
    "startFrom": "beginning"
  }
}
```

### Truncate to last N chunks

```json
{
  "type": "ColumnSplitter",
  "params": {
    "inCol": "full_name",
    "separator": " ",
    "outColPrefix": "full_name_",
    "target": "COLUMNS",
    "keepEmptyChunks": false,
    "limitOutput": true,
    "limit": 2,
    "startFrom": "end"
  }
}
```

## Update Guidance

1. Read existing payload first and keep unrelated top-level keys untouched.
2. Modify only target `steps[]` entries for `ColumnSplitter`.
3. Keep `limitOutput`, `limit`, and `startFrom` coherent to avoid accidental truncation behavior.
4. Ensure `target` matches downstream expectations (`COLUMNS` vs `JSON` array output).

## References

- Dataiku DSS: Split column (Options)  
  https://doc.dataiku.com/dss/latest/preparation/processors/split.html#split-column
