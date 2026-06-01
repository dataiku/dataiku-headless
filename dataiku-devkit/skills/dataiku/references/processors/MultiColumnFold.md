# MultiColumnFold

**When:** Unpivot wide-to-long. Prefer over `pd.melt()`. Stock DSS — works on every instance.

**CLI shortcut:** `dku recipe add-fold RECIPE --columns "jan,feb,mar" --key-column month --value-column sales -P PROJ`

| Param | Required | Description |
|-------|----------|-------------|
| `columns` | Yes | Array of column names to fold |
| `foldNameColumn` | Yes | Output column for original column names |
| `foldValueColumn` | Yes | Output column for values |
| `foldRemoveFoldedColumns` | No | `true` to drop the folded source columns (pd.melt semantic); `false`/omit to keep them |

```json
{"columns": ["jan", "feb", "mar"], "foldNameColumn": "month", "foldValueColumn": "sales", "foldRemoveFoldedColumns": true}
```
