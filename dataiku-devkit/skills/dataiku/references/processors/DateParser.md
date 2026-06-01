# DateParser

**When:** Parse date strings to ISO 8601. Also used for timestamp→dateonly conversion (the only working approach on DSS 14.5).

**CLI shortcut:** `dku recipe add-step RECIPE --type DateParser --params '{"appliesTo":"SINGLE_COLUMN","columns":["signup_date"],"formats":["yyyy-MM-dd"],"lang":"auto","outCol":"signup_parsed","outType":{"name":"out","type":"date"},"timezone_id":"UTC"}' -P PROJ`

| Param | Required | Description |
|-------|----------|-------------|
| `appliesTo` | Yes | `SINGLE_COLUMN` |
| `columns` | Yes | `["date_col"]` |
| `formats` | Yes | Java date patterns: `["yyyy-MM-dd", "MM/dd/yyyy"]`. For ISO 8601 with timezone, use `Z`/`z` NOT `XXX` |
| `lang` | Yes | `"auto"` or locale code (`en_US`, `fr_FR`) |
| `timezone_id` | Yes | `"UTC"`, IANA timezone, etc. |
| `outCol` | **Yes** | Output column name. **CRITICAL: omitting outCol (in-place) silently produces all nulls** |
| `outType` | Yes | `{"name":"out","type":"date"}`, `"dateonly"`, or `"datetimenotz"` |

```json
{"appliesTo": "SINGLE_COLUMN", "columns": ["signup_date"], "formats": ["yyyy-MM-dd"], "lang": "auto", "outCol": "signup_parsed", "outType": {"name": "out", "type": "date"}, "timezone_id": "UTC"}
```

**Format ordering:** `yy` MUST precede `yyyy` when both apply. `yyyy` matches any digit run and will produce wrong years for 2-digit dates. List 2-digit-year patterns first.
