# FlagOnValue

**When:** Filter/flag rows matching specific values. Prefer over GREL `if(col == "x", ...)`.

**CLI shortcut:** `dku recipe add-filter-rows RECIPE --column status --values "active,pending" --action KEEP_ROW -P PROJ`

| Param | Required | Description |
|-------|----------|-------------|
| `appliesTo` | Yes | `SINGLE_COLUMN` |
| `columns` | Yes | `["col_name"]` |
| `values` | Yes | Array of values to match |
| `action` | Yes | `KEEP_ROW`, `REMOVE_ROW`, `FLAG` |
| `matchingMode` | Yes | `FULL_STRING`, `SUBSTRING`, `PATTERN` |
| `normalizationMode` | Yes | `EXACT`, `LOWERCASE`, `NORMALIZED` |
| `booleanMode` | Yes | `AND` or `OR` |

```json
{"appliesTo": "SINGLE_COLUMN", "columns": ["status"], "values": ["active", "pending"], "action": "KEEP_ROW", "matchingMode": "FULL_STRING", "normalizationMode": "EXACT", "booleanMode": "AND"}
```

For `FLAG` action:
```json
{"appliesTo": "SINGLE_COLUMN", "columns": ["status"], "values": ["active"], "action": "FLAG", "flagColumn": "is_active", "matchingMode": "FULL_STRING", "normalizationMode": "EXACT", "booleanMode": "AND", "exclude": false, "processNullOrEmptyValues": false}
```
