# FindReplace

**When:** Find and replace values in a column. Prefer over GREL `replace()`.

**CLI shortcut:** `dku recipe add-find-replace RECIPE --column city --find "NYC" --replace "New York" -P PROJ`

| Param | Required | Description |
|-------|----------|-------------|
| `appliesTo` | Yes | `SINGLE_COLUMN` |
| `columns` | Yes | `["col_name"]` |
| `mapping` | Yes | Array of `{"from": "old", "to": "new"}` |
| `matching` | Yes | `FULL_STRING`, `SUBSTRING`, `PATTERN` (regex) |
| `normalization` | Yes | `EXACT`, `LOWERCASE`, `NORMALIZED` |
| `output` | Yes | `""` (in-place) or output column name |

```json
{"appliesTo": "SINGLE_COLUMN", "columns": ["category"], "output": "", "mapping": [{"from": "Electronics", "to": "Tech"}], "matching": "FULL_STRING", "normalization": "EXACT"}
```
