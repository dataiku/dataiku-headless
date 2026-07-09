---
name: prepare-min-max-processor
description: "Observed JSON patterns for the MinMaxProcessor prepare/shaker processor."
---

# MinMaxProcessor

Force numerical values to stay within a range by clipping out-of-range values, or clear out-of-range values instead.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `columns` | yes | `list<string<column_name>>` | Any valid list of numeric column names | Target column(s) whose values are range-constrained. |
| `lowerBound` | conditional | `string<number_literal>` | Any numeric lower bound as text | Inclusive lower bound. At least one of `lowerBound` or `upperBound` must be set. |
| `upperBound` | conditional | `string<number_literal>` | Any numeric upper bound as text | Inclusive upper bound. At least one of `lowerBound` or `upperBound` must be set. |
| `clear` | yes | `boolean` | `true` \| `false` | `false`: clip out-of-range values to nearest bound. `true`: clear out-of-range values instead of clipping. |

## Canonical Variants

### Clip values outside both bounds

```json
{
  "type": "MinMaxProcessor",
  "params": {
    "columns": ["age"],
    "lowerBound": "0",
    "upperBound": "120",
    "clear": false
  }
}
```

### Clear values below lower bound

```json
{
  "type": "MinMaxProcessor",
  "params": {
    "columns": ["score", "event_count"],
    "lowerBound": "0",
    "clear": true
  }
}
```

### Clip values above upper bound

```json
{
  "type": "MinMaxProcessor",
  "params": {
    "columns": ["event_count"],
    "upperBound": "500",
    "clear": false
  }
}
```

## Update Guidance

1. Read existing payload first and keep unrelated top-level keys untouched.
2. Modify only target `steps[]` entries for `MinMaxProcessor`.
3. Set at least one bound (`lowerBound` or `upperBound`); set both for a closed interval.
4. Confirm `clear` behavior before execution (`false` clip vs `true` clear).

## References

- Dataiku DSS: Force numerical range (Options)  
  https://doc.dataiku.com/dss/latest/preparation/processors/number-clipping.html#force-numerical-range
