# DateIncrement

**When:** Add a fixed time delta to a date column (anonymization, projection scenarios).

**CLI shortcut:** `dku recipe add-step RECIPE --type DateIncrement --params '{"inCol":"start_date","outCol":"anon_start","datePart":"YEAR","incrementBy":"STATIC","increment":5}' -P PROJ`

| Param | Required | Description |
|-------|----------|-------------|
| `inCol` | Yes | Input date column |
| `outCol` | Yes | Output column |
| `datePart` | Yes | `YEAR` / `MONTH` / `DAY` / `HOUR` / `MINUTE` / `SECOND` |
| `incrementBy` | Yes | `STATIC` (constant offset) or `COLUMN` (per-row offset from `incrementCol`) |
| `increment` | If `STATIC` | Integer offset |
| `incrementCol` | If `COLUMN` | Column holding the per-row offset |

```json
{"inCol": "start_date", "outCol": "anon_start", "datePart": "YEAR", "incrementBy": "STATIC", "increment": 5}
```
