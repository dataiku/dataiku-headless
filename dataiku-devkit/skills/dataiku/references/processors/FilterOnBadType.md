# FilterOnBadType

**When:** Remove rows where values don't match expected type (e.g. non-numeric in a number column).

**CLI shortcut:** `dku recipe add-step RECIPE --type FilterOnBadType --params '{"appliesTo":"SINGLE_COLUMN","columns":["price"],"type":"DoubleMeaning","action":"REMOVE_ROW","considerEmptyAsInvalid":false,"booleanMode":"AND"}' -P PROJ`

| Param | Required | Description |
|-------|----------|-------------|
| `appliesTo` | Yes | Scope (SINGLE_COLUMN, COLUMNS) |
| `columns` | Yes | `["col_name"]` |
| `action` | Yes | `REMOVE_ROW`, `KEEP_ROW`, `CLEAR_CELL` |
| `type` | Yes | `DoubleMeaning`, `LongMeaning`, `Date`, `Boolean`, `Email`, `URL`, `IPAddress` |
| `considerEmptyAsInvalid` | Yes | `true`/`false` |
| `booleanMode` | Yes | `AND` |

```json
{"appliesTo": "SINGLE_COLUMN", "columns": ["price"], "action": "REMOVE_ROW", "type": "DoubleMeaning", "considerEmptyAsInvalid": false, "booleanMode": "AND"}
```
