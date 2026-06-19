# Alteryx Core Tools to Dataiku

Row-local + source/input tools: TextInput, DbFileInput/Output, Formula (+ GREL cheatsheet), AlteryxSelect, Filter, Sort, Sample, Unique.

## TextInput

Inline data in the workflow XML (`<NumRows>`, `<Fields>`, `<Data><r><c>…`). No external file.

Extract → upload → set schema:

```bash
uv run python scripts/extract_textinput.py workflow.yxmd -o ./out   # one tool_<ToolID>.csv per TextInput
dku dataset create tool_13 --type UploadedFiles -P PROJ
dku dataset upload tool_13 out/tool_13.csv -P PROJ
dku dataset set-schema tool_13 -P PROJ -d '[{"name":"Customer ID","type":"bigint"}, …]'
```

- Types are NOT in the XML — set them from the first downstream `AlteryxSelect` (else STRING). Thousand-separators / leading-zeros arrive STRING; clean in a Prepare step before casting.
- Single-column or delimited/quoted inline data mis-parses on upload — see `overview.md` "Single-column TextInput upload traps" before uploading.

---

## DbFileInput / DbFileOutput

`DbFileInput` covers TWO unrelated cases — read the `<File>` / `<Connection>` shape to tell them apart.

### DbFileOutput — multi-file output (`MultiFile` + `MultiFileField`)

`<MultiFile value="True">` + `<MultiFileType>FileName</MultiFileType>` + `<MultiFileField>Output_Name</MultiFileField>` writes ONE FILE PER unique value of the named column (per-region / per-product CSVs from one joined dataset).

DSS has no direct visual equivalent. Migration paths, in order:

| Path | When | How |
|---|---|---|
| **Partitioned dataset** (cleanest) | batching field is a single existing column | managed Filesystem/SQL dataset partitioned on `Output_Name`; one folder/partition per value at build. Read one (`dku dataset head OUT --partition Region1_Product1`) or all. Schema shared across partitions (matches Alteryx per-file). |
| **Single dataset + downstream filter** (usual right call) | "files" only feed another DSS process (chart/scenario/dashboard) | keep one wide dataset with `Output_Name` intact; consumers filter. No partitioning overhead. |
| **Python recipe per-group `to_csv`** (last resort) | external system genuinely needs one file per group | `for name, sub in src.groupby("Output_Name"): folder.get_writer(f"{name}.csv")` writing `sub.drop(columns=["Output_Name"]).to_csv(index=False)` to a managed folder. |

Partitioned-dataset definition shape:
```bash
dku dataset create batch_out --type Filesystem -P PROJ
dku dataset set-definition batch_out -P PROJ -d '{
  "type":"Filesystem","managed":true,
  "partitioning":{"dimensions":[{"name":"Output_Name","type":"value"}],"filePathPattern":"%{Output_Name}/.*"}
}'
```

Expected output for batch-output workflows is usually ONE batch's contents — the author picks one key combo as the test case. Build the joined+formula upstream pipeline and filter to the documented batch for value-comparison; don't match all N files.

### Case A — ODBC database (DSN connection)

`<Query><![CDATA[SELECT …]]></Query>` + `<Connection>odbc:DSN=…`. Create a SQL dataset on the equivalent connection:

```bash
dku dataset create sales --type Snowflake -P PROJ \
    --definition '{"params":{"connection":"snow_prod","mode":"query","query":"SELECT * FROM schema.table"}}'
```
Pure table: `"mode":"table","table":"schema.table"`.

- Alteryx "Pre/Post SQL Statement" don't map 1:1 — move those side-effects to a scenario SQL step (`dku scenario add-step … --kind exec_sql`) that runs before/after the build.

### Case B — File-based input (Excel / Access / SQLite, often wildcard)

Tells: `<File>` path + numeric `FileFormat` (`8`=Excel, `9`=Access, `25`=SQLite); `|`Sheet1$`` suffix selects a sheet; `OutputFileName="FileName"` adds a `FileName` column carrying the source filename per row; `<FirstRowData>True</FirstRowData>` means row 1 is DATA not header — Alteryx auto-names columns `F1,F2,…` and the literal header appears as a data row.

No one-shot CLI verb for "read every `*.xls` in a folder, concat, add `FileName`". Two paths:

| Path | When | How |
|---|---|---|
| **Native multi-file dataset** | files share schema, live in DSS-managed storage | files in a managed folder → Filesystem dataset, format `excel`/`csv`; capture filename via `partitioning.filePathPattern` else project per-file path with `dataikuapi iter_dataframes`. CLI partial: `dku dataset create --type Filesystem` + `set-definition` JSON for `params.filesSelectionRules` and `formatType:excel`. |
| **Pre-bake offline** | migration loop, small fixed file list | `pandas.read_excel` each → prepend `FileName` literal + optional `row_idx` 1..N → concat → `dku dataset create --type UploadedFiles` + `upload`. Collapses a downstream `MultiRowFormula(Row=row_within_file)` step (see `tools-state-parsing.md` § MultiRowFormula + `overview.md` § Collapse triggers). |

- `<FirstRowData>True</FirstRowData>`: literal header is in the data stream. Want names from the header → set CSV upload header-aware and skip the auto-`F1..F4` naming. Want to mimic Alteryx exactly → keep all rows AND name columns `F1..F4` at conversion.
- `OutputFileName` returns the FULL path. If downstream only uses the basename, strip it at conversion — saves a Prepare step.
- Wildcard reads in OS lexicographic order; both DSS paths preserve row-within-file ordering that `MultiRowFormula(Row=…)` depends on.

---

## Formula

`<FormulaField expression="…" field="…" size="…" type="…"/>` per field → Prepare recipe, one `CreateColumnWithGREL` step per field.

```bash
dku recipe create-prepare prep_formula -i in --output-ds out -P PROJ
dku recipe add-step prep_formula -P PROJ --step '{
  "type": "CreateColumnWithGREL",
  "params": {"expression": "Price * Qty", "column": "Total"}
}'
dku recipe add-step prep_formula -P PROJ --step '{
  "type": "CreateColumnWithGREL",
  "params": {"expression": "if(Qty > 10, \"Bulk\", \"Single\")", "column": "Bucket"}
}'
```

> **Numeric formulas on hyphenated/spaced columns — use `numval`, not `val`.** Bareword `Anti-Gravity Speed` parses as subtraction; `val("Anti-Gravity Speed")` returns a string that breaks arithmetic. Use `numval("col")` (or `strval(...)` for string casts) on every non-identifier column reference.

> **On a SQL target, keep every Formula step SQL-translatable.** A single non-translatable GREL function (`split`/`hash`/`strval`/`arrayContains`/regex) demotes the *whole* Prepare recipe to `Engine: DSS` and kills push-down (one engine per flow). Check which GREL functions/processors keep push-down: `../../dku-cli/references/prepare-processors.md`.

### Alteryx formula → GREL cheatsheet

| Alteryx | GREL |
|---|---|
| `[Field]` | `Field` if valid identifier; else `val("Field")`, `numval("Field")`, or `strval("Field")` by intended type |
| `IF a THEN b ELSE c ENDIF` | `if(a, b, c)` |
| `IF a THEN b ELSEIF c THEN d ELSE e ENDIF` | `if(a, b, if(c, d, e))` |
| `Length([s])` | `length(s)` |
| `Left([s], n)` | `substring(s, 0, n)` |
| `Right([s], n)` | `substring(s, length(s)-n)` |
| `Substring([s], start, n)` | `substring(s, start, start+n)` — both 0-indexed ✓ |

> **Slicing a zero-padded STRING column? Use `strval("s")`, not bareword `s`.** When the column is digit-only with significant leading zeros (zero-padded IDs, `YYMMDD`/`HHMMSS`, ZIP-like keys), the bareword forms (`substring(s,…)`, `Left/Right` translations) coerce `s` to a number and drop leading zeros *before* slicing — `Left([date],1)` on `"0990930"` reads `990930`, wrong char. Write `substring(strval("date"), 0, 1)` on every slice. (Common in "string→date" where the leading digit is a century/era flag.) Platform-wide — see `../../dku-cli/references/formulas.md` § Quick gotchas.

| Alteryx | GREL |
|---|---|
| `Trim([s])` | `strip(s)` |
| `Trim([s], 'X')` (charset, bidirectional) | `replace(s, /^[X]+|[X]+$/, "")` — no `strip(s, charset)`; leading-only zeros: `replace(s, /^0+/, "")`. `strip(s)` strips whitespace only |
| `LTrim([s])` / `RTrim([s])` | `replace(s, /^\s+/, "")` / `replace(s, /\s+$/, "")` — no helper; charset variant: `replace(s, /^[X]+/, "")` |
| `Uppercase` / `Lowercase` / `Titlecase([s])` | `toUppercase(s)` / `toLowercase(s)` / `toTitlecase(s)` |
| `Replace([s], "a", "b")` | `replace(s, "a", "b")` — literal substring both |
| `REGEX_Replace([s], "pat", "r")` | `replace(s, /pat/, "r")` — slash-delimited regex |
| `Contains([s], "x")` | `contains(s, "x")` |
| `StartsWith` / `EndsWith([s], "x")` | `startsWith(s, "x")` / `endsWith(s, "x")` |
| `ToString([x])` | `toString(x)` — but int→string pushed to SQL: `concat("", x)` (see `../../dku-cli/playbooks/tabular-flow.md`) |
| `ToNumber([s])` | `toNumber(s)` |
| `Null()` | `""` (empty = NULL in GREL), or `null()` newer DSS |
| `IsNull([x])` | `isnull(x)` or `x == ""` on strings |
| `IsEmpty([x])` | `isBlank(x)` |
| `Ceil` / `Floor([x])`, `Round([x], n)` | `ceil(x)`, `floor(x)`, `round(x, n)` |
| `Abs([x])` | `abs(x)` |
| `Mod([x], y)` | `x % y` |
| `DateTimeNow()` | `now()` |
| `DateTimeFormat([d], "%Y-%m-%d")` | Prepare `DateFormatter` step — GREL `formatDate()` does NOT exist. Tokens differ (%Y→yyyy, %m→MM, %d→dd, %H→HH, %M→mm, %S→ss) |
| `DateTimeParse([s], "%Y-%m-%d")` | Prepare `DateParser` step — GREL `toDate()` does NOT work |
| `DateTimeAdd([d], n, "days")` | `inc(d, n, "days")` — NOT `computeDate()`. Unit plural. **`inc()` needs a DATE-typed input** — `inc(strval("Month"), 1, "months")` on STRING returns the string unchanged (silent). (a) **inline one-shot**: `toString(inc(asDateOnly(strval("Month"), "yyyy-MM-dd"), 1, "months"))`; (b) **three steps**: `DateParser(Month→Month_dt)` → `add-formula 'inc(val("Month_dt"), 1, "months")'→month_plus_1` → `DateFormatter(month_plus_1→…_iso)`. (a) for one-offs, (b) when the parsed date is reused. Use `val("col")` (not `numval`/`strval`) passing a date to `inc()`. |
| `DateTimeDiff([a], [b], "days")` | `diff(a, b, "days")` — NOT `diffDate()`. Order preserved (`d1 - d2`, as Alteryx). Unit plural. |

**Date RENDERING parity — when the Alteryx output field is a `Date` (not DateTime), finish with `DateFormatter` → string `yyyy-MM-dd`.** A DSS date-typed column (DateParser output) renders `2005-04-16 00:00:00` (+TZ) in `head`/JSON reads, so exact-match/diff verification against the Alteryx output fails on EVERY row even though the parse is correct. SAS sibling of the same quirk: `../sas/functions-formats.md` § verification.

> **Military / variable-width time string (`HHMM` or `HMM`) → `HH:MM` + elapsed minutes** — the Alteryx `PadLeft([t],4,"0") → Left(...,2)/Right(...,2) → DateTimeDiff` idiom. **Split by LENGTH, do NOT left-pad-then-slice.** The `"0000"+[t]`-then-slice approach is off-by-one (3-char `"815"` → `"815"`, not `"0815"`). Robust pattern, all 3-arg `substring`:
> ```
> // hour (1-2 digit), minute (always last 2) — works for "815" and "1045"
> hour   = substring(strval("t"), 0, length(strval("t"))-2)
> minute = substring(strval("t"), length(strval("t"))-2, length(strval("t")))
> // 12-hour clock (no AM/PM): if(h>12, h-12, h), zero-padded
> h12 = replace(toString(if(toNumber(hour)>12, toNumber(hour)-12, toNumber(hour))), /\.0$/, "")
> "Begin Time" = if(isNonBlank(strval("t")) && strval("t")!="TBA", (if(length(h12)==1,"0"+h12,h12)) + ":" + minute, "")
> ```
> **Elapsed minutes without a date:** `DateTimeDiff` needs date-typed args; skip it — compute `(toNumber(h2)*60+toNumber(m2)) - (toNumber(h1)*60+toNumber(m1))`. Guard `if(both valid, …, "")` so `"TBA"`/empty rows stay blank. **Pin the elapsed column to `string` (`set-schema` + re-run WITHOUT `apply-schema`)** or digit-only values infer `bigint` and blank `""` rows come back null (renders `None`) — see `../../dku-cli/references/formulas.md` § Output-type inference.

**Gotchas:**
- GREL date functions (`diff`, `inc`, `formatDate`-equivalents) only operate on date-typed values. CSV columns are strings — wrap with `asDatetimeNoTz(col, "yyyy-MM-dd HH:mm:ss")` (or `asDateOnly` for date-only) inside the formula. There is NO `parseDate()` or `toEpoch()` in GREL — agents reach for these and get `Unknown function`.
- Alteryx truthiness: non-zero/non-empty is true. GREL needs explicit booleans — `IF [Count] THEN …` → `if(Count > 0, …)`.
- Alteryx `[_CurrentField_]` (Multi-Field Formula tool) → DSS Prepare step with multiple-column selection, or loop in Python.

---

## AlteryxSelect

Renames, retypes, reorders, and drops columns in one tool (`<SelectField field rename type size selected>`). `*Unknown` = pass-through rule. → single Prepare recipe, multiple steps:

```bash
# Rename
--step '{"type":"ColumnRenamer","params":{"renamings":[{"from":"Col1","to":"A"}]}}'
# Drop
--step '{"type":"ColumnsSelector","params":{"columns":["Col2"],"keep":false}}'
# Retype (cast)
--step '{"type":"CastTypes","params":{"columnNames":["A"],"typesMap":{"A":"bigint"}}}'
# Reorder (visible output schema order)
--step '{"type":"ColumnsSelector","params":{"columns":["A","Col3","*"],"keep":true}}'
```

- `*Unknown selected=True` = "pass through any other column" — DSS default (unselected steps don't drop). No action.
- `*Unknown selected=False` = "drop any other column" — use `ColumnsSelector keep:true` with the explicit list.
- `size` on `AlteryxSelect`'s `<SelectField>` is a declared-width hint (no truncation); DSS strings unbounded. **But** `size` on a `<FormulaField>` (Formula step) **does** silently truncate output to N chars — see `semantics.md` § Data types. Treat `Formula(size=N)` as a behavioral difference, not metadata.

---

## Filter

One condition; True output → `True` connection, False → `False`.

- **Only True branch used** → `dku recipe create-filter` (Prepare with `FilterOnCustomFormula`):
  ```bash
  dku recipe create-filter f_active -i in --output-ds active -f 'Status == "A" && Amount > 0' -P PROJ
  ```
- **Both branches consumed** → **Split recipe**, or one Prepare with branching GREL: pre-compute the condition as a column, route each value to a separate output dataset. Cleaner than two inverse filters; schema/metrics/lineage stay coherent.

- Alteryx `=`→`==`, `AND`→`&&`, `OR`→`||`, `NOT`→`!`.
- "Basic" mode shows pickers; the compiled `<Expression>` is what ships — read that, not UI hints.
- Prepare recipes sample input at edit time — filter runs on the full dataset at build, preview is sampled. Warn the user if their sample doesn't match expectation.

---

## Sort

`<SortInfo><Field field order="Ascending|Descending"/>` → Sort recipe.

```bash
dku recipe create-sort sort_x -i in --output-ds sorted -P PROJ --sort-by 'Col1:asc,Col2:desc'
```

---

## Sample

| Alteryx mode | Dataiku |
|---|---|
| `First N` | Top N recipe, sort ascending by RecordID, limit N |
| `Last N` | Top N recipe, descending sort, limit N, then re-reverse |
| `Skip 1st N` | Window recipe, add `ROW_NUMBER`, filter `row_num > N` |
| `Random N%` | Sample recipe (built-in sampling) |
| `1 in every N` | Window + modulo on row_num (`row_num % N == 0`) |

---

## Unique

Groups by `<UniqueFields>` and keeps the first row per group; remaining rows → `Duplicates` output. **Non-key columns are preserved on the kept row.**

Naive `Distinct` is wrong: it dedups on the full row — drop non-key columns first and you lose them; keep them and same-key rows with differing values all survive. Two correct paths:

1. **Window recipe** (preferred when order matters): partition by the Unique keys, order by a tiebreak (e.g. RecordID), add `ROW_NUMBER` as `rank`, post-filter `rank == 1`. Window carries every non-key column through.
   ```bash
   dku recipe create-window win_uniq -P PROJ -i in --output-ds deduped \
       --partition Col1,Col2 --order-by rec_id:asc --agg 'rec_id:row_number:rank'
   # Then Prepare: FilterOnCustomFormula  rank == 1
   ```
2. **Group recipe with `first`** on every non-key column: GroupBy the Unique keys, `first` on everything else. Output columns become `{col}_first` — follow with a Prepare `ColumnRenamer` to restore names. Requires an upstream Sort for order sensitivity.

- Alteryx `Unique` is stable by input row order. On a SQL engine, Window `ROW_NUMBER` needs explicit `ORDER BY` — bake `row_idx` at extraction if the input has no natural ordering key (no AddId Prepare processor — see `tools-state-parsing.md` § RecordID).
- If Alteryx's `Duplicates` output is consumed downstream (dup detection / DQ), wire it as a second output: Window with `rank != 1` filter.
