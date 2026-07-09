---
name: prepare-binner-processor
description: "Observed JSON patterns for the BinnerProcessor prepare/shaker processor."
---

# BinnerProcessor Processor

Discretize numerical values into bins using either fixed width or custom ranges.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `input` | yes | `string<column_name>` | Any valid numeric input column name | Source column with values to discretize. |
| `mode` | yes | `enum` | `WIDTH` \| `CUSTOM` | Binning strategy: fixed width or explicit bin ranges. |
| `output` | yes | `string<column_name>` \| `""` | Any valid output column name \| empty string | Empty string performs operation in place; non-empty writes to output column. |
| `width` | conditional | `number` | Any positive number | Used for `WIDTH` mode. |
| `useMin` | yes | `boolean` | `true` \| `false` | Whether a minimum bound is enforced. |
| `min` | conditional | `number` | Any number | Minimum boundary value when `useMin=true`. |
| `useMax` | yes | `boolean` | `true` \| `false` | Whether a maximum bound is enforced. |
| `max` | conditional | `number` | Any number | Maximum boundary value when `useMax=true`. |
| `bins` | yes | `list<object<{inf:number, sup:number, name:string<any>}>>` | Empty list for `WIDTH`, explicit range list for `CUSTOM` | Each custom bin object uses `inf`/`sup` boundaries and an optional `name` custom label (overrides the auto-generated `inf : sup` range string). |
| `useDecimalSeparatorFromLocale` | yes | `boolean` | `true` \| `false` | Locale-aware parsing toggle for decimal separator behavior. |

## Canonical Variants

### Fixed-width bins (10-unit buckets)

```json
{
  "type": "BinnerProcessor",
  "params": {
    "output": "age_10_yr_bins",
    "mode": "WIDTH",
    "input": "age",
    "useMin": false,
    "bins": [],
    "min": 0.0,
    "useDecimalSeparatorFromLocale": false,
    "max": 0.0,
    "useMax": false,
    "width": 10.0
  }
}
```

### Fixed-width bins with explicit min/max bounds

```json
{
  "type": "BinnerProcessor",
  "params": {
    "output": "age_10_yr_bins",
    "mode": "WIDTH",
    "input": "age",
    "useMin": true,
    "bins": [],
    "min": 0.0,
    "useDecimalSeparatorFromLocale": false,
    "max": 100.0,
    "useMax": true,
    "width": 10.0
  }
}
```

### Custom bins (in-place)

```json
{
  "type": "BinnerProcessor",
  "params": {
    "output": "",
    "mode": "CUSTOM",
    "input": "age",
    "useMin": true,
    "bins": [
      {"inf": 0.0, "sup": 25.0},
      {"inf": 26.0, "sup": 35.0},
      {"inf": 36.0, "sup": 55.0},
      {"inf": 56.0, "sup": 80.0},
      {"inf": 81.0, "sup": 100.0}
    ],
    "min": 0.0,
    "useDecimalSeparatorFromLocale": false,
    "max": 100.0,
    "useMax": true,
    "width": 10.0
  }
}
```

## Update Guidance

1. Read existing payload first and keep unrelated top-level keys untouched.
2. Modify only target `steps[]` entries for `BinnerProcessor`.
3. Keep `mode` coherent with bin definition fields (`WIDTH` with `width`; `CUSTOM` with `bins` ranges).
4. Align `useMin`/`useMax` flags with `min`/`max` boundaries to avoid unintended overflow buckets.
5. Use `output: ""` only when overwriting the source column is intentional.

## References

- Dataiku DSS: Bin numerical values (Options)  
  https://doc.dataiku.com/dss/latest/preparation/processors/binner.html
