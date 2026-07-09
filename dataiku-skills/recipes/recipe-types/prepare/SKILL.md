---
name: dataiku-recipe-prepare
description: "Prepare (shaker) recipes apply a sequential script of processor steps for data cleansing, normalization, and enrichment. The recipe has a library of ~100 purpose-built processors (filtering, rounding, regex extraction, column splitting, date parsing, geo operations, and more); steps are applied to the input dataset in order."
---

# Prepare Recipe

The prepare recipe applies an ordered list of processor steps to an input dataset. Each step handles one specific operation; steps are chained to achieve complex transformations. Use the parent `recipes` skill for shared lifecycle steps (flow checks, recipe creation/selection, I/O changes, execution).

**I/O:** exactly 1 dataset in (role `main`) → exactly 1 dataset out (role `main`).

## Workflow

1. `get_recipe_settings` → inspect `payload.steps[]`.
2. Before writing any processor that transforms values in a specific column, inspect the source columns with `get_dataset_profile` using `columns=[<col>]` for distributions, distinct values, and null rates, and `get_dataset_sample` using `columns=[<col>], limit=10` (or higher if needed) when you also need raw value formats such as date patterns, text structure, or delimiters.
3. Before editing `steps[]`, choose the most specific purpose-built processor that matches the transformation intent. Do not use the `CreateColumnWithGREL` processor unless you confirm no other listed processor or sequence of processors covers the operation.
4. Add, remove, or reorder `steps[]` entries. Preserve unrelated keys.
5. `set_recipe_settings` with action `set_payload`. Always include `"alwaysShowComment": true` in every step envelope.
6. The prepare recipe automatically detects and sets the schema of the output dataset upon creation. Despite this, it can be helpful to change output dataset column types with `set_dataset_column_storage_types` (e.g. `{"parsed_date": "date", "score": "bigint"}`) for cases like parsing a string date in place, then changing the storage type to `date`, or extracting a number from a string column in place, then changing the storage type to `bigint`. Valid types are 'tinyint', 'smallint', 'int', 'bigint', 'float', 'double', 'boolean', 'string', 'date', 'dateonly', 'datetimenotz', 'geopoint', 'geometry', 'array', 'map', and 'object'. Be careful when setting storage types.
**NOTE:** if a column contains values that don't conform to the storage type, Dataiku will treat them as null. Since storage types use strict interpretation of what data is valid, you may need to parse or format the data (with steps in the prepare recipe) before being able to use it with a precise storage type. 
**NOTE:** certain storage types are not supported for certain dataset connection types. If an error or warning is encountered with a particular storage type and connection type, fallback to string.
8. Build the output dataset(s).
9. Validate produced columns proportionately:
   - use `get_dataset_sample` by default to confirm values are populated and plausibly correct
   - add `get_dataset_profile` when distribution, null-rate, or typing sanity checks materially affect confidence

Preview-level confidence is not enough. A step that looks syntactically valid in settings can still yield empty output columns after execution.

## Step Execution Order

Steps execute top-to-bottom. Columns created in earlier steps are available to later steps; renamed or removed columns must use their new names (or are gone) in later steps.

## Required References

Read before editing:
- [Prepare recipe settings and payload](references/recipe_settings_and_payload.md) (always)
- [Shared scope params](references/shared_scope_params.md) (`appliesTo`, `columns`, `appliesToPattern`)
- [Shared formula language](references/dataiku_formula_language.md) (formula-based processors)
- [Shared timezone params](references/shared_timezone_params.md) (timezone-aware processors)

Before any `set_payload` call: read the relevant processor reference and make an explicit decision for each param field. Re-reading it immediately before every write is not required if you already have the needed details in working context.

## Processors

Processor `type` is at `steps[i].type`. **Prefer purpose-built processors over `CreateColumnWithGREL`** — use GREL only when no listed processor (or combination of multiple processors) covers the operation. Only use types listed here; never invent a type name. If no listed type covers the operation, tell the user.

- [FlagOnValue](references/processors/flag_on_value.md): Flag rows containing specific values — creates a 1/empty indicator column.
- [FlagOnDate](references/processors/flag_on_date.md): Flag rows based on date range, relative window, or date-part matching.
- [FlagOnBadType](references/processors/flag_on_bad_type.md): Flag rows with invalid meaning/type values.
- [NumericalFormatConverter](references/processors/numerical_format_converter.md): Convert numbers between locale-specific formats.
- [CurrencyConverterProcessor](references/processors/currency_converter_processor.md): Convert amounts between currencies using configurable reference dates.
- [CurrencySplitter](references/processors/currency_splitter.md): Split currency-formatted strings into amount and currency code columns.
- [MatchCounter](references/processors/match_counter.md): Count pattern occurrences in a column.
- [FindReplace](references/processors/find_replace.md): Replace values, substrings, or regex patterns using explicit mappings.
- [TextSimplifierProcessor](references/processors/text_simplifier_processor.md): Normalize text — stemming, stop-word removal, optional token sorting.
- [ColumnPseudonymization](references/processors/column_pseudonymization.md): Hash-pseudonymize column values with optional salt/pepper.
- [JSONFlattener](references/processors/json_flattener.md): Flatten JSON objects or arrays.
- [UserAgentClassifier](references/processors/user_agent_classifier.md): Parse a User-Agent column into browser/device metadata.
- [GeoIPResolver](references/processors/geo_ip_resolver.md): Resolve an IP address column into country / region / city / lat-lng / timezone.
- [ChangeCRSProcessor](references/processors/change_crs_processor.md): Convert geometry values between coordinate reference systems.
- [GeoPointCreator](references/processors/geo_point_creator.md): Create a geopoint column from latitude and longitude columns.
- [GeoDistanceProcessor](references/processors/geo_distance_processor.md): Compute distance between two geopoints or a geopoint and a fixed reference point.
- [GeoPointBufferProcessor](references/processors/geo_point_buffer_processor.md): Create circle or rectangle areas around geopoint values.
- [ZipArrays](references/processors/zip_arrays.md): Combine N JSON array columns into one.
- [ConcatArrays](references/processors/concat_arrays.md): Concatenate N JSON array columns into a single JSON array.
- [ArrayExtractProcessor](references/processors/array_extract_processor.md): Extract an element or sub-array from a JSON array column.
- [ArraySortProcessor](references/processors/array_sort_processor.md): Sort values inside a JSON array column.
- [ArrayFold](references/processors/array_fold.md): Expand each array element into a separate row.
- [ColumnsConcat](references/processors/columns_concat.md): Concatenate multiple columns into one with a delimiter.
- [ColumnCopier](references/processors/column_copier.md): Copy values from one column into a new column.
- [Coalesce](references/processors/coalesce.md): Return the first non-empty value across selected columns, with optional default.
- [VisualIfRule](references/processors/visual_if_rule.md): If / else-if / else branching to assign output column values.
- [CreateColumnWithGREL](references/processors/create_column_with_grel.md): Compute new columns using formulas (math, string, date, boolean).
- [FlagOnCustomFormula](references/processors/flag_on_custom_formula.md): Flag rows using a formula expression.
- [FilterOnCustomFormula](references/processors/filter_on_custom_formula.md): Keep/remove rows or clear cells using a formula.
- [FilterOnBadType](references/processors/filter_on_bad_type.md): Filter or clear rows with invalid meaning/type values.
- [ColumnRenamer](references/processors/column_renamer.md): Rename columns using explicit source-to-target mappings.
- [ColumnsSelector](references/processors/columns_selector.md): Keep or remove columns by name or pattern.
- [ColumnSplitter](references/processors/column_splitter.md): Split a column into multiple columns or a JSON array on a delimiter.
- [FilterOnNumericalRange](references/processors/filter_on_numerical_range.md): Filter or clear rows outside a numerical range.
- [BinnerProcessor](references/processors/binner_processor.md): Discretize numerical values into fixed-width or custom bins.
- [MinMaxProcessor](references/processors/min_max_processor.md): Clip or clear values outside a min/max range.
- [DateParser](references/processors/date_parser.md): Parse date strings into ISO 8601 format.
- [UNIXTimestampParser](references/processors/unix_timestamp_parser.md): Convert Unix timestamps to date/datetime values.
- [DateComponentsExtractor](references/processors/date_components_extractor.md): Extract date parts (year, month, day, etc.) to new columns.
- [DateIncrement](references/processors/date_increment.md): Increment a date column by a static value or by another column's values.
- [DateDifference](references/processors/date_difference.md): Compute date differences in configurable units.
- [HolidaysComputer](references/processors/holidays_computer.md): Flag holidays/weekends from date values.
- [BooleanNot](references/processors/boolean_not.md): Negate a boolean column in place, flipping true to false and false to true.
- [ColumnReorder](references/processors/column_reorder.md): Move selected columns to a new position (start, end, or relative to a reference column) without adding, removing, or modifying any column values.
- [ComputeNTile](references/processors/compute_n_tile.md): Assign each row an n-tile (quantile) bucket for a numeric column, written to a new column or in place.
- [ExtractNumbers](references/processors/extract_numbers.md): Parse numeric values out of an alphanumeric text column into one or more decimal columns.
- [FillColumn](references/processors/fill_column.md): Overwrite every value in a column with a single constant value, creating the column if it does not already exist.
- [GrokProcessor](references/processors/grok_processor.md): Parse a free-text string column with a Grok expression, emitting one new output column per named capture variable plus an optional match-flag column.
- [MeanProcessor](references/processors/mean_processor.md): Compute the per-row mean of two or more numeric columns into a new output column.
- [MeaningTranslate](references/processors/meaning_translate.md): Translate a column's values through a user-defined VALUES_MAPPING meaning, writing the mapped labels in place or to a new column.
- [MeasureNormalize](references/processors/measure_normalize.md): Normalize physical-measurement strings (mass, volume, surface) to canonical units in place.
- [NGramExtract](references/processors/n_gram_extract.md): Extract word n-grams from a text column, emitting them as a JSON array, one new row per n-gram, or one column per n-gram.
- [PythonUDF](references/processors/python_udf.md): Run user-defined Python over each cell, row, or row group via a `process` function.
- [RegexpExtractor](references/processors/regexp_extractor.md): Extract substrings from a string column with a Java regex, writing one output column per capture group (named or numbered) and an optional match-flag column.
- [RoundProcessor](references/processors/round_processor.md): Round the numeric values in selected columns in place, using round, floor, or ceiling at a chosen number of decimal places or significant digits.
- [SplitIntoChunks](references/processors/split_into_chunks.md): Split a long free-text column into overlapping character-bounded chunks, emitting one output row per chunk.
- [StringTransformer](references/processors/string_transformer.md): Apply a single in-place string transformation (case change, trim, URL/XML/Unicode (un)escaping, normalization, or truncation) to one or more text columns.
- [SwitchCase](references/processors/switch_case.md): Map the values of an input column into a new output column via an ordered list of key-to-value rules, with a fallback default for unmatched rows.
- [Tokenizer](references/processors/tokenizer.md): Tokenize a free-text column into words, optionally normalizing, stemming, removing stop words, and sorting, then emit them as a JSON array (`TO_JSON`), one row per token (`FOLD`), or one column per token (`SPLIT`).
- [FillEmptyWithValue](references/processors/fill_empty_with_value.md): Replace empty or null cells in the selected column(s) with a fixed placeholder value.
- [RemoveRowsOnEmpty](references/processors/remove_rows_on_empty.md): Delete rows that have an empty or null value in the selected column(s), or keep only those rows when `keep` is `true`.
- [SplitInvalidCells](references/processors/split_invalid_cells.md): Move cells of a column that are invalid for a chosen meaning out into a new column, leaving valid values in place.
- [UpDownFiller](references/processors/up_down_filler.md): Fill empty cells in the selected column(s) with the previous non-empty value above (fill down) or the next non-empty value below (fill up).
- [FilterOnDate](references/processors/filter_on_date.md): Keep, remove, or clear rows and cells based on a date condition: a static range, a relative window, or a date part.
- [FilterOnValue](references/processors/filter_on_value.md): Keep, remove, or clear rows and cells whose selected column values match one or more specified values.
- [FlagOnNumericalRange](references/processors/flag_on_numerical_range.md): Flag rows whose selected numeric column values fall inclusively within a numerical range by creating a column containing `1` for matching rows.
- [MergeLongTailValues](references/processors/merge_long_tail_values.md): Keep only the most frequent values in a categorical column and fold every rarer value into a single replacement bucket.
- [DateFormatter](references/processors/date_formatter.md): Reformat a parsed ISO 8601 datetime into a human-readable string using a Java `SimpleDateFormat` pattern.
- [DateTruncate](references/processors/date_truncate.md): Truncate a parsed datetime down to a chosen calendar granularity (year, month, day, hour, minute, or second).
- [EmailSplitter](references/processors/email_splitter.md): Split each email address into its local-part and domain columns.
- [JSONPathExtractor](references/processors/json_path_extractor.md): Extract the JSON content of a column via a JSONPath expression into a new column.
- [QueryStringSplitter](references/processors/query_string_splitter.md): Explode an HTTP query string into a separate, optionally prefixed column for each parameter key.
- [URLSplitter](references/processors/url_splitter.md): Parse a URL column into its scheme, host, port, path, query-string, and anchor parts, each gated by a boolean flag.
- [VisitorIdGenerator](references/processors/visitor_id_generator.md): Derive a single best-effort visitor id column by hashing several per-row web-log fields together.
- [ArrayUnfold](references/processors/array_unfold.md): Unfold a JSON-array string column into one column per distinct array element, holding either the occurrence count or a binary indicator.
- [NestProcessor](references/processors/nest_processor.md): Nest one or more selected columns into a single JSON-object output column, typing embedded JSON and numeric values while keeping everything else as strings.
- [NumericalCombinator](references/processors/numerical_combinator.md): Generate pairwise sum, difference, product, and quotient columns from a set of selected numeric columns.
- [SplitUnfold](references/processors/split_unfold.md): Split a delimited string column on a separator and unfold each distinct chunk into its own column whose cell holds the occurrence count of that chunk in the row.
- [Transpose](references/processors/transpose.md): Transpose the dataset so the chosen column's row values become column headers and the original columns become rows.
- [Unfold](references/processors/unfold.md): Dummify a categorical column into one binary indicator column per distinct value.
- [GeoPointExtractor](references/processors/geo_point_extractor.md): Extract latitude and longitude columns from a GeoPoint-format column.
- [GeometryInfoExtractor](references/processors/geometry_info_extractor.md): Extract centroid, length, and area columns from a WKT geometry column.
- [EnrichFrenchDepartement](references/processors/enrich_french_departement.md): Enrich a French department code column with INSEE demography, housing, fiscal, employment, and companies columns.
- [EnrichFrenchPostcode](references/processors/enrich_french_postcode.md): Enrich a French postcode column with the associated department code plus INSEE demography, housing, fiscal, employment, and companies columns.
- [EnrichWithBuildContextProcessor](references/processors/enrich_with_build_context_processor.md): Enrich every row with build-time context columns: the build date and the build job id.
- [EnrichWithRecordContextProcessor](references/processors/enrich_with_record_context_processor.md): Enrich each row with its record-level source context (partition id, file path/name, file record id, and last-modified time) as new columns.
- [MultiColumnByPrefixFold](references/processors/multi_column_by_prefix_fold.md): Fold every column whose name matches a regex into long form, emitting one row per non-empty matched column with the captured column name and value in two new columns.
- [MultiColumnFold](references/processors/multi_column_fold.md): Melt a chosen set of columns into long form, emitting one row per non-empty cell with the source column name and value in two new columns.
- [ObjectFoldProcessor](references/processors/object_fold_processor.md): Parse a JSON-object column and fold each key/value entry into its own row, writing the key and value into two new columns and deleting the source column.
- [Pivot](references/processors/pivot.md): Collapse rows sharing a sorted index into one row, turning each distinct label value into its own column filled by the values column.
- [RepeatableUnfold](references/processors/repeatable_unfold.md): Group rows by a key column and, each time a trigger value appears in the fold column, flush the accumulated data-column values into a new row with dynamically named fold columns.
- [SplitFold](references/processors/split_fold.md): Split a delimited column on a literal whole-string separator and fan each input row out into one row per non-empty chunk, overwriting the column with that chunk.

## Guardrails

- Resolve `params` from the processor reference + shared references every time; do not guess params.
- Keep unknown payload keys unchanged unless intentionally modifying behavior.
- Use `set_payload` for `steps[]` edits; `set_params` is not needed for processor-step logic.
- Do not assume success from payload inspection alone; validate built output columns before considering the recipe complete.
