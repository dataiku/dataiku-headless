# ColumnSplitter

**When:** Split a column by delimiter into multiple columns. Prefer over GREL `split()`.

**CLI shortcut:** `dku recipe add-step RECIPE --type ColumnSplitter --params '{"inCol":"full_name","separator":" ","outColPrefix":"name_","target":"COLUMNS","keepEmptyChunks":false,"limitOutput":false,"limit":0}' -P PROJ`

| Param | Required | Description |
|-------|----------|-------------|
| `inCol` | Yes | Input column |
| `separator` | Yes | Delimiter string |
| `outColPrefix` | Yes | Prefix for generated columns (e.g. `name_0`, `name_1`) |
| `target` | Yes | `COLUMNS` (separate cols) or `JSON` (JSON array) |
| `keepEmptyChunks` | Yes | `false` = skip empty |
| `limitOutput` | Yes | `true` = limit to N chunks |
| `limit` | Yes | Max chunks (0 = unlimited) |
| `startFrom` | Cond | **Required when `limitOutput: true`.** `"beginning"` or `"end"` (lowercase only — `"BEGINNING"` fails). Set to `null` when `limitOutput: false`. |

```json
{"inCol": "full_name", "separator": " ", "outColPrefix": "name_", "target": "COLUMNS", "keepEmptyChunks": false, "limitOutput": false, "limit": 0, "startFrom": "beginning"}
```

With `limitOutput`:
```json
{"inCol": "notes", "separator": " - ", "outColPrefix": "notes_", "target": "COLUMNS", "keepEmptyChunks": false, "limitOutput": true, "limit": 2, "startFrom": "beginning"}
```
