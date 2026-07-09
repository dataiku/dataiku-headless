---
name: prepare-concat-arrays
description: "Observed JSON patterns for the ConcatArrays prepare/shaker processor."
---

# ConcatArrays Processor

Concatenate N input columns containing arrays (as JSON) into a single JSON array.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `inputColumns` | yes | `list<string<column_name>>` | Any valid ordered list of array-valued input column names | Arrays are concatenated in listed column order. |
| `outputColumn` | yes | `string<column_name>` | Any valid output column name | Column containing the concatenated array result. |

## Canonical Variant

```json
{
  "type": "ConcatArrays",
  "params": {
    "outputColumn": "fake_tags_scores_arrays_concat",
    "inputColumns": ["fake_tags_array", "fake_scores_array"]
  }
}
```

## Update Guidance

1. Read existing payload first and keep unrelated top-level keys untouched.
2. Modify only target `steps[]` entries for `ConcatArrays`.
3. Preserve `inputColumns` ordering because it determines output array ordering.
4. Use a distinct `outputColumn` if downstream steps still need the original arrays.

## References

- Dataiku DSS: Concatenate JSON Arrays (Options)  
  https://doc.dataiku.com/dss/latest/preparation/processors/arrays-concat.html
