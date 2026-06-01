# FilterOnNumericalRange

**When:** Keep/remove rows where a numeric column is within a range.

**CLI shortcut:** `dku recipe add-step RECIPE --type FilterOnNumericalRange --params '{"appliesTo":"SINGLE_COLUMN","columns":["age"],"action":"KEEP_ROW","min":18.0,"max":65.0,"booleanMode":"AND"}' -P PROJ`

| Param | Required | Description |
|-------|----------|-------------|
| `appliesTo` | Yes | `SINGLE_COLUMN` |
| `columns` | Yes | `["col_name"]` |
| `action` | Yes | `KEEP_ROW`, `REMOVE_ROW` |
| `min` | Yes | Lower bound (inclusive) |
| `max` | Yes | Upper bound (inclusive) |
| `booleanMode` | Yes | `AND` |

```json
{"appliesTo": "SINGLE_COLUMN", "columns": ["age"], "action": "KEEP_ROW", "min": 18.0, "max": 65.0, "booleanMode": "AND"}
```
