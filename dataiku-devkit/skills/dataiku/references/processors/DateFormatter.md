# DateFormatter

**When:** Format an ISO-8601 date column into a custom string format (e.g. `MMM yyyy`, `yyyy-MM-dd`, `EEEE d MMMM`). Input must be a parsed date column — run `DateParser` first if the source is a string.

**CLI shortcut:** `dku recipe add-step RECIPE --type DateFormatter --params '{"inCol":"parsed_date","outCol":"month_label","format":"MMM yyyy","lang":"en_US","timezone_id":"UTC"}' -P PROJ`

| Param | Required | Description |
|-------|----------|-------------|
| `inCol` | Yes | Input column name (must be a parsed date/datetime column) |
| `outCol` | No | Output column name (omit or empty = in-place) |
| `format` | Yes | Java `SimpleDateFormat` pattern (`yyyy`, `MM`, `dd`, `HH`, `mm`, `ss`, `EEEE`, `MMM`, etc.) |
| `lang` | No | Locale code (`en_US`, `fr_FR`, …). Default `auto` |
| `timezone_id` | No | `"UTC"`, IANA timezone, `"use_preferred_timezone"`, `"extract_from_column"`. Default `"UTC"` |
| `timezone_src` | Cond | Column name when `timezone_id = "extract_from_column"` |

```json
{"inCol": "parsed_date", "outCol": "month_label", "format": "MMM yyyy", "lang": "en_US", "timezone_id": "UTC"}
```

**⚠ Param naming trap:** DSS expects `inCol`/`outCol`. Agents often guess `column`/`outputColumn` — DSS rejects with a misleading `Empty column name` error.
