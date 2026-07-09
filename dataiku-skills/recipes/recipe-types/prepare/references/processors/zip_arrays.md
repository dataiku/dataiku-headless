---
name: prepare-zip-arrays
description: "Observed JSON patterns for the ZipArrays prepare/shaker processor."
---

# ZipArrays Processor

Combine N input columns containing arrays (as JSON) into a single output column.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `inputColumns` | yes | `list<string<column_name>>` | Any valid ordered list of input column names | Column order determines pairing in output. |
| `outputColumn` | yes | `string<column_name>` | Any valid output column name | Column containing the combined array/object structure. |

## Canonical Variant

```json
{
  "type": "ZipArrays",
  "params": {
    "inputColumns": ["fake_tags_array", "fake_scores_array"],
    "outputColumn": "fake_tags_scores_arrays"
  }
}
```

## Update Guidance

1. Read existing payload first and keep unrelated top-level keys untouched.
2. Modify only target `steps[]` entries for `ZipArrays`.
3. Preserve `inputColumns` order because it determines how values are paired in output.
4. Use a distinct `outputColumn` name to avoid overwriting input columns or prior derived outputs.
