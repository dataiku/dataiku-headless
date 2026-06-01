# ColumnsSelector

**When:** Delete or keep specific columns. Prefer over GREL.

**CLI shortcut:** `dku recipe add-delete-columns RECIPE --columns "tmp1,tmp2" -P PROJ`

| Param | Required | Description |
|-------|----------|-------------|
| `appliesTo` | Yes | `COLUMNS` |
| `columns` | Yes | Array of column names |
| `keep` | Yes | `false` = delete listed, `true` = keep only listed |

```json
{"appliesTo": "COLUMNS", "columns": ["debug_col", "temp_id"], "keep": false}
```

> **`keep: true` does NOT reorder.** It filters the schema to the listed columns and preserves their on-disk order, which is the input order — not the order in your `columns` array. To impose a final column order, use `ColumnReorder`.
