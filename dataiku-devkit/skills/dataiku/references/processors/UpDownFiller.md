# UpDownFiller

**When:** Fill null/empty cells with the previous non-null value (fill down) or next non-null value (fill up). For last-observation-carried-forward (LOCF) and next-observation-carried-backward (NOCB) imputation.

**CLI shortcut:** `dku recipe add-step RECIPE --type UpDownFiller --params '{"appliesTo":"SINGLE_COLUMN","columns":["value"],"direction":"DOWN"}' -P PROJ`

| Param | Required | Description |
|-------|----------|-------------|
| `appliesTo` | Yes | `SINGLE_COLUMN` or `COLUMNS` |
| `columns` | Yes | Array of column names to fill |
| `direction` | Yes | `DOWN` (fill with previous value) or `UP` (fill with next value) |

```json
{"appliesTo": "SINGLE_COLUMN", "columns": ["value"], "direction": "DOWN"}
```
