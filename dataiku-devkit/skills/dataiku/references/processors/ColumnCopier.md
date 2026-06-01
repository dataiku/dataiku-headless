# ColumnCopier

**When:** Copy a column's values to a new column. Prefer over GREL `column_name` identity expression.

**CLI shortcut:** `dku recipe add-step RECIPE --type ColumnCopier --params '{"inputColumn":"status","outputColumn":"status_bak"}' -P PROJ`

| Param | Required | Description |
|-------|----------|-------------|
| `inputColumn` | Yes | Source column |
| `outputColumn` | Yes | New column name |

```json
{"inputColumn": "status", "outputColumn": "status_backup"}
```
