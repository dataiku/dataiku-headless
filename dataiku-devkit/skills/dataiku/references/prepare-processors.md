# Prepare Recipe Processors

## Golden Rule

**ALWAYS prefer a purpose-built processor over `CreateColumnWithGREL`.** GREL formulas are the last resort — use only when no dedicated processor handles the operation.

Purpose-built processors are faster (native Java), produce cleaner step lists, and don't require GREL syntax knowledge. When chaining prepare steps, mix shortcuts and `add-step` freely.

## Critical: Column Names with Spaces

**Columns with spaces in their names (e.g. `Return Reason`, `Order Date`) cannot be referenced by GREL formulas, ColumnCopier, or VisualIfRule in prepare recipes.** GREL variable references replace spaces with underscores (`Return_Reason`), but the column lookup silently returns null — it does NOT match the actual column.

Workarounds (pick one):
1. **Rename first** — add a `ColumnRenamer` step to remove spaces BEFORE any GREL/VisualIfRule step, then rename back after
2. **Use a Python recipe** — `df["col with spaces"]` works correctly in pandas
3. **Use processors that take column names as params** (not GREL variables) — `DateParser`, `DateDifference`, `DateComponentsExtractor`, `StringTransformer`, `FillEmptyWithValue`, `RemoveRowsOnEmpty`, `FindReplace`, `ColumnsSelector` all accept `"columns": ["Return Reason"]` and work correctly with spaces

Processors that **DO** work with spaces (they take column names in `columns[]` params):
`DateParser`, `DateDifference`, `DateComponentsExtractor`, `StringTransformer`, `FillEmptyWithValue`, `RemoveRowsOnEmpty`, `FindReplace`, `FlagOnValue`, `FilterOnBadType`, `ColumnsSelector`, `ColumnRenamer`, `ColumnsConcat`

Processors that **DO NOT** work with spaces (they use GREL variable references):
`CreateColumnWithGREL` (`add-formula`), `ColumnCopier`, `VisualIfRule`, `FilterOnCustomFormula`

## Processor Catalog by Usage Tier

### Essential (used in almost every project)

| Need | Processor | CLI |
|------|-----------|-----|
| Rename columns | `ColumnRenamer` | `add-rename --from old --to new` |
| Delete/keep columns | `ColumnsSelector` | `add-delete-columns --columns "c1,c2"` |
| Reorder columns | `ColumnReorder` | `add-step --type ColumnReorder` |
| Filter rows by value | `FlagOnValue` | `add-filter-rows --column col --values "a,b"` |
| Find & replace text | `FindReplace` | `add-find-replace --column col --find X --replace Y` |
| If/then/else branching | `VisualIfRule` | `add-step --type VisualIfRule` |
| Parse date strings | `DateParser` | `add-step --type DateParser` |

### Very Common (frequent in most workflows)

| Need | Processor | CLI |
|------|-----------|-----|
| Compute new column with formula | `CreateColumnWithGREL` | `add-formula --expr "..." --column col` |
| Fill nulls/blanks (fixed value) | `FillEmptyWithValue` | `add-fill-empty --column col --value "0"` |
| Remove empty rows | `RemoveRowsOnEmpty` | `add-step --type RemoveRowsOnEmpty` |
| Filter rows by formula | `FilterOnCustomFormula` | `add-filter-rows --formula "price > 100"` |
| Format dates (custom pattern) | `DateFormatter` | `add-step --type DateFormatter` |
| Round numbers | `RoundProcessor` | `add-step --type RoundProcessor` |
| Filter by numeric range | `FilterOnNumericalRange` | `add-step --type FilterOnNumericalRange` |
| Uppercase/lowercase/trim | `StringTransformer` | `add-step --type StringTransformer` |
| Split column by delimiter | `ColumnSplitter` | `add-step --type ColumnSplitter` |
| Extract year/month/day | `DateComponentsExtractor` | `add-step --type DateComponentsExtractor` |
| Set every row to a constant | `FillColumn` | `add-step --type FillColumn --params '{"column":"col","value":"X"}'` |
| Normalize/stem/stop-words | `TextSimplifierProcessor` | `add-step --type TextSimplifierProcessor` |
| Compute date difference | `DateDifference` | `add-step --type DateDifference` |
| Filter by date range | `FilterOnDate` | `add-step --type FilterOnDate` |
| Extract with regex | `RegexpExtractor` | `add-step --type RegexpExtractor` |
| Concatenate columns | `ColumnsConcat` | `add-step --type ColumnsConcat` |
| Flatten JSON column | `JSONFlattener` | `add-step --type JSONFlattener` |
| Remove invalid-type rows | `FilterOnBadType` | `add-step --type FilterOnBadType` |
| Copy a column | `ColumnCopier` | `add-step --type ColumnCopier` |
| Fold wide→long | `MultiColumnFold` | `add-fold --columns "c1,c2" --key-column k --value-column v` |
| Create geopoint | `GeoPointCreator` | `add-geopoint --lat-column lat --lon-column lon` |
| Format numbers | `NumericalFormatConverter` | `add-step --type NumericalFormatConverter` |
| Flag rows by value | `FlagOnValue` | `add-step --type FlagOnValue` |
| Extract JSON path | `JSONPathExtractor` | `add-step --type JSONPathExtractor` |
| Fill down/up | `UpDownFiller` | `add-step --type UpDownFiller` |

### Common (used regularly depending on use case)

| Need | Processor | CLI |
|------|-----------|-----|
| Fold array to rows | `ArrayFold` | `add-step --type ArrayFold` |
| Flag rows by date | `FlagOnDate` | `add-step --type FlagOnDate` |
| Increment dates | `DateIncrement` | `add-step --type DateIncrement` |
| Reverse geocode | `CityLevelReverseGeocoder` | `add-step --type CityLevelReverseGeocoder` |
| Clip numeric range | `MinMaxProcessor` | `add-step --type MinMaxProcessor` |
| Switch/case mapping | `SwitchCase` | `add-step --type SwitchCase` |
| Enrich with record context | `EnrichWithRecordContextProcessor` | `add-step --type EnrichWithRecordContextProcessor` |
| Truncate dates to unit | `DateTruncate` | `add-step --type DateTruncate` |
| Extract numbers from text | `ExtractNumbers` | `add-step --type ExtractNumbers` |
| Tokenize text | `Tokenizer` | `add-step --type Tokenizer` |
| Split & fold | `SplitFold` | `add-step --type SplitFold` |
| Unfold (long→wide) | `Unfold` | `add-step --type Unfold` |
| Fold by column prefix | `MultiColumnByPrefixFold` | `add-step --type MultiColumnByPrefixFold` |
| Convert currency | `CurrencyConverterProcessor` | `add-step --type CurrencyConverterProcessor` |
| Parse UNIX timestamps | `UNIXTimestampParser` | `add-step --type UNIXTimestampParser` |
| Sort array | `ArraySortProcessor` | `add-step --type ArraySortProcessor` |
| Pivot | `Pivot` | `add-step --type Pivot` |
| Flag rows by formula | `FlagOnCustomFormula` | `add-step --type FlagOnCustomFormula` |
| Transpose | `Transpose` | `add-step --type Transpose` |
| GeoIP resolve | `GeoIPResolver` | `add-step --type GeoIPResolver` |
| Count pattern matches | `MatchCounter` | `add-step --type MatchCounter` |
| Discretize numbers into bins | `BinnerProcessor` | `add-step --type BinnerProcessor` |
| Unfold array to columns | `ArrayUnfold` | `add-step --type ArrayUnfold` |
| Compute geo distance | `GeoDistanceProcessor` | `add-step --type GeoDistanceProcessor` |
| Split text into chunks | `SplitIntoChunks` | `add-step --type SplitIntoChunks` |
| Normalize measurement units | `MeasureNormalize` | `add-step --type MeasureNormalize` |
| Combine numeric columns | `NumericalCombinator` | `add-step --type NumericalCombinator` |
| Extract from array | `ArrayExtractProcessor` | `add-step --type ArrayExtractProcessor` |
| Group rare values | `LongTailGrouper` | `add-step --type LongTailGrouper` |
| Enrich with build context | `EnrichWithBuildContextProcessor` | `add-step --type EnrichWithBuildContextProcessor` |
| Pseudonymize column | `ColumnPseudonymization` | `add-step --type ColumnPseudonymization` |
| Extract with Grok pattern | `GrokProcessor` | `add-step --type GrokProcessor` |
| Nest columns into JSON | `NestProcessor` | `add-step --type NestProcessor` |
| Detect holidays | `HolidaysComputer` | `add-step --type HolidaysComputer` |
| Flag values by numeric range | `FlagOnNumericalRange` | `add-step --type FlagOnNumericalRange` |
| Flag invalid types | `FlagOnBadType` | `add-step --type FlagOnBadType` |
| Split invalid cells | `SplitInvalidCells` | `add-step --type SplitInvalidCells` |
| Coalesce (first non-null) | `Coalesce` | `add-step --type Coalesce` |

### Less Common (specific use cases)

| Need | Processor | CLI |
|------|-----------|-----|
| Split email into parts | `EmailSplitter` | `add-step --type EmailSplitter` |
| Split currency | `CurrencySplitter` | `add-step --type CurrencySplitter` |
| Extract lat/lon from geopoint | `GeoPointExtractor` | `add-step --type GeoPointExtractor` |
| Parse User-Agent | `UserAgentClassifier` | `add-step --type UserAgentClassifier` |
| Fold JSON objects to rows | `ObjectFoldProcessor` | `add-step --type ObjectFoldProcessor` |
| Extract geometry metrics | `GeometryInfoExtractor` | `add-step --type GeometryInfoExtractor` |
| Compute quantiles | `ComputeNTile` | `add-step --type ComputeNTile` |
| Concatenate arrays | `ConcatArrays` | `add-step --type ConcatArrays` |
| Extract n-grams | `NGramExtract` | `add-step --type NGramExtract` |
| Split URL into parts | `URLSplitter` | `add-step --type URLSplitter` |
| Zip arrays | `ZipArrays` | `add-step --type ZipArrays` |
| Negate boolean | `BooleanNot` | `add-step --type BooleanNot` |
| Repeatable unfold | `RepeatableUnfold` | `add-step --type RepeatableUnfold` |
| Change CRS | `ChangeCRSProcessor` | `add-step --type ChangeCRSProcessor` |
| Merge long-tail values | `MergeLongTailValues` | `add-step --type MergeLongTailValues` |
| Split query string | `QueryStringSplitter` | `add-step --type QueryStringSplitter` |
| Compute row-wise mean | `MeanProcessor` | `add-step --type MeanProcessor` |
| Change column type/meaning | `TypeSetter` | `add-step --type TypeSetter` |

## Shared Param Patterns

Many processors share these param groups. Learn them once, apply everywhere.

## Processor Detail References

| Need | Read |
|---|---|
| Column selection, rename/reorder/copy, fill, string transforms, filters, formula, numeric helpers | `prepare-processors-core.md` |
| DateParser, DateFormatter, DateTruncate, UNIXTimestampParser, date differences/components, date gotchas | `prepare-processors-dates.md` |
| Fold/unfold, JSON flattening, arrays, MemoryEquiJoiner, geospatial processors, enrichment | `prepare-processors-reshape-json-geo.md` |

## Step JSON Structure

Prepare step JSON uses this shape inside a recipe's Shaker script:

```json
{"type":"ProcessorType","params":{}}
```

Use `dku recipe add-step --type TYPE --params JSON` for raw processor insertion, or a purpose-built CLI shortcut when one exists.
