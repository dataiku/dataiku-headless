# Prepare Processors: Dates and Time

Date/time processor details and traps. Read this before parsing, formatting, truncating, or converting timestamps.

### DateParser

**When:** Parse date strings to ISO 8601. Also used for timestamp→dateonly conversion (the only working approach on DSS 14.5).

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

**Format ordering — `yy` MUST precede `yyyy` when both apply.** DateParser tries formats in list order and uses the first one that consumes the input. `yyyy` is permissive: it matches any digit run, so against `27-JUN-70` the pattern `dd-MMM-yyyy` will succeed and produce year `0070` instead of letting `dd-MMM-yy` (with the SimpleDateFormat 80-year pivot) fire. Symptom: dates with 2-digit years come out as years `0006`, `0070`, `0007` etc. Fix: list 2-digit-year patterns first — `["dd-MMM-yy", "d-MMM-yy", "dd-MMM-yyyy", "d-MMM-yyyy", ...]`. Same trap with `M` vs `MM`, `d` vs `dd`: most-restrictive (or shortest-year) variant first.

---

### DateComponentsExtractor

**When:** Extract year, month, day, hour, etc. from a parsed date column. Prefer over GREL `year()`, `month()`.

| Param | Required | Description |
|-------|----------|-------------|
| `column` | Yes | Input date column (must be parsed ISO-8601) |
| `timezone_id` | Yes | `"UTC"` or IANA timezone |
| `outYearColumn` | No | Output column for year (empty = skip) |
| `outMonthColumn` | No | Output column for month |
| `outDayColumn` | No | Output column for day-of-month |
| `outHourColumn` | No | Output column for hour |
| `outDayOfWeekColumn` | No | Output column for day-of-week |
| `outWeekOfYearColumn` | No | Output column for week-of-year |

```json
{"column": "order_date", "timezone_id": "UTC", "outYearColumn": "order_year", "outMonthColumn": "order_month", "outDayColumn": "order_day"}
```

---

### DateDifference

**When:** Compute time between dates. Prefer over GREL `dateDiff()`.

| Param | Required | Description |
|-------|----------|-------------|
| `input1` | Yes | Primary date column |
| `compareTo` | Yes | `COLUMN`, `DATE`, or `NOW` |
| `input2` | Cond | Second date column (when `compareTo = COLUMN`) |
| `refDate` | Cond | Fixed ISO-8601 date (when `compareTo = DATE`) |
| `output` | Yes | Output column name |
| `outputUnit` | Yes | `DAYS`, `WEEKS`, `MONTHS` |
| `timezone_id` | Yes | `"UTC"` or `"use_preferred_timezone"` |

```json
{"output": "days_since_signup", "input1": "signup_date", "compareTo": "NOW", "outputUnit": "DAYS", "timezone_id": "UTC"}
```

---

### DateFormatter

**When:** Format an ISO-8601 date column into a custom string format (e.g. `MMM yyyy`, `yyyy-MM-dd`, `EEEE d MMMM`). Input must be a parsed date column (type `date`, `datetimenotz`, or `dateonly`) — run `DateParser` first if the source is a string.

**⚠ Param naming trap:** DSS expects `inCol`/`outCol`. Agents often guess `column`/`outputColumn` from older docs — DSS rejects with a misleading `Empty column name` error. The `dku recipe add-step` CLI catches this and exits early.

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

**Output type:** `STRING`. DSS warns that non-ISO-8601 output will be treated as an unparsed date — that's fine if you only need the string representation.

---

### DateTruncate

**When:** Truncate a parsed date to a unit (year / month / day / hour / minute / second). Output keeps the date type (not a string) — good for subsequent grouping or aggregation. Prefer over GREL `trunc()`.

| Param | Required | Description |
|-------|----------|-------------|
| `inCol` | Yes | Input column name (parsed date) |
| `outCol` | No | Output column name (empty = in-place) |
| `datePart` | No | `YEAR`, `MONTH`, `DAY`, `HOUR`, `MINUTE`, `SECOND` (UPPERCASE). Default `YEAR` if omitted — **silent trap if you forget it** |

```json
{"inCol": "parsed_date", "outCol": "month_start", "datePart": "MONTH"}
```

**Gotcha:** Unknown fields (e.g., `unit`, `truncate`, `precision`) are silently ignored, and `datePart` defaults to `YEAR`. Always spell `datePart` correctly and supply one of the enum values above.

---

### UNIXTimestampParser

**When:** Convert an integer UNIX epoch column (seconds or milliseconds) to an ISO-8601 date column.

| Param | Required | Description |
|-------|----------|-------------|
| `inCol` | Yes | Input column (integer or string epoch) |
| `outCol` | No | Output column name (empty = in-place) |
| `milliseconds` | No | `true` = interpret as ms, `false` = interpret as seconds. **Default `false`** (seconds). Note: this is a BOOLEAN, not a string enum — `"unit":"SECONDS"` is ignored |

```json
{"inCol": "event_ts", "outCol": "event_date", "milliseconds": false}
```

Output column type is `date` (ISO-8601). Use downstream `DateFormatter` / `DateTruncate` / `DateParser(outType: dateonly)` for further shaping.

---

### Timestamp → date-only (common recipe)

**For timestamp string → date-only column:** Use `DateParser` with `outType: dateonly`. Always provide `outCol` — in-place DateParser **silently produces all nulls**.

```json
{"appliesTo": "SINGLE_COLUMN", "columns": ["timestamp_col"], "formats": ["yyyy-MM-dd HH:mm:ss"], "lang": "auto", "timezone_id": "UTC", "outCol": "date_only", "outType": {"name": "out", "type": "dateonly"}}
```

**DateParser format patterns (Java SimpleDateFormat):**
- `yyyy-MM-dd HH:mm:ss` — standard timestamp
- `MM/dd/yyyy h:mm a` — US format with AM/PM
- `yyyy-MM-dd'T'HH:mm:ssZ` — ISO 8601 (use `Z`/`z`, NOT `XXX` — `XXX` causes "Illegal pattern component")
- `yyyy-MM-dd` — date-only string
- Works on both string AND already-typed date columns (e.g., `datetimenotz`)

**Timezone gotcha:** DateParser converts to UTC before extracting date. `2024-01-01 23:59:59-05:00` → `2024-01-02` in UTC dateonly. Use `"timezone_id":"use_preferred_timezone"` if you want to preserve the source timezone's date.

**For UNIX epoch → date-only:** `UNIXTimestampParser` → `DateParser(outType: dateonly)` in two steps.

---

### GREL Critical Gotchas

| Trap | What happens | Fix |
|------|-------------|-----|
| `round(x, 2)` | Silent empty output — `round()` takes exactly 1 arg (nearest integer) | `round(x * 100) / 100` for 2 decimals, `round(x * 10) / 10` for 1 decimal |
| `toString(date, "yyyy-MM-dd")` | **No-op** — format argument silently ignored, returns original ISO date | Use the `DateFormatter` processor (`inCol`/`outCol`/`format`) for custom string formats |
| `formatDate()` / `toDate()` | **Do not exist in GREL** — "Unknown function" error | Use processors: `DateFormatter` for formatting, `DateParser` or `UNIXTimestampParser` for parsing — never these GREL functions |
| DateParser without `outCol` | **Silently produces all nulls** — in-place parsing is broken | Always specify `outCol` to write to a new column |
| Date processor `Empty column name` error | Legacy param names `column`/`outputColumn` instead of `inCol`/`outCol` | `DateFormatter`, `DateTruncate`, `UNIXTimestampParser` all use `inCol`/`outCol`. The `dku recipe add-step` CLI catches this and exits early |
| `DateTruncate` silently truncates to year | `datePart` param missing or misspelled (e.g. `unit`, `truncate`) — unknown fields are ignored and it defaults to `YEAR` | Always spell `datePart` exactly; valid values are `YEAR`/`MONTH`/`DAY`/`HOUR`/`MINUTE`/`SECOND` (UPPERCASE) |
| `UNIXTimestampParser` dates at `1970-01-21` | Default `milliseconds` is `false`; passing `"unit":"SECONDS"` does nothing because `unit` isn't a valid key | Use boolean `"milliseconds": true` for ms input, `false` (or omit) for seconds |
| `asDateOnly()` on STRING column | Silently fails in some recipe contexts | Run `DateParser` step first, then use the parsed column in date functions |
| `log()` | Returns base-10, not natural log | Use `ln()` for natural log |
| `numval(col)` / `val(col)` bareword | Silent empty output — accessor needs a quoted column name | Use `numval("col")` / `val("col")` with quotes, OR drop the wrapper and use bareword `col` (arithmetic auto-coerces) |
| Formula column type | New columns default to STRING | Always run `apply-schema` after adding formula steps |

---

## Full Processor Catalog (Quick Reference)

For processors not covered in detail above, use `add-step --type TYPE --params JSON`. Key params are listed for orientation — verify exact params via `dku recipe get-step` on an existing recipe or DSS documentation.

### Date formatting in Prepare recipes
`DateFormatter`, `DateTruncate`, `UNIXTimestampParser` all exist on DSS 14.5. The agent trap is wrong param names: they use `inCol` / `outCol` (NOT `column` / `outputColumn` from older docs), and DSS returns a misleading `Empty column name` error otherwise — the `dku recipe add-step` CLI catches this pre-send. Other traps:
- `DateTruncate` param is `datePart` (values `YEAR` / `MONTH` / `DAY` / `HOUR` / `MINUTE` / `SECOND`) and defaults to `YEAR` if missing.
- `UNIXTimestampParser` uses `milliseconds` BOOLEAN, not `unit` string.
- GREL `formatDate()` and `toDate()` do not exist; GREL `toString(date, "format")` is a no-op.
- `DateParser` without `outCol` silently produces all nulls.
- ISO 8601 `DateParser` format: use `Z` / `z` pattern, NOT `XXX`.

### Processor field-name traps (silent no-ops)
DSS silently ignores unknown processor params — wrong field names produce a step that looks accepted but does nothing. The traps:
- `MinMaxProcessor`: `lowerBound` / `upperBound` / `clear` (NOT `min` / `max` / `action`).
- `GeoIPResolver`: `inCol` / `outColPrefix` + 10 boolean `extract_*` toggles (`extract_country` / `_country_code` / `_continent` / `_continent_code` / `_region` / `_city` / `_postal_code` / `_latitude` / `_longitude` / `_timezone`) — NOT `inputColumn` / `outputColumn`.
- `FillColumn`: `{column, value}` — sets EVERY row of `column` to `value` (overwrites non-null AND fills nulls). For "fill nulls only, leave existing values" use `FillEmptyWithValue`.
- `ArrayUnfold`: `countVal: true` emits the `<col>_count` length column (legacy `appendCount` is silently ignored).
- `PythonUDF`: requires `mode: ROW|CELL` — CELL needs `column`. Missing `mode` produces a no-op.
