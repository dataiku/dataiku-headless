# RemoveRowsOnEmpty

**When:** Remove rows with empty/null values.

**CLI shortcut:** `dku recipe add-step RECIPE --type RemoveRowsOnEmpty --params '{"appliesTo":"ALL","columns":[],"keep":false}' -P PROJ`

| Param | Required | Description |
|-------|----------|-------------|
| `appliesTo` | Yes | `SINGLE_COLUMN`, `COLUMNS`, or `ALL` |
| `columns` | Yes | Column(s) to check |
| `keep` | Yes | `false` = remove empty rows, `true` = keep only empty |

```json
{"appliesTo": "ALL", "columns": [], "keep": false}
```
