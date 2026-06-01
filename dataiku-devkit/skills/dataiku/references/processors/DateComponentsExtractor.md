# DateComponentsExtractor

**When:** Extract year, month, day, hour, etc. from a parsed date column. Prefer over GREL `year()`, `month()`.

**CLI shortcut:** `dku recipe add-step RECIPE --type DateComponentsExtractor --params '{"column":"order_date","timezone_id":"UTC","outYearColumn":"order_year","outMonthColumn":"order_month","outDayColumn":"order_day"}' -P PROJ`

| Param | Required | Description |
|-------|----------|-------------|
| `column` | Yes | Input date column (must be parsed ISO-8601) |
| `timezone_id` | Yes | `"UTC"` or IANA timezone |
| `outYearColumn` | No | Output column for year (empty = skip) |
| `outMonthColumn` | No | Output column for month |
| `outDayColumn` | No | Output column for day-of-month |
| `outHourColumn` | No | Output column for hour |
| `outDayOfWeekColumn` | No | Output column for day-of-week |
| `outWeekOfYearColumn` | No | Output column for week-of-year |

```json
{"column": "order_date", "timezone_id": "UTC", "outYearColumn": "order_year", "outMonthColumn": "order_month", "outDayColumn": "order_day"}
```
