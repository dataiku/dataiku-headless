# FillEmptyWithValue

**When:** Fill null/blank cells with a default value. Prefer over GREL `if(isBlank(x), "0", x)`.

**CLI shortcut:** `dku recipe add-fill-empty RECIPE --column age --value "0" -P PROJ`

| Param | Required | Description |
|-------|----------|-------------|
| `appliesTo` | Yes | `SINGLE_COLUMN` |
| `columns` | Yes | `["col_name"]` |
| `value` | Yes | Fill value (string) |

```json
{"appliesTo": "SINGLE_COLUMN", "columns": ["age"], "value": "0"}
```
