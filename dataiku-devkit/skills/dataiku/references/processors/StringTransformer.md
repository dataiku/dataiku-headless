# StringTransformer

**When:** Uppercase, lowercase, trim, normalize, or truncate text. Prefer over GREL `toUppercase()`, `toLowercase()`, `trim()`.

**CLI shortcut:** `dku recipe add-step RECIPE --type StringTransformer --params '{"mode":"TO_UPPER","appliesTo":"SINGLE_COLUMN","columns":["city"]}' -P PROJ`

| Param | Required | Description |
|-------|----------|-------------|
| `mode` | Yes | `TO_UPPER`, `TO_LOWER`, `TRIM`, `NORMALIZE`, `TRUNCATE` |
| `appliesTo` | Yes | Scope (SINGLE_COLUMN, COLUMNS, ALL) |
| `columns` | Yes | `["col_name"]` |
| `truncate_limit` | Cond | Integer max length (required when `mode: TRUNCATE`) |

```json
{"mode": "TO_UPPER", "appliesTo": "SINGLE_COLUMN", "columns": ["city"]}
```

**Note:** Use `TO_UPPER`/`TO_LOWER`, NOT `UPPERCASE`/`LOWERCASE`. Wrong values produce a runtime NullPointerException at build time. No `TITLECASE` mode — use GREL `toTitlecase(col)`.
