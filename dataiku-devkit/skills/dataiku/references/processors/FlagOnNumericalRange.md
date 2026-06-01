# FlagOnNumericalRange

**When:** Add a boolean flag column when a numeric value falls in `[min, max]`. Pair with downstream Window/Group: e.g. `uptime_ratio = sum(machine_idle_flag) / count`.

**CLI shortcut:** `dku recipe add-step RECIPE --type FlagOnNumericalRange --params '{"appliesTo":"SINGLE_COLUMN","columns":["Floatvalue"],"min":-5.0,"max":5.0,"action":"FLAG","flagColumn":"machine_idle","booleanMode":"AND","includeEmptyValues":false}' -P PROJ`

| Param | Required | Description |
|-------|----------|-------------|
| `appliesTo`, `columns` | Yes | Standard scope params |
| `min`, `max` | Yes | Numeric bounds |
| `action` | Yes | `FLAG` (write a boolean column) — distinct from `FilterOnNumericalRange` whose action is `KEEP_ROW` / `REMOVE_ROW` |
| `flagColumn` | Yes | Name of the boolean column to write |
| `booleanMode` | No | `AND` / `OR` when multiple columns are scoped |
| `includeEmptyValues` | No | Whether nulls count as in-range |

```json
{
  "appliesTo": "SINGLE_COLUMN",
  "columns": ["Floatvalue"],
  "min": -5.0,
  "max": 5.0,
  "action": "FLAG",
  "flagColumn": "machine_idle",
  "booleanMode": "AND",
  "includeEmptyValues": false
}
```
