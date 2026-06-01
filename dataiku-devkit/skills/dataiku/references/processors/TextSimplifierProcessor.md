# TextSimplifierProcessor

**When:** Normalize text with stemming, stop-word removal, and sorting. For NLP preprocessing.

**CLI shortcut:** `dku recipe add-step RECIPE --type TextSimplifierProcessor --params '{"inCol":"description","outCol":"description_clean","normalize":true,"stem":false,"clearStopWords":true,"sortAlphabetically":false,"language":"english"}' -P PROJ`

| Param | Required | Description |
|-------|----------|-------------|
| `inCol` | Yes | Input text column |
| `outCol` | No | Output column (empty = in-place) |
| `normalize` | Yes | Lowercase + remove punctuation/accents |
| `stem` | Yes | Language-specific stemming |
| `clearStopWords` | Yes | Remove stop words |
| `sortAlphabetically` | Yes | Sort tokens alphabetically |
| `language` | Yes | `english`, `french`, `german`, `spanish`, etc. |

```json
{"inCol": "description", "outCol": "description_clean", "normalize": true, "stem": false, "clearStopWords": true, "sortAlphabetically": false, "language": "english"}
```
