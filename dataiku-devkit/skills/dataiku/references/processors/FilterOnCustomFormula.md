# FilterOnCustomFormula

**When:** Filter rows or clear cells based on a formula expression. Prefer over Python filtering.

**CLI shortcut:** `dku recipe add-filter-rows RECIPE --formula "price > 100" --action REMOVE_ROW -P PROJ`

| Param | Required | Description |
|-------|----------|-------------|
| `expression` | Yes | DSS formula expression |
| `action` | Yes | `KEEP_ROW`, `REMOVE_ROW`, `CLEAR_CELL`, `DONTCLEAR_CELL` |
| `clearColumn` | Cond | Required for `CLEAR_CELL` / `DONTCLEAR_CELL` |

```json
{"expression": "age > 65", "action": "REMOVE_ROW"}
```

> Always use `FilterOnCustomFormula` (not `FilterOnFormula`) — the latter is a plugin type that may not be installed and will fail with `UnavailableTypeException`.
