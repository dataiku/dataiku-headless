---
name: prepare-array-fold
description: "Observed JSON patterns for the ArrayFold prepare/shaker processor."
---

# ArrayFold Processor

Transform a cell containing a JSON array and fold it into several rows, performing the transformation in-place. Each generated row contains a single value from the input array. All other columns are copied in each generated row.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `column` | yes | `string<column_name>` | Any valid array-valued input column name | Source column containing array values to unfold into rows. |

## Canonical Variant

```json
{
  "type": "ArrayFold",
  "params": {
    "column": "fake_tags_array"
  }
}
```

## Update Guidance

1. Read existing payload first and keep unrelated top-level keys untouched.
2. Modify only target `steps[]` entries for `ArrayFold`.
3. Ensure `column` is array-valued before folding to avoid unexpected output behavior.
4. Re-check downstream steps because folding changes row cardinality.

## References

- Dataiku DSS: Fold an array (Options)  
  https://doc.dataiku.com/dss/latest/preparation/processors/array-fold.html
