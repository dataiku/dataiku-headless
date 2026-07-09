---
name: prepare-pivot
description: "Observed JSON patterns for the Pivot prepare/shaker processor."
---

# Pivot Processor

Collapse rows sharing a sorted index into one row, turning each distinct label value into its own column filled by values column. Input must be pre-sorted on `indexColumn` (identical values contiguous) and read single-threaded; DSS engine only; not SQL-translatable.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `indexColumn` | yes | `string<column_name>` | Any existing column name | New output row on each value change. Input must be SORTED on this column and read single-threaded; null/empty index value triggers a flush. |
| `labelsColumn` | yes | `string<column_name>` | Any existing column name | Each distinct (trimmed) value becomes a new output column. Empty label values ignored. |
| `valuesColumn` | yes | `string<column_name>` | Any existing column name | Fills pivoted column for (index, label). Multiple rows sharing same index+label: last row's value wins. |
| `otherColumnsAction` | no | `enum` | `CLEAR` \| `KEEP_FIRST` \| `KEEP_IF_CONSTANT` \| `MAKE_ARRAY` | Treatment of non-pivoted columns. CLEAR=drop; KEEP_FIRST=keep first encountered value per index; KEEP_IF_CONSTANT=keep value only if single distinct value per index; MAKE_ARRAY=collect all values into JSON-array string. Form default `KEEP_IF_CONSTANT`. |

## Canonical Variant

```json
{
  "type": "Pivot",
  "params": {
    "labelsColumn": "category",
    "otherColumnsAction": "KEEP_IF_CONSTANT",
    "indexColumn": "pivot_index",
    "valuesColumn": "payload"
  }
}
```
