---
name: prepare-array-sort-processor
description: "Observed JSON patterns for the ArraySortProcessor prepare/shaker processor."
---

# ArraySortProcessor Processor

Sort values inside an array-valued column (numerically or alphabetically, ascending or descending).

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `input` | yes | `string<column_name>` | Any valid array-valued input column name | Source column containing array values to sort. |
| `sortingType` | yes | `enum` | `NUM` \| `ALPHA` | Numeric sort or alphabetical sort mode. |
| `descending` | yes | `boolean` | `true` \| `false` | `false` for ascending, `true` for descending order. |
| `output` | yes | `string<column_name>` \| `""` | Any valid output column name \| empty string | Empty string applies sorting in-place on `input`; non-empty writes to output column. |

## Canonical Variants

### Numeric ascending sort in-place

```json
{
  "type": "ArraySortProcessor",
  "params": {
    "output": "",
    "input": "fake_scores_array",
    "sortingType": "NUM",
    "descending": false
  }
}
```

### Reverse alphabetical sort to new output column

```json
{
  "type": "ArraySortProcessor",
  "params": {
    "output": "fake_tags_array_sorted",
    "input": "fake_tags_array",
    "sortingType": "ALPHA",
    "descending": true
  }
}
```

## Update Guidance

1. Read existing payload first and keep unrelated top-level keys untouched.
2. Modify only target `steps[]` entries for `ArraySortProcessor`.
3. Keep `sortingType` consistent with array content (`NUM` for numeric values, `ALPHA` for string values).
4. Use `output: ""` only when in-place overwrite is intended.

## References

- Dataiku DSS: Sort array (Options)  
  https://doc.dataiku.com/dss/latest/preparation/processors/array-sort.html
