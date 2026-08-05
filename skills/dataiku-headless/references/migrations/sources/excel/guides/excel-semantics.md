# Excel Semantics and Placeholders

Read this when translating workbook semantics or classifying placeholders. Return to [Excel](../excel.md) for routing.

## Excel semantics

- Formulas and M are the spec. Cached cell values are the parity contract.
- Upload the workbook itself. CSV round-trip destroys typed cells, dates, encoding,
  and display-vs-stored distinctions.
- Formatted display value is not stored value. Parity-check stored value only.
- Excel Find/Replace can act on displayed text. The same stored value can diverge by
  cell format.
- Fold on wide month columns can silently drop null-valued rows. Pre-fill or isolate
  rows when null itself is meaningful.
- A mixed date column must be parsed by render class: serial digits, long textual
  dates, short canonical dates, then explicit fallback.
- `asDateOnly` can parse patterns that a date-parser step rejects. If the parser nulls
  the whole column, switch to formula parsing.
- A two-digit-year pivot window can turn absurd source years into plausible wrong
  years. Range-check parsed years.
- Volatile formulas use cached snapshot values for parity.
- The same row label on different source sheets is a different series. Sheet identity
  is part of the key.
- Manual math like `TREND`, `LINEST`, `SUMPRODUCT` OLS, and expanding means is still
  workbook logic, not an excuse to transcribe outputs.
- Sign can flip per block on the same metric. Carry sign as contract. Verify sign, not
  just magnitude.
- Schema type `date` does not serial-convert numeric cells. Mixed datetime, serial,
  and text columns stay string until branch-parse.
- Merged cells read null outside the top-left cell.
- Autofilter hides rows without deleting them; hidden rows remain data.
- Total Row and pivot totals are aggregates, not records.
- Long IDs beyond 15 significant digits were already corrupted in Excel.
- The workbook date system can be 1900 or 1904. Hand-rolled serial math must check
  `date1904`.
- A sibling CSV export is usually cp1252 and exports display-formatted dates, not
  stored date values.

## Silent-Failure Traps

| Trap | Guard |
|---|---|
| Numbers-as-text, non-breaking spaces, whitespace dirt, or encoding damage break joins and deduplication | Normalize before equality logic while retaining raw evidence for diagnosis |
| Column-variant formulas, wrong array extent, or wrong day-count basis shift only part of the horizon | Sample several columns per row and compare with cached outputs before broad claims |

## Excel placeholders

- `Web.Page(Web.Contents(...))` is live scrape. Distinguish: live-refresh works, cached
  workbook output used as static source, or refresh path blocked. Record which state
  the build used.
- External connections and query tables can point at sources unavailable in the shipped
  bundle. Use a shipped-file match, cached-output fallback, or user escalation. Do not
  silently invent the refresh path.
- VBA, Goal Seek, Solver, slicers, validation dropdowns, comments, and conditional
  formatting are separate UI or code concerns. Inventory intent. Do not silently
  pretend they are tabular transforms.
