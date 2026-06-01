# NumericalFormatConverter

**When:** Convert numerals between FR/US locales (decimal `,` ↔ `.`, thousand separator). Common Alteryx Multi-Field Formula replacement.

**CLI shortcut:** `dku recipe add-step RECIPE --type NumericalFormatConverter --params '{"appliesTo":"SINGLE_COLUMN","columns":["price_str"],"outCol":"price_us","inFormat":"FR","outFormat":"US"}' -P PROJ`

| Param | Required | Description |
|-------|----------|-------------|
| `appliesTo`, `columns` | Yes | Standard scope params |
| `outCol` | No | Output column (omit to overwrite input column) |
| `inFormat` | Yes | `FR`, `US`, or `RAW` |
| `outFormat` | Yes | `FR`, `US`, or `RAW` |

```json
{"appliesTo": "SINGLE_COLUMN", "columns": ["price_str"], "outCol": "price_us", "inFormat": "FR", "outFormat": "US"}
```
