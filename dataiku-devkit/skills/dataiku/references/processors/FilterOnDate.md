# FilterOnDate

**When:** Keep/remove rows where a date column falls within a date range.

**CLI shortcut:** `dku recipe add-step RECIPE --type FilterOnDate --params '{"appliesTo":"SINGLE_COLUMN","columns":["order_date"],"filterType":"RANGE","min":"2024-01-01T00:00:00.000Z","max":"2024-12-31T23:59:59.000Z","action":"KEEP_ROW","timezone_id":"UTC"}' -P PROJ`

| Param | Required | Description |
|-------|----------|-------------|
| `appliesTo` | Yes | `SINGLE_COLUMN` |
| `columns` | Yes | `["col_name"]` |
| `filterType` | Yes | `RANGE` or other date filter type |
| `min` | Yes | Minimum date (ISO-8601 string with milliseconds) |
| `max` | Yes | Maximum date (ISO-8601 string with milliseconds) |
| `action` | Yes | `KEEP_ROW`, `REMOVE_ROW` |
| `timezone_id` | Yes | `"UTC"` or IANA timezone |
| `includeEmptyValues` | No | Whether to include rows with null/empty dates |

```json
{"appliesTo": "SINGLE_COLUMN", "columns": ["order_date"], "filterType": "RANGE", "min": "2024-01-01T00:00:00.000Z", "max": "2024-12-31T23:59:59.000Z", "action": "KEEP_ROW", "timezone_id": "UTC", "includeEmptyValues": false}
```
