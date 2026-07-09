---
name: prepare-array-extract-processor
description: "Observed JSON patterns for the ArrayExtractProcessor prepare/shaker processor."
---

# ArrayExtractProcessor Processor

Extract one element or a contiguous sub-array from an array-valued column.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `input` | yes | `string<column_name>` | Any valid input column name | Source column containing array-like values. |
| `mode` | yes | `enum` | `INDEX` \| `RANGE` | Extraction mode: single element or sub-array slice. |
| `index` | yes | `integer` | Any integer `>= 0` | Element index used for `INDEX` mode. Seen in both modes in live payloads. |
| `begin` | conditional | `integer` | Any integer `>= 0` | Range start index (inclusive) for `RANGE` mode. May still appear in `INDEX` mode payloads. |
| `end` | conditional | `integer` | Any integer `>= 0` | Range end index (exclusive or DSS-processor-defined boundary) for `RANGE` mode. May still appear in `INDEX` mode payloads. |
| `output` | no | `string<column_name>` \| `""` | Any valid output column name \| empty/omitted | When provided, writes extracted result to a separate output column. |

## Canonical Variants

### Extract one element by index

```json
{
  "type": "ArrayExtractProcessor",
  "params": {
    "mode": "INDEX",
    "input": "fake_tags_array",
    "index": 0,
    "end": 0,
    "begin": 0
  }
}
```

### Extract a range to a new output column

```json
{
  "type": "ArrayExtractProcessor",
  "params": {
    "output": "fake_scores_sub_array_extracted",
    "mode": "RANGE",
    "input": "fake_scores_array",
    "index": 0,
    "end": 3,
    "begin": 1
  }
}
```

## Update Guidance

1. Read existing payload first and keep unrelated top-level keys untouched.
2. Modify only target `steps[]` entries for `ArrayExtractProcessor`.
3. Keep `mode` aligned with index fields: `INDEX` for one element, `RANGE` for sub-array extraction.
4. Preserve existing `begin`/`end`/`index` fields unless intentionally changing extraction boundaries.
5. Set `output` explicitly when downstream steps require a dedicated extracted column.

## References

- Dataiku DSS: Extract from array (Options)  
  https://doc.dataiku.com/dss/latest/preparation/processors/array-extract.html
