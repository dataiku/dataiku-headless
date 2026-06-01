# ColumnReorder

**When:** Force a specific column order in the output schema. Use after a `ColumnsSelector keep:true` if you also want to reorder, or anywhere you need to pin a column to a specific position.

**CLI shortcut:** `dku recipe add-reorder RECIPE -c col1 -c col2 --mode BEFORE_COLUMN --anchor existing_col -P PROJ`

| Param | Required | Description |
|-------|----------|-------------|
| `appliesTo` | Yes | `SINGLE_COLUMN` (one column) or `COLUMNS` (multiple columns). **Required** — the UI shows "Applies mode not selected" when missing, and the step renders as a no-op. |
| `columns` | Yes | Array of column names to move (in the order you want) |
| `referenceColumn` | When `reorderAction ∈ {BEFORE_COLUMN, AFTER_COLUMN}` | Anchor column — `columns` are placed relative to this one |
| `reorderAction` | Yes | `AT_THE_BEGINNING` / `AT_THE_END` / `BEFORE_COLUMN` / `AFTER_COLUMN` |

```json
{
  "appliesTo": "COLUMNS",
  "columns": ["customer_id", "order_date", "total"],
  "referenceColumn": "",
  "reorderAction": "AT_THE_BEGINNING"
}
```

For `BEFORE_COLUMN` / `AFTER_COLUMN`, set `referenceColumn` to the anchor; for `AT_THE_BEGINNING` / `AT_THE_END`, leave it empty. **Multi-column moves work correctly** when `appliesTo: COLUMNS` is set.
