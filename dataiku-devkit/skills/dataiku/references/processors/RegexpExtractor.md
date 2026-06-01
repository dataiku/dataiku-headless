# RegexpExtractor

**When:** Extract text matching a regular expression pattern from a column. Prefer over GREL `find()` or `match()`.

**CLI shortcut:** `dku recipe add-step RECIPE --type RegexpExtractor --params '{"inCol":"description","pattern":"(\\\\d{3}-\\\\d{2}-\\\\d{4})","output":"ssn"}' -P PROJ`

| Param | Required | Description |
|-------|----------|-------------|
| `inCol` | Yes | Input text column |
| `output` | Yes | Output column name |
| `pattern` | Yes | Regex pattern (Java syntax). Use capturing groups to extract specific parts |
| `groupNum` | No | Capturing group index to extract (0 = full match, 1 = first group). Default 0 |
| `caseSensitive` | No | `true` (default) or `false` |
| `multiLine` | No | `true` enables `^`/`$` across lines |

```json
{"inCol": "description", "output": "extracted_phone", "pattern": "(\\d{3}-\\d{3}-\\d{4})", "groupNum": 1, "caseSensitive": false}
```
