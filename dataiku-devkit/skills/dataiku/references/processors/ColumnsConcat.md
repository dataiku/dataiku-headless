# ColumnsConcat

**When:** Concatenate multiple columns with a delimiter. Prefer over GREL `col1 + " " + col2`.

**CLI shortcut:** `dku recipe add-step RECIPE --type ColumnsConcat --params '{"columns":["first","last"],"join":" ","outputColumn":"full_name"}' -P PROJ`

| Param | Required | Description |
|-------|----------|-------------|
| `columns` | Yes | Input columns in order |
| `join` | Yes | Delimiter string (can be empty) |
| `outputColumn` | Yes | Output column name |

```json
{"outputColumn": "full_address", "columns": ["street", "city", "state"], "join": ", "}
```
