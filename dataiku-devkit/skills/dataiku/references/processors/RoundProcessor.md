# RoundProcessor

**When:** Round numeric values to a specified number of decimal places. Prefer over GREL `round()` which only rounds to the nearest integer.

**CLI shortcut:** `dku recipe add-step RECIPE --type RoundProcessor --params '{"appliesTo":"SINGLE_COLUMN","columns":["price"],"decimalPlaces":2}' -P PROJ`

| Param | Required | Description |
|-------|----------|-------------|
| `appliesTo` | Yes | `SINGLE_COLUMN` or `COLUMNS` |
| `columns` | Yes | Array of column names to round |
| `decimalPlaces` | Yes | Number of decimal places (integer) |

```json
{"appliesTo": "SINGLE_COLUMN", "columns": ["price"], "decimalPlaces": 2}
```
