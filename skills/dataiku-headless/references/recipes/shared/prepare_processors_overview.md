---
name: prepare-processors-overview
description: "Consolidated one-line reference for all prepare/shaker processor types: what each does and any behavioral gotchas, for interpreting existing steps[] or describing steps accurately to Cobuild."
---

# Prepare Processors Overview

Consolidated reference for all prepare (Shaker) recipe processor `type` values. Use this to interpret an existing prepare recipe's `steps[]` list (from `get_recipe_settings`) or to describe a prepare step accurately in a natural-language Cobuild request.

## Column Management

- **ColumnRenamer** — Rename one or more columns using explicit source-to-target mappings.
- **ColumnCopier** — Copy values from one column into another column.
- **ColumnReorder** — Move selected columns to a new position (start, end, or relative to a reference column); does not change values.
- **ColumnSplitter** — Split a column into several columns (or a JSON array) on each occurrence of a delimiter.
- **ColumnsSelector** — Keep or remove columns by explicit names or pattern.
- **ColumnsConcat** — Concatenate values across columns using a delimiter into a single output column.
- **Coalesce** — Return the first non-empty value across selected columns, optionally with a fallback default.
- **FillColumn** — Overwrite every value in a column with a single constant; creates the column if absent.
- **FillEmptyWithValue** — Replace empty/null cells in selected column(s) with a fixed placeholder value.
- **UpDownFiller** — Fill empty cells with the previous non-empty value above (fill down) or next non-empty value below (fill up). Order-sensitive; engines that don't preserve row order can scramble the fill sequence.
- **NestProcessor** — Nest selected columns into a single JSON-object output column.
- **Transpose** — Transpose the dataset: a chosen column's row values become column headers, original columns become rows. Hard-capped at 100 input rows.

## Text / String

- **StringTransformer** — Apply a single in-place string transformation (case change, trim, URL/XML/Unicode escape/unescape, normalization, truncation) to one or more text columns.
- **FindReplace** — Replace values in selected columns using explicit mapping rules (inline or dataset-backed), with configurable match mode and normalization. Dataset-backed mode requires wiring the mapping dataset as a secondary `reference` recipe input.
- **SwitchCase** — Map input-column values to a new output column via ordered key-to-value rules, with a fallback default for unmatched rows.
- **RegexpExtractor** — Extract substrings via Java regex; one output column per capture group (named/numbered) plus optional match-flag column.
- **GrokProcessor** — Parse free text with a Grok expression; emits one output column per named capture plus optional match-flag column. Composite patterns can expand into extra sub-capture columns.
- **MatchCounter** — Count occurrences of a pattern (full-string/substring/regex) in a column.
- **NGramExtract** — Extract word n-grams from a text column as a JSON array, one row per n-gram, or one column per n-gram.
- **Tokenizer** — Tokenize free text into words; optionally normalize, stem, remove stop words, sort; output as JSON array, one row per token, or one column per token.
- **TextSimplifierProcessor** — Normalize, stem, remove stop words, and/or alphabetically sort tokens in a text column.
- **SplitIntoChunks** — Split long free text into overlapping character-bounded chunks, one output row per chunk (multiplies row count).
- **MeasureNormalize** — Normalize physical-measurement strings (mass/volume/surface) to canonical units in place.
- **UserAgentClassifier** — Parse a User-Agent string column into classified browser/device metadata.
- **VisitorIdGenerator** — Derive a single best-effort visitor id by hashing several per-row web-log fields (IP, user agent, browser language, timezone offset) together.
- **ColumnPseudonymization** — Pseudonymize column values by hashing `cell_value + pepper + salt_value` (SHA256/SHA512/MD5). Salt/pepper must stay stable across datasets for hashed values to match on joins.

## Split / Unfold / Fold (Row & Column Shape)

- **ArrayFold** — Fold a JSON-array cell into several rows (one row per array value); other columns are copied to each generated row.
- **ArrayUnfold** — Unfold a JSON-array string column into one column per distinct array element, holding occurrence count or a binary indicator.
- **SplitFold** — Split a column on a literal separator and fan each row into one row per non-empty chunk, overwriting the column with that chunk.
- **SplitUnfold** — Split a column on a separator; unfold each distinct chunk into its own column whose cell holds that chunk's occurrence count.
- **Unfold** — Dummify a categorical column into one binary indicator column per distinct value.
- **MultiColumnFold** — Melt (unpivot) chosen columns into long form: one row per non-empty cell with source column name and value in two new columns.
- **MultiColumnByPrefixFold** — Like MultiColumnFold, but column selection is by regex matched against the FULL column name (despite the "prefix" name), not a literal prefix.
- **ObjectFoldProcessor** — Parse a JSON-object column and fold each key/value entry into its own row (key and value in two new columns); source column deleted afterward.
- **RepeatableUnfold** — Group rows by a key column; each time a trigger value appears in the fold column, flush accumulated data into a new row with dynamically named fold columns. Buffers all per-key data in memory.
- **Pivot** — Collapse rows sharing a sorted index into one row, turning each distinct label value into its own column. Requires input pre-sorted on the index column.
- **compute_n_tile / ComputeNTile** — Assign each row to an n-tile (quantile) bucket for a numeric column. Requires a SQL/in-database or native Spark engine; the Dataiku streaming engine yields null.

## Arrays

- **ArrayExtractProcessor** — Extract one element (by index) or a contiguous sub-array (by range) from an array-valued column.
- **ArraySortProcessor** — Sort values inside an array-valued column, numerically or alphabetically, ascending or descending.
- **ConcatArrays** — Concatenate N input array columns (as JSON) into a single JSON array, in listed column order.
- **ZipArrays** — Combine N input array columns (as JSON) into a single output column, pairing by column order.

## Date / Time

- **DateParser** — Parse strings containing dates in any format into standard ISO 8601.
- **DateFormatter** — Reformat a parsed ISO 8601 datetime to a string via a Java `SimpleDateFormat` pattern.
- **DateComponentsExtractor** — Extract elements (year, month, day, hour, week, timestamp, etc.) of an ISO 8601 date into separate columns.
- **DateDifference** — Compute the difference between a date column and another reference (column, fixed date, or now), with options to exclude weekends/holidays.
- **DateIncrement** — Increment a date column by a static value or by a value from another column.
- **DateTruncate** — Truncate a parsed datetime to a chosen calendar granularity (year/month/day/hour/minute/second). Truncating to hour/minute/second on a date-only column throws at runtime.
- **UNIXTimestampParser** — Convert a Unix timestamp column (seconds or milliseconds) to a date/datetime column.
- **HolidaysComputer** — Flag bank holidays, school holidays, and weekends from a date column, with optional holiday reasons and zones; calendar/timezone can be per-row via column extraction.
- **FilterOnDate** — Keep/remove/clear rows or cells based on a date condition: static range, relative window, or date-part match. Target column must already hold parsed dates.
- **FlagOnDate** — Flag (rather than filter) rows based on the same date-condition modes as FilterOnDate.

## Numeric

- **RoundProcessor** — Round numeric values in place (round/floor/ceiling) at chosen decimal places or significant digits.
- **BinnerProcessor** — Discretize numerical values into bins, either fixed width or custom explicit ranges.
- **MinMaxProcessor** — Force numeric values into a range by clipping out-of-range values to the nearest bound, or clearing them instead.
- **NumericalCombinator** — Generate pairwise sum/difference/product/quotient columns from selected numeric columns (up to 19 columns).
- **NumericalFormatConverter** — Convert numbers between country/language-specific formats (e.g. EN, FR, CH, IT, raw).
- **MeanProcessor** — Compute the per-row mean of two or more numeric columns into a new output column.
- **ExtractNumbers** — Parse numeric values out of an alphanumeric text column into one or more decimal columns; can expand multipliers like `k`/`m`.
- **CurrencyConverterProcessor** — Convert numeric amounts from one currency to another using exchange rates at a selected reference date.
- **CurrencySplitter** — Split a currency-formatted string column into separate amount and currency-code columns.

(See ComputeNTile above under Split/Unfold/Fold — it is also numeric-bucketing in nature.)

## Filtering / Flagging

- **FilterOnValue** — Keep/remove/clear rows and cells whose column values match one or more specified values (full string, substring, or regex).
- **FlagOnValue** — Flag (add indicator column) rather than filter, same matching semantics as FilterOnValue.
- **FilterOnNumericalRange** — Keep/remove rows, or clear/preserve cells, containing numbers within an inclusive numerical range.
- **FlagOnNumericalRange** — Flag rows whose numeric value falls inclusively within a range.
- **FilterOnBadType** — Keep/remove rows, or clear/preserve cells, based on whether values match a selected meaning (type validity check, e.g. LongMeaning, Email, URL).
- **FlagOnBadType** — Flag rows based on the same meaning-validity check as FilterOnBadType.
- **FilterOnCustomFormula** — Filter rows or clear cell values based on a formula expression; a row/cell matches if the formula result is "truish" (true boolean, non-zero number, or the string "true").
- **FlagOnCustomFormula** — Flag rows matching a formula expression (writes `1` for matches, leaves others empty).
- **RemoveRowsOnEmpty** — Delete rows with an empty/null value in selected column(s), or (with `keep`) keep only those rows.
- **SplitInvalidCells** — Move cells invalid for a chosen meaning into a new column, leaving valid values in place.
- **MergeLongTailValues** — Keep only the most frequent values in a categorical column; fold rarer values into a single replacement bucket. Requires a SQL/in-database or native Spark engine; the local Dataiku streaming engine is a no-op passthrough.

## Geo

- **GeoPointCreator** — Create a geopoint column (WKT `POINT(lon lat)`) from separate latitude and longitude columns.
- **GeoPointExtractor** — Extract latitude/longitude columns back out of a GeoPoint-format column.
- **GeoDistanceProcessor** — Compute geographic distance between two geopoint columns, or between a geopoint column and a fixed reference point/geometry.
- **GeoPointBufferProcessor** — Create a circle or rectangle area geometry around geopoint values.
- **GeoIPResolver** — Resolve an IP address column into geographic attributes (country, city, lat/lng, timezone, etc.); requires a configured Dataiku GeoIP database.
- **ChangeCRSProcessor** — Convert geometry values from one coordinate reference system (CRS) to another (EPSG code or WKT).
- **GeometryInfoExtractor** — Extract centroid, length, and area columns from a WKT geometry column; length/area are in CRS units, so meaning differs between planar and spheroidal engines.
- **EnrichFrenchDepartement** — Enrich a French department code column with INSEE demography/housing/fiscal/employment/companies data.
- **EnrichFrenchPostcode** — Enrich a French postcode column with department code plus INSEE demography/housing/fiscal/employment/companies data.

## Web / Log Parsing

- **URLSplitter** — Parse a URL column into scheme/host/port/path/query-string/anchor parts, each independently toggled.
- **QueryStringSplitter** — Explode an HTTP query string into one column per parameter key (data-dependent column set).
- **EmailSplitter** — Split an email address column into local-part and domain columns (split on `@`).

## JSON

- **JSONFlattener** — Unnest/flatten JSON objects (and optionally arrays) into multiple columns.
- **JSONPathExtractor** — Extract JSON content via a JSONPath expression into a new column.

## Enrichment / Context

- **EnrichWithBuildContextProcessor** — Add build-time context columns (build date, build job id); values are only meaningful at actual build time.
- **EnrichWithRecordContextProcessor** — Add record-level source-context columns (partition id, file path/name, file record id, last-modified time) for file-based/partitioned inputs.
- **MeaningTranslate** — Translate a column's values through a user-defined VALUES_MAPPING meaning; build fails if the referenced meaning doesn't exist or isn't a VALUES_MAPPING type.

## Boolean

- **BooleanNot** — Negate a boolean column in place (true↔false); null/unrecognized values pass through unchanged.

## Formula / Code / Conditional Logic

- **CreateColumnWithGREL** — Compute a new column using a Dataiku formula (Math, string, date, boolean/conditional functions). Intended as a fallback for logic not covered by a more targeted processor — not the first choice for common cleaning/parsing/normalization.
- **VisualIfRule** — Create if / else-if / else branching logic to assign values or formulas into output columns. Branch conditions are Dataiku visual conditions: each is an input column + operator + value (operators match the column's type — e.g. string columns get `contains`, numeric columns get `<`/`>`), combinable into AND/OR groups.
- **PythonUDF** — Run user-defined Python over each cell/row/row group via a `process` function; can run in-process (Jython, Python 2, stdlib-only) or via a real Python code environment kernel (`useKernel`).
