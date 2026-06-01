# BinnerProcessor

**When:** Discretize numbers into bins (age groups, price ranges). Prefer over GREL `if` chains.

**CLI shortcut:** `dku recipe add-step RECIPE --type BinnerProcessor --params '{"input":"age","output":"age_group","mode":"WIDTH","width":10.0,"bins":[]}' -P PROJ`

| Param | Required | Description |
|-------|----------|-------------|
| `input` | Yes | Source numeric column |
| `output` | Yes | Output column (empty = in-place) |
| `mode` | Yes | `WIDTH` (fixed width) or `CUSTOM` (manual ranges) |
| `width` | Cond | Bin width (for `WIDTH` mode) |
| `bins` | Cond | Array of `{"inf": 0, "sup": 25}` (for `CUSTOM` mode) |
| `useMin`/`min` | No | Enforce minimum bound |
| `useMax`/`max` | No | Enforce maximum bound |
| `useDecimalSeparatorFromLocale` | No | When true, render bin labels using the user's locale decimal separator |

```json
{"input": "age", "output": "age_group", "mode": "WIDTH", "width": 10.0, "bins": [], "useMin": false, "min": 0.0, "useMax": false, "max": 0.0}
```
