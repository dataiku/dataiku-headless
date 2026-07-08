# Analysis Workbooks

Excel workbooks whose job is an *analysis pipeline*: raw data sheet → cleaned sheet → pivot tables → dashboard, and/or Power Query (M) ETL. Read `overview.md` first (triage, shared rules, parsing scripts, ingestion).

## Approach — recover the implicit DAG

Excel has no explicit workflow graph. The "workflow" hides in four layers, in *decreasing order of fidelity*:

1. **Power Query (M)** — when present, the M source IS the DAG: every `shared <Query> = …` is a node; a query referencing another query is a flow edge. Fully recoverable (`dump_anatomy.py` extracts it).
2. **Pivot table definitions** — exact aggregation specs (rows / columns / filters / value-aggs + source table).
3. **Formulas** — per-column formulas are Prepare steps; cross-sheet references are flow edges; `VLOOKUP`/`XLOOKUP`/`INDEX+MATCH` are Joins; `SUMIF(S)`/`COUNTIF(S)` are aggregations.
4. **Sheet topology** — the canonical analyst pipeline expressed as sheets. When cleaning was done by hand (no formulas, no M), **diff raw vs cleaned** to reverse-engineer the steps (dedup count, recoded values, added columns, renames).

## Analysis-specific rules

1. **One sheet ≠ one dataset.** Sheets may hold several tables, title rows above headers, doc text, pivot outputs. The ListObject refs and pivot locations in the inventory say what's real. Pivot-output sheets are *validation targets*, not data inputs.
2. **Hand-edited columns may have NO derivable rule — detect this early and stop chasing parity.** Sheet-diffing can expose a column where no `(stored value, format) → cleaned value` function exists (manual range edits / display-text Find&Replace passes — Excel F&R matches the *displayed* text, so identical stored values diverge by cell format). Compute the empirical mapping `(format class, stored value) → cleaned value`; if it's inconsistent within a class, classify the column as **hand-authored data**: preserve source-stored values, document the divergence, surface to the user. Validate the *deliverables* (pivots/charts) instead — they rarely consume such columns.
3. **Excel "Remove Duplicates" keeps the first occurrence in sheet order — DSS has no sheet-order column.** Reproduce with TopN (partition = key, rank by a data column that encodes the preference — a validity/dirt flag, a date). True ties fall to engine arrival order, which *usually* matches file order on the DSS engine but is not guaranteed — validate value-differing pairs individually and document residual one-cell divergences. If exact order parity is mandatory, pre-bake a row-index column offline.

## Inventory triage

| Found in workbook | Meaning | Migration source of truth |
|---|---|---|
| M queries present | Explicit ETL graph | Translate M per § M → DSS. Sheet tables named like queries are *cached query outputs* — validation targets |
| `Source = File.Contents("C:\Users\…")` | Author-machine absolute path | Files usually ship alongside the workbook — match by name; else migrate from the cached output table; else ask |
| `Source = Web.Page(Web.Contents(url))` | Live web scrape | User decision — § M → DSS quick reference (`Web.Page` row) |
| Pivot tables | Aggregation specs | → Group recipes; pivot *sheet cells* (read `data_only=True`) = ground truth |
| Formula columns in a Table | Derived columns | → Prepare steps (§ Formula → DSS) |
| Raw sheet + cleaned sheet, no formulas/M | Hand cleaning | Diff the two sheets **column-complete**: row delta = dedup/filters; value deltas = recodes; new cols = formulas. Migrate raw→cleaned as one Prepare (+ dedup) |
| `=RANDBETWEEN(…)`, `NOW()`, `TODAY()` | Volatile formulas | § Formula → DSS quick reference (volatile row) |
| Hidden sheets / very-hidden sheets | Often staging or "dirt" data | Inventory them — hidden ≠ ignorable; they may feed queries |
| `.xlsm` with VBA macros | Code-driven logic | § Non-migratable patterns (VBA row) |
| Slicers, conditional formatting, data validation | Presentation/UX | § Non-migratable patterns |

### Inventory shape

```
| # | Object | Kind | What It Does | Inputs | Outputs | Migratable? |
|---|--------|------|--------------|--------|---------|-------------|
| 1 | Original Data!Table1 | sheet table | Raw purchases (1026 rows + dups) | (file) | #2 | Yes → UploadedFiles dataset |
| 2 | Cleaned & Formatted Data!Table2 | sheet table | Dedup on ID, recode M/S→Married/Single, add Age Brackets | #1 | #3,#4,#5 | Yes → Prepare + Distinct |
| 3 | PivotTable1 | pivot | avg(Income) by Gender × Purchased Bike | #2 | chart | Yes → Group |
| 6 | Dashboard | sheet | 3 charts + 3 slicers | #3,#4,#5 | — | Yes → chart insights + dashboard |
```

## Mixed/dirty date columns — parse by render class

A real-world Excel date column can mix typed datetimes (under several display formats), serial numbers stored as plain ints, and stray text — in one column. With schema `string`, DSS renders each **class** deterministically, so one GREL formula handles all of them:

| Cell content | DSS string render | GREL branch |
|---|---|---|
| Datetime, short date formats (`mm-dd-yy`, …) | Canonical `M/d/yy` (`9/1/07`) — DSS does NOT use the cell's own short format | `asDateOnly(strval("d"), "M/d/yy")` |
| Datetime, long/locale formats (`[$-F800]dddd…`) | The cell's format (`Wednesday, July 14, 2021`) | `contains(strval("d"), ",")` → `asDateOnly(strval("d"), "EEEE, MMMM d, yyyy")` |
| Serial stored as number | Digits (`44391`) | `match(strval("d"), /(\d{5})/) != null` → `inc(asDateOnly("1899-12-30","yyyy-MM-dd"), toNumber(strval("d")), "days")` |
| Text junk | Literal text | Fallback fill (often a known bulk-update date from the GT) |

Branch order: serial → long-format → short-format, with a final null-guard fill. Two more traps: **GREL `asDateOnly(s, fmt)` parses patterns that the `DateParser` *processor* refuses outright** (all-null output for the same `M/d/yy` — if DateParser nulls everything, switch the step to a GREL formula); and the 2-digit-year pivot window (~±80y) sends corrupted years somewhere absurd (stored year 7463 renders `…63` → parses 1963) — **range-check parsed years** and repair impossible ones explicitly.

## M → DSS quick reference

| M construct | DSS |
|---|---|
| `Excel.Workbook(File.Contents(path))` / `Csv.Document(…)` | Uploaded dataset (one per source file) |
| `Folder.Files(dir)` + `Transform File` fn + `ExpandTableColumn` | Same-schema files → ONE UploadedFiles dataset (multi-upload). Filename used (`Source.Name` kept) → per-file datasets + `create-stack --origin-column` |
| `Table.Combine({A, B})` | Stack (`create-stack`) — or `upload --sheet-indices … --sheets-to-column` when the inputs are sheets of one workbook |
| `Table.NestedJoin(A, k, B, k, …, JoinKind.X)` + `ExpandTableColumn` | Join (`create-join`); JoinKind.LeftOuter→LEFT, Inner→INNER, FullOuter→FULL (SQL engine) |
| `Table.SelectRows(t, each cond)` | Prepare filter step, or `preFilter` on the consuming visual recipe |
| `Table.AddColumn(t, "c", each expr)` | Prepare `add-formula` (GREL) |
| `Table.TransformColumnTypes` | `set-schema` on the dataset (NOT Prepare steps) |
| `Table.RenameColumns` / `RemoveColumns` / `SelectColumns` / `ReorderColumns` | Prepare `ColumnRenamer` / `ColumnsSelector` |
| `Table.Skip(n)` + `Table.PromoteHeaders` | Format params `skipRowsBeforeHeader` + `parseHeaderRow` — disappears as a step |
| `Table.ReplaceValue(t, old, new, …, {cols})` | Prepare `FindReplace` (`add-find-replace`; `--ignore-case` for case-insensitive) |
| `Table.SelectRows(… <> null)` / `RemoveRowsWithErrors` | Prepare filter on blank / `RemoveRowsOnEmpty` |
| `Table.Distinct` | Distinct recipe (all cols) or Window `ROW_NUMBER`+filter (subset key — same as Alteryx `Unique`) |
| `Table.Group(t, keys, aggs)` | Group (`create-group`) |
| `Table.UnpivotOtherColumns` / `Unpivot` | Prepare `add-fold` (`MultiColumnFold`) — same null-drop + fold-before-clean rules as Alteryx Transpose |
| `Table.Pivot` | Pivot recipe (modality caveat — see ayx CrossTab) or Group + per-modality computed cols |
| `Table.Sort` | Sort recipe — or drop if presentation-only |
| `Table.AddIndexColumn` | Pre-bake at extraction or Window `rowNumber` (no `AddId` processor) |
| `Text.BeforeDelimiter` / `Splitter.SplitTextByDelimiter` | Prepare `ColumnSplitter` / GREL `split()` |
| `Date.Year(col)` etc. | GREL `datePart(col, "year")` family |
| `Web.Page(Web.Contents(url))` | User decision: pre-bake the cached table (static) or Python recipe (`pandas.read_html`) + scenario for refresh |
| `let … in` chains within one query | Almost always ONE Prepare recipe with N steps |
| Query referencing another query | Flow edge — the referenced query's output dataset feeds the next recipe |
| Parameter queries (`IsParameterQuery=true`), `Transform Sample File` scaffolding | Combine-files plumbing — drops entirely (the dataset-level multi-upload replaces it) |

## Formula → DSS quick reference

Formulas live in *columns* (one formula filled down a Table column = one Prepare step) or in *cells* (summary blocks — usually pivot-adjacent presentation, validate-don't-migrate).

| Excel formula | DSS |
|---|---|
| `IF(a, b, IF(c, d, e))` nests | GREL `if(a, b, if(c, d, e))` |
| `VLOOKUP` / `XLOOKUP` / `INDEX+MATCH` onto another sheet/table | **Join recipe** (the lookup sheet is a dataset) — never a GREL emulation. Tiny static remap (<10 pairs) → Prepare `FindReplace` |
| `SUMIF(S)` / `COUNTIF(S)` / `AVERAGEIF(S)` keyed on own-row values | Group(keys) + Join back — or Window `--frame-unbounded` partitioned by the key (broadcast-aggregate collapse, see ayx) |
| `SUM`/`AVERAGE` over a whole column (grand totals block) | Drop — it's a pivot/`info` concern, not data |
| `CONCATENATE` / `&` / `TEXTJOIN` | GREL `+` concat / `join()` |
| `LEFT/RIGHT/MID/LEN/TRIM/UPPER/LOWER/PROPER/SUBSTITUTE` | GREL `substring/length/trim/toUppercase/toLowercase/capitalize/replace` |
| `TEXT(date, fmt)` | Prepare `DateFormatter` |
| `YEAR/MONTH/DAY/WEEKDAY/EOMONTH/DATEDIF` | GREL `datePart` / `inc` / `diff` (see `../../dku-cli/references/formulas.md`) |
| `IFERROR(x, y)` | GREL null guards (`if(isBlank(…)…)`) — most Excel errors become nulls in DSS |
| `RANDBETWEEN/RAND/NOW/TODAY` | Volatile — the cached value is THE value (recalcs on every open): migrate it, note the non-determinism; `now()` exists in GREL but freezing the cached snapshot preserves parity |
| 3-D refs (`=Sheet2!B2`), spill ranges, array formulas | Cross-sheet refs are flow edges; spill/array formulas → usually a Join or Window, read intent not syntax (deep treatment: `model-workbooks.md`) |

## Collapse triggers — analysis workbooks

The cross-source triggers in `../references/workflow.md` § Phase 2 all apply. Excel adds:

| Trigger pattern | DSS collapse | Ratio |
|---|---|---|
| Raw sheet → cleaned sheet (hand-edited or N M steps): dedup + recodes + case-fixes + derived buckets + renames | **ONE Prepare** (recodes, formulas, renames, blank-row guard) **+ one dedup** (Distinct, or TopN/Window if keyed on a subset) | N steps→2 |
| Per-sheet query + `Table.Combine` + add-source-tag column (Year 11/Year 12 pattern) | **ONE dataset**: `upload --sheet-indices "0,1" --sheets-to-column` — the prepended sheet-name column IS the tag. Zero recipes | 3 queries→0 |
| Per-file query + combine-files scaffolding (`Folder.Files`, `Sample File`, `Transform File`, `Parameter1`) | Same-schema files → ONE multi-upload dataset (scaffolding queries all drop). Filename-as-data → per-file datasets + `create-stack --origin-column` | 5 queries→0–1 |
| N pivot tables on one cleaned table | N parallel Group recipes from ONE input dataset (don't re-clean per pivot). Pivot's column axis (e.g. × Purchased Bike) usually stays **long** in DSS — charts/dashboards consume long better than wide | — |
| Pivot + chart + dashboard chain | Group recipe + **chart insight on the grouped dataset** + dashboard tile. The "pivot sheet" itself is not a dataset | pivot sheet→0 |
| Helper-column ladders (B2 helper feeds C2 feeds D2, helpers hidden/ignored downstream) | Inline into the final expression in ONE Prepare step; keep helpers only if reused | N cols→1 step |
| `GETPIVOTDATA` cells / KPI summary blocks | Validation targets only — values come from the Group outputs; nothing to build | →0 |

## Non-migratable patterns

| Excel pattern | Reason | Dataiku answer |
|---|---|---|
| Dashboard layout, text boxes, screenshots, doc sheets | Presentation | DSS dashboard + wiki (`ai-describe --save` opt-in) |
| Slicers | Interactive filter UI | Dashboard filters tile (UI step — `dashboard add-tile` only places insights today). The chart layer itself is fully CLI-buildable: `insight create -t chart --ds` → `set-chart-type` → `add-dimension` (`--slot 0` X, `--breakdown` series) → `add-measure` → `validate`, then `dashboard create` + `add-tile` |
| Conditional formatting | Visual flagging | Usually drop; if it encodes logic (e.g. "red = overdue"), surface as an explicit flag column in Prepare |
| Data validation dropdowns | Input UX | Editable dataset / app — note it, don't block on it |
| Goal Seek / Solver / What-If tables | Optimization | Python recipe (scipy) — same as Alteryx optimizer macros |
| VBA macros (`.xlsm`) | Arbitrary code | Inventory intent via `olevba`/`oletools` on `vbaProject.bin`; usually Python recipe or scenario step. Surface to user before migrating |
| Cell comments / notes | Annotations | Wiki or column descriptions |

## Gotchas

| Gotcha | Details / fix |
|---|---|
| Autodetected `parseHeaderRow` may be `false` (detection ran on a non-data sheet) | `upload --sheet` re-asserts it. When patching `formatParams.sheets` by hand, always re-assert `parseHeaderRow: true` too — else the header arrives as row 1 and numerics go null |
| Full re-detection **clobbers** manual formatParams (snaps back to the first sheet) | Re-infer with `detect --keep-format`, never plain `detect --save` (`overview.md` § Ingestion) |
| A structurally-broken recipe can "succeed" into a **0-row output** | Row-count verification after every build is non-negotiable; check `dku job status` when output looks off |
| Whole columns render null in `head` after a step-set change | Stale output schema — `apply-schema` + rebuild after every step-set change (`../../dku-cli/playbooks/tabular-flow.md`) |
| Phantom all-null rows (used range > table) | Blank-row filter + Table-ref count-match (`overview.md` shared rule "the used range lies") |
| Junk columns right of the real table (used-range pollution, 200+ cols) | Schema from `dump_anatomy.py --schema` clamps to header extent; verify col count |
| Merged cells read null outside the top-left cell | `UpDownFiller` fill-down (`ingestion.md` § reshape toolkit; only NULL triggers the fill — `../../dku-cli/references/prepare-processors.md`) |
| Hidden rows (filtered views) are still data | An Excel autofilter hides rows without deleting — if the analysis depended on the filter, make it an explicit Prepare filter |
| Excel Table "Total Row" / "Grand Total" pivot rows | Aggregates, not records — filter them; exclude from ground-truth reads too |
| Numbers stored as text (leading `'`, `TEXT()` outputs, web pastes) | Mixed-type column → DSS reads strings; strip/cast in Prepare. Watch invisible chars: NBSP `\xa0` from web/cp1252 sources breaks equality and `numval` |
| 17-variant categorical dirt (case + leading/trailing + internal whitespace) | Whitespace: one formula `replace(trim(strval("c")), /\s+/, " ")`. Case: `add-find-replace --ignore-case` per canonical value |
| Corrupted near-duplicate rows (mojibake suffixes like `Clerical Ω║` on pasted twins) | Clean values via anchored alternation `match(strval("c"), /(Skilled Manual|Management|Manual|…).*/)[0]`; rank the dedup TopN by a raw-validity flag computed BEFORE the cleanup overwrites the evidence |
| Multi-input Join `-k` prefix is the join-**pair** index (pairs = inputs − 1), not the input index | 3 inputs → `-k 'Order ID' -k '1:Region'` (pairs 0..1) |
| 15-significant-digit limit | Long IDs (credit cards) were already corrupted *in Excel* — flag, don't "fix" |
| 1900 vs 1904 date systems | `xl/workbook.xml` `date1904="1"` (old Mac files) shifts every serial by 4 years — openpyxl handles it; hand-rolled serial math must check |
| Sibling CSV exports are **cp1252**, not UTF-8 (Excel's default export) | DSS usually autodetects `windows-1252` — verify (symptom: `0xa0`/accents garbled). CSV dates export in *display* format — `dd-MM-yyyy` vs `MM-dd-yyyy` is ambiguous; disambiguate from a >12 day value, ship-date coherence, or the source xlsx |
| `.xls` (BIFF, pre-2007) | DSS reads it (same excel format); `openpyxl` does NOT — use `xlrd` for the offline inventory, or convert once |

## Verification

Validation targets, in order: (1) pivot-sheet cached cells (`data_only=True`) vs your Group outputs — exact values, modulo float display rounding; (2) cleaned-table row count vs Table ref; (3) formula-column cached values vs Prepare outputs on spot rows; (4) a shipped dashboard image, if any, for chart shape/series sanity.

The workhorse pattern: `dku dataset download` → pandas diff against the cleaned sheet, **column-complete** (diff EVERY column's value set raw→clean at inventory time — a quiet `10+ Miles` → `More than 10 Miles` recode hides in any column you skip). When a series diverges, read the divergence signature before chasing causes (table in `model-workbooks.md` § Verification — constant offset, sign mirror, seam-exact drift each point somewhere different). When one column won't converge, compute its empirical `(format class, stored value) → cleaned value` mapping before burning cycles — inconsistency within a class means hand-authored data (the hand-authored-column rule above): stop, document, validate the pivots instead.

Float caveat: Excel cached values are full-precision IEEE 754 (`4.27169` may be `4.271689999…`) — compare rounded. (DSS Group `avg` reproduces Excel pivot averages to full double precision — exact compare is usually safe on aggregates.)
