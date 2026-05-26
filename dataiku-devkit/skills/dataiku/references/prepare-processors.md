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

## Processor Decision Table

Before writing a GREL formula, check this table. The processors below are stock DSS unless flagged otherwise (`FoldColumnsByName` is a plugin — see its section).

| Need to... | Processor | CLI |
|------------|-----------|-----|
| Rename columns | `ColumnRenamer` | `add-rename --from old --to new` |
| Delete/keep columns | `ColumnsSelector` | `add-delete-columns --columns "c1,c2"` |
| Copy a column | `ColumnCopier` | `add-step --type ColumnCopier` |
| Reorder columns | `ColumnReorder` | `add-step --type ColumnReorder` |
| Coalesce (first non-null) | `Coalesce` | `add-step --type Coalesce` |
| Fill nulls/blanks (fixed value) | `FillEmptyWithValue` | `add-fill-empty --column col --value "0"` |
| Set every row to a constant | `FillColumn` | `add-step --type FillColumn --params '{"column":"col","value":"X"}'` — `{column, value}` shape; sets EVERY row of `column` to `value` (overwrites non-null AND fills nulls). Verified against localhost. Omit `value` (or pass empty string) to clear the column. For "fill nulls only, leave existing values" use `FillEmptyWithValue` instead. |
| Fill down/up | `UpDownFiller` | `add-step --type UpDownFiller` |
| Concatenate columns | `ColumnsConcat` | `add-step --type ColumnsConcat` |
| Uppercase/lowercase/trim | `StringTransformer` | `add-step --type StringTransformer` |
| Find & replace text | `FindReplace` | `add-find-replace --column col --find X --replace Y` |
| Split column by delimiter | `ColumnSplitter` | `add-step --type ColumnSplitter` |
| Split email into parts | `EmailSplitter` | `add-step --type EmailSplitter` |
| Split URL into parts | `URLSplitter` | `add-step --type URLSplitter` |
| Extract with regex | `RegexpExtractor` | `add-step --type RegexpExtractor` |
| Extract with Grok pattern | `GrokProcessor` | `add-step --type GrokProcessor` |
| Normalize/stem/stop-words | `TextSimplifierProcessor` | `add-step --type TextSimplifierProcessor` |
| Tokenize text | `Tokenizer` | `add-step --type Tokenizer` |
| If/then/else branching | GREL `if()` | `add-formula --expr 'if(cond, "a", "b")'` |
| Switch/case mapping | `SwitchCase` | `add-step --type SwitchCase` |
| Filter rows by value | `FlagOnValue` | `add-filter-rows --column col --values "a,b"` |
| Filter rows by formula | `FilterOnCustomFormula` | `add-filter-rows --formula "price > 100"` |
| Remove invalid-type rows | `FilterOnBadType` | `add-step --type FilterOnBadType` |
| Filter by numeric range | `FilterOnNumericalRange` | `add-step --type FilterOnNumericalRange` |
| Filter by date range | `FilterOnDate` | `add-step --type FilterOnDate` |
| Remove empty rows | `RemoveRowsOnEmpty` | `add-step --type RemoveRowsOnEmpty` |
| Flag invalid types | `SplitInvalidCells` | `add-step --type SplitInvalidCells` |
| Parse date strings | `DateParser` | `add-step --type DateParser` |
| Extract year/month/day | `DateComponentsExtractor` | `add-step --type DateComponentsExtractor` |
| Compute date difference | `DateDifference` | `add-step --type DateDifference` |
| Timestamp → date-only | `DateParser` (outType: dateonly) | `add-step --type DateParser` |
| Format dates (custom pattern) | `DateFormatter` | `add-step --type DateFormatter` |
| Truncate dates to unit | `DateTruncate` | `add-step --type DateTruncate` |
| Increment dates | `DateIncrement` | `add-step --type DateIncrement` |
| Parse UNIX timestamps | `UNIXTimestampParser` | `add-step --type UNIXTimestampParser` |
| Detect holidays | `HolidaysComputer` | `add-step --type HolidaysComputer` |
| Bin/discretize numbers | `BinnerProcessor` | `add-step --type BinnerProcessor` |
| Clip numeric range | `MinMaxProcessor` | `add-step --type MinMaxProcessor` |
| Round numbers | `RoundProcessor` | `add-step --type RoundProcessor` |
| Combine numeric columns | `NumericalCombinator` | `add-step --type NumericalCombinator` |
| Compute mean of columns | `MeanProcessor` | `add-step --type MeanProcessor` |
| Negate boolean | `BooleanNot` | `add-step --type BooleanNot` |
| Change column type/meaning | `TypeSetter` | `add-step --type TypeSetter` |
| Fold wide→long | `MultiColumnFold` | `add-fold --columns "c1,c2" --key-column k --value-column v` |
| Fold by column prefix | `MultiColumnByPrefixFold` | `add-step --type MultiColumnByPrefixFold` |
| Split & fold | `SplitFold` | `add-step --type SplitFold` |
| Unfold (long→wide) | `Unfold` | `add-step --type Unfold` |
| Split & unfold | `SplitUnfold` | `add-step --type SplitUnfold` |
| Pivot | `Pivot` | `add-step --type Pivot` |
| Transpose | `Transpose` | `add-step --type Transpose` |
| Flatten JSON column | `JSONFlattener` | `add-step --type JSONFlattener` |
| Extract JSON path | `JSONPathExtractor` | `add-step --type JSONPathExtractor` |
| Nest columns into JSON | `NestProcessor` | `add-step --type NestProcessor` |
| Extract from array | `ArrayExtractProcessor` | `add-step --type ArrayExtractProcessor` |
| Sort array | `ArraySortProcessor` | `add-step --type ArraySortProcessor` |
| Unfold array to columns | `ArrayUnfold` | `add-step --type ArrayUnfold` |
| Fold array to rows | `ArrayFold` | `add-step --type ArrayFold` |
| Create geopoint | `GeoPointCreator` | `add-geopoint --lat-column lat --lon-column lon` |
| Compute geo distance | GREL `geoDistance()` | `add-geodistance --from A --to B` |
| Extract lat/lon from geopoint | `GeoPointExtractor` | `add-step --type GeoPointExtractor` |
| Group long-tail values | `LongTailGrouper` | `add-step --type LongTailGrouper` |
| Count pattern matches | `MatchCounter` | `add-step --type MatchCounter` |
| Pseudonymize column | `ColumnPseudonymization` | `add-step --type ColumnPseudonymization` |
| Normalize/scale values | `MeasureNormalize` | `add-step --type MeasureNormalize` |
| Custom expression (LAST RESORT) | `CreateColumnWithGREL` | `add-formula --expr "..." --column col` |

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
