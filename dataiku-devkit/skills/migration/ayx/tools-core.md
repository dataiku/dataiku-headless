# Alteryx Core Tools to Dataiku

Translation details for common row-local and source/input Alteryx tools.

## TextInput

**Alteryx:** inline data in the XML.

```xml
<Configuration>
  <NumRows value="N"/>
  <Fields><Field name="A"/><Field name="B"/></Fields>
  <Data><r><c>1</c><c>x</c></r>...</Data>
</Configuration>
```

**Dataiku:** extract to CSV, upload, set schema.

```python
import xml.etree.ElementTree as ET, csv
root = ET.parse("workflow.yxmd").getroot()
for node in root.findall("./Nodes/Node"):
    if "TextInput" not in node.find("./GuiSettings").get("Plugin", ""):
        continue
    tid = node.get("ToolID")
    cfg = node.find("./Properties/Configuration")
    fields = [f.get("name") for f in cfg.findall("./Fields/Field")]
    rows = [[c.text or "" for c in r.findall("./c")] for r in cfg.findall("./Data/r")]
    with open(f"tool_{tid}.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(fields); w.writerows(rows)
```

Then:

```bash
dku dataset create tool_13 --type UploadedFiles -P PROJ
dku dataset upload tool_13 tool_13.csv -P PROJ
dku dataset set-schema tool_13 -P PROJ -d '[{"name":"Customer ID","type":"bigint"}, …]'
```

**Caveats:** no inferred type from the XML — types come from the first downstream `AlteryxSelect` (or, failing that, user input). Columns with thousand separators or leading zeros come through as STRING and must be cleaned in a Prepare step before casting.

---

## DbFileInput / DbFileOutput

`DbFileInput` is a misnomer — it covers TWO unrelated cases. Look at the `<File>` / `<Connection>` shape to tell them apart:

### DbFileOutput — multi-file output via `MultiFile` + `MultiFileField`

Alteryx `DbFileOutput` with `<MultiFile value="True">` + `<MultiFileType>FileName</MultiFileType>` + `<MultiFileField>output_name</MultiFileField>` writes ONE FILE PER unique value of the `output_name` column. Common pattern: produce per-region or per-product CSVs from a single joined dataset (the canonical "batch output for downstream Excel/PDF stitching" workflow).

```xml
<Configuration>
  <File MaxRecords="" FileFormat="0">.\output.csv</File>
  <MultiFile value="True"/>
  <MultiFileType>FileName</MultiFileType>
  <MultiFileField>Output_Name</MultiFileField>
  <KeepField value="False"/>
</Configuration>
```

**DSS has no direct visual equivalent.** Three migration paths, in order of preference:

1. **Partitioned dataset by the batching field** (the cleanest visual answer). Create the output as a managed Filesystem (or SQL) dataset partitioned on `Output_Name`. DSS writes one folder/partition per value at build time. Subsequent reads can target a specific partition (`dku dataset head OUT --partition Region1_Product1`) or all of them. Caveat: the partition dimension must be a single column already in the dataset. Schema (column names + types) is shared across partitions — Alteryx's per-file behavior is identical.
   ```bash
   # Create partitioned output (CLI shape, illustrative — see dataikuapi for exact partitioning JSON):
   dku dataset create batch_out --type Filesystem -P PROJ
   dku dataset set-definition batch_out -P PROJ -d '{
     "type":"Filesystem","managed":true,
     "partitioning":{"dimensions":[{"name":"Output_Name","type":"value"}],"filePathPattern":"%{Output_Name}/.*"}
   }'
   ```

2. **Single dataset + downstream filter at consumption time.** Skip the multi-file decomposition entirely — keep everything in one wide dataset with the `Output_Name` column intact. Downstream consumers filter to the specific batch they need. This is usually the right call when the "files" exist only to feed another DSS process (chart, scenario, dashboard) — partitioning adds operational overhead with no benefit.

3. **Python recipe with per-group `to_csv`.** Last resort for compatibility with external systems that genuinely consume one file per group. Write to a managed folder, one CSV per `Output_Name` value:
   ```python
   import dataiku
   src = dataiku.Dataset("joined").get_dataframe()
   folder = dataiku.Folder("batch_files")
   for name, sub in src.groupby("Output_Name"):
       with folder.get_writer(f"{name}.csv") as w:
           w.write(sub.drop(columns=["Output_Name"]).to_csv(index=False).encode())
   ```

**The migration loop's expected output for batch-output workflows is usually ONE batch's contents** — the challenge author picked one specific (key1,key2) combination as the test case. Don't try to match all N output files exactly; build the joined+formula upstream pipeline and filter to the documented batch for value-comparison. Tested on Challenge_038: 4 Alteryx tools (2 Joins, 1 Formula, 1 multi-file Output) → 3 DSS recipes (2 Joins + 1 Prepare with `Output_Name`); validated by filtering to `(Region Key=1, Product Key=1)` and matching the 15-row expected sample.

### Case A — ODBC database (DSN-style connection)

**Alteryx:** native DB connection via ODBC DSN.

```xml
<Configuration>
  <Passwords/>
  <Query><![CDATA[SELECT * FROM schema.table]]></Query>
  <Connection>odbc:DSN=...</Connection>
</Configuration>
```

**Dataiku:** create a SQL dataset on the equivalent connection.

```bash
dku dataset create sales --type Snowflake -P PROJ \
    --definition '{"params":{"connection":"snow_prod","mode":"query","query":"SELECT * FROM schema.table"}}'
```

Or for a pure table: `"mode":"table","table":"schema.table"`.

**Caveats:** Alteryx's "Pre SQL Statement" / "Post SQL Statement" don't map 1:1. Move those side-effects to a scenario SQL step (`dku scenario add-step ... --kind exec_sql`) that runs before/after the recipe build.

### Case B — File-based input (Excel / Access / SQLite, often with a wildcard)

**Alteryx:**

```xml
<Configuration>
  <Passwords/>
  <File OutputFileName="FileName" RecordLimit="" SearchSubDirs="True" FileFormat="8">.\*.xls|`Sheet1$`</File>
  <FormatSpecificOptions>
    <FirstRowData>True</FirstRowData>
    <NoProgress>False</NoProgress>
  </FormatSpecificOptions>
</Configuration>
```

Tells: `<File>` path + `FileFormat` numeric code (`8` = Excel, `9` = Access, `25` = SQLite). The `|`Sheet1$`` suffix selects a sheet. `OutputFileName="FileName"` adds a column named `FileName` to the output records carrying the source filename per row. `<FirstRowData>True</FirstRowData>` means the first row of each sheet is treated as DATA (not header) — Alteryx auto-names columns `F1, F2, F3, …` and the literal header row appears as a data row.

**Dataiku:** there is no one-shot CLI verb that reproduces "read every `*.xls` in a folder, concatenate, add a `FileName` column". Two paths:

1. **Native multi-file dataset** (preferred when the files share a schema and live in DSS-managed storage). Put the files in a managed folder, then create a Filesystem dataset over the folder with format `excel` (or `csv`). The dataset's `partitioning.filePathPattern` can capture the filename as a partition dimension; otherwise read with `dataikuapi`'s `iter_dataframes` and project the per-file path. CLI support is partial — `dku dataset create --type Filesystem` plus a `set-definition` JSON edit for `params.filesSelectionRules` and `formatType: excel`.
2. **Pre-bake offline** (preferred for migration loops with a small fixed file list). Convert each file locally to CSV with `pandas.read_excel`, prepend a `FileName` literal column and (optionally) a `row_idx` 1..N counter, concatenate, then `dku dataset create --type UploadedFiles` + `dku dataset upload`. This collapses the downstream `MultiRowFormula(Row=row_within_file)` step (see § MultiRowFormula collapse hints + `ayx/overview.md` § Collapse triggers).

**Caveats:**
- `<FirstRowData>True</FirstRowData>` means the literal header row IS in the data stream. If you need column names from the header instead, set the CSV upload to header-aware AND skip Alteryx's auto-`F1..F4` naming (DSS will use the actual column names). If you need to mimic Alteryx exactly (header-row visible in the row stream), keep all rows AND name the columns `F1..F4` at conversion time.
- `OutputFileName` in Alteryx returns the FULL filesystem path. If the downstream logic only uses the basename (stripped of `.xls`), strip it at conversion time — saves a Prepare step.
- Alteryx wildcard reads files in OS lexicographic order. DSS multi-file datasets do too — but `MultiRowFormula(Row=row_within_file)` depends on row-within-file ordering, which is preserved by both the native multi-file path AND the pre-baked path.

---

## Formula

**Alteryx:**

```xml
<Configuration>
  <FormulaFields>
    <FormulaField expression="[Price] * [Qty]" field="Total" size="4" type="Double"/>
    <FormulaField expression="IF [Qty]&gt;10 THEN 'Bulk' ELSE 'Single' ENDIF" field="Bucket" size="254" type="V_WString"/>
  </FormulaFields>
</Configuration>
```

**Dataiku:** Prepare recipe with one `CreateColumnWithGREL` step per formula field.

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

> **Numeric formulas on hyphenated/spaced columns — use `numval`, not `val`.** GREL bareword `Anti-Gravity Speed` parses as subtraction (`Anti` minus `Gravity Speed`) and `val("Anti-Gravity Speed")` returns a string that breaks downstream arithmetic. Use `numval("Anti-Gravity Speed")` (or `strval(...)` for explicit string casts) on every non-identifier column reference. The conventions section (top of file) covers this for all tools — restating here because Formula is the most common slip-up.

### Alteryx formula → GREL cheatsheet

| Alteryx | GREL |
|---|---|
| `[Field]` | `Field` if it is a valid identifier; otherwise `val("Field")`, `numval("Field")`, or `strval("Field")` depending on intended type |
| `IF a THEN b ELSE c ENDIF` | `if(a, b, c)` |
| `IF a THEN b ELSEIF c THEN d ELSE e ENDIF` | `if(a, b, if(c, d, e))` |
| `Length([s])` | `length(s)` |
| `Left([s], n)` | `substring(s, 0, n)` |
| `Right([s], n)` | `substring(s, length(s)-n)` |
| `Substring([s], start, n)` | `substring(s, start, start+n)` — Alteryx `start` is 0-indexed; GREL is 0-indexed too ✓ |
| `Trim([s])` | `strip(s)` |
| `Trim([s], 'X')` (charset form, e.g. `Trim([Field1], '0')` to strip both leading AND trailing zeros) | `replace(s, /^[X]+|[X]+$/, "")` — GREL has no `strip(s, charset)` overload. For leading-only zeros use `replace(s, /^0+/, "")`. Alteryx `Trim(s, charset)` is bidirectional; GREL `strip(s)` only strips whitespace. |
| `LTrim([s])` / `RTrim([s])` | `replace(s, /^\s+/, "")` / `replace(s, /\s+$/, "")` — no GREL helper; regex form is canonical. Charset variants (`LTrim([s], 'X')`) follow the same `replace(s, /^[X]+/, "")` pattern. |
| `Uppercase([s])` / `Lowercase([s])` / `Titlecase([s])` | `toUppercase(s)` / `toLowercase(s)` / `toTitlecase(s)` |
| `Replace([s], "a", "b")` | `replace(s, "a", "b")` — literal substring in both |
| `REGEX_Replace([s], "pat", "r")` | `replace(s, /pat/, "r")` — regex via slash-delimiters |
| `Contains([s], "x")` | `contains(s, "x")` |
| `StartsWith([s], "x")` / `EndsWith` | `startsWith(s, "x")` / `endsWith(s, "x")` |
| `ToString([x])` | `toString(x)` — but for int→string pushed to SQL, use `concat("", x)` (see sql-engines.md) |
| `ToNumber([s])` | `toNumber(s)` |
| `Null()` | `""` (empty = NULL in GREL), or `null()` in newer DSS |
| `IsNull([x])` | `isnull(x)` or `x == ""` on string columns |
| `IsEmpty([x])` | `isBlank(x)` |
| `Ceil([x])`, `Floor([x])`, `Round([x], n)` | `ceil(x)`, `floor(x)`, `round(x, n)` |
| `Abs([x])` | `abs(x)` |
| `Mod([x], y)` | `x % y` |
| `DateTimeNow()` | `now()` |
| `DateTimeFormat([d], "%Y-%m-%d")` | Prepare `DateFormatter` step — GREL `formatDate()` does NOT exist. Format tokens differ (%Y→yyyy, %m→MM, %d→dd, %H→HH, %M→mm, %S→ss) |
| `DateTimeParse([s], "%Y-%m-%d")` | Prepare `DateParser` step — GREL `toDate()` does NOT work |
| `DateTimeAdd([d], n, "days")` | `inc(d, n, "days")` — NOT `computeDate()` (does not exist). Unit must be plural. **`inc()` requires a DATE-typed input** — `inc(strval("Month"), 1, "months")` on a STRING column returns the original string unchanged (silent). Two paths: (a) **inline GREL one-shot** — `toString(inc(asDateOnly(strval("Month"), "yyyy-MM-dd"), 1, "months"))` parses, increments, and formats in a single `add-formula`; or (b) **three Prepare steps** — `DateParser(Month → Month_dt)` → `add-formula 'inc(val("Month_dt"), 1, "months")' → month_plus_1` → `DateFormatter(month_plus_1 → month_plus_1_iso)`. Path (a) is cleaner for one-off increments; path (b) is preferred when the parsed date is reused across multiple computations. Use `val("col")` (NOT `numval`/`strval`) when passing a date column to `inc()`. |
| `DateTimeDiff([a], [b], "days")` | `diff(a, b, "days")` — NOT `diffDate()` (does not exist). Operand order is preserved (`d1 - d2`, same convention as Alteryx). Unit must be plural (`"days"`, `"hours"`, `"seconds"`, …). |

**Gotcha:** GREL date functions (`diff`, `inc`, `formatDate`-equivalents) only operate on date-typed values. CSV-loaded columns are strings — wrap with `asDatetimeNoTz(col, "yyyy-MM-dd HH:mm:ss")` (or `asDateOnly` for date-only) inside the formula. There is NO `parseDate()` or `toEpoch()` in GREL — agents trained on Excel/JS-style functions will reach for these and get `Unknown function` errors.

**Gotcha:** Alteryx truthiness: non-zero / non-empty is true. GREL requires explicit booleans — convert `IF [Count] THEN …` → `if(Count > 0, …)`.

**Gotcha:** Alteryx `[_CurrentField_]` is a row-builder pattern for applying the same formula across many columns via the Multi-Field Formula tool. In DSS, use a Prepare step with multiple column selection, or loop in Python.

---

## AlteryxSelect

**Alteryx:** renames, retypes, reorders, and drops columns — all in one tool.

```xml
<Configuration>
  <OrderChanged value="True"/>
  <SelectFields>
    <SelectField field="Col1" selected="True" rename="A" type="Int32" size="4"/>
    <SelectField field="Col2" selected="False"/>  <!-- drop -->
    <SelectField field="Col3" selected="True" type="Double" size="8"/>  <!-- retype, keep name -->
    <SelectField field="*Unknown" selected="True"/>  <!-- keep any future columns -->
  </SelectFields>
</Configuration>
```

**Dataiku:** single Prepare recipe with multiple steps.

```bash
# Rename
--step '{"type":"ColumnRenamer","params":{"renamings":[{"from":"Col1","to":"A"}]}}'
# Drop
--step '{"type":"ColumnsSelector","params":{"columns":["Col2"],"keep":false}}'
# Retype (cast)
--step '{"type":"CastTypes","params":{"columnNames":["A"],"typesMap":{"A":"bigint"}}}'
# Reorder (the visible column order in the output schema)
--step '{"type":"ColumnsSelector","params":{"columns":["A","Col3","*"],"keep":true}}'
```

**Caveats:**
- `*Unknown selected=True` means "pass through any other column" — in DSS, this is the default (unselected steps don't drop columns). No action needed.
- `*Unknown selected=False` means "drop any other column" — use `ColumnsSelector keep:true` with the explicit list.
- Alteryx `size` on `AlteryxSelect`'s `<SelectField>` is a declared-width hint (no truncation); DSS strings are unbounded. **But** `size` on a `<FormulaField>` (in a `Formula` step) **does** silently truncate the formula output to N chars — see `semantics.md` § Data types. Treat `Formula(size=N)` as a behavioral difference, not metadata.

---

## Filter

**Alteryx:** one condition; True output goes to `True` connection, False output goes to `False`.

```xml
<Configuration>
  <Mode>Simple|Custom</Mode>
  <Expression>[Status] = "A" AND [Amount] &gt; 0</Expression>
</Configuration>
```

**Dataiku:**

- **Only True branch used** → `dku recipe create-filter` (Prepare with `FilterOnCustomFormula`).
  ```bash
  dku recipe create-filter f_active -i in --output-ds active \
      -f 'Status == "A" && Amount > 0' -P PROJ
  ```
- **Both True and False branches consumed** → **Split recipe**, pre-compute the condition as a column, route each value to a separate output dataset. Cleaner than two inverse filters; schema, metrics, and lineage stay coherent.

**Caveats:**
- Alteryx `=` → GREL `==`; `AND` → `&&`; `OR` → `||`; `NOT` → `!`.
- Alteryx's "Basic" mode shows range pickers etc.; the compiled `Expression` is what ships. Read that, not the UI hints.
- Remember Prepare recipes sample the input at edit time — the filter runs on the full dataset at build, but the preview is sampled. Tell the user if their sample doesn't match their expectation.

---

## Sort

**Alteryx:**

```xml
<Configuration>
  <SortInfo>
    <Field field="Col1" order="Ascending"/>
    <Field field="Col2" order="Descending"/>
  </SortInfo>
</Configuration>
```

**Dataiku:** Sort recipe.

```bash
dku recipe create-sort sort_x -i in --output-ds sorted \
    -P PROJ --sort-by 'Col1:asc,Col2:desc'
```

---

## Sample

**Alteryx:** four modes — `First N`, `Last N`, `Skip 1st N`, `1 in every N`, `Random N%`.

**Dataiku:**
- `First N` → Top N recipe, sort ascending by RecordID, limit N.
- `Last N` → Top N recipe with descending sort, limit N, then re-reverse.
- `Skip 1st N` → Window recipe, add `ROW_NUMBER`, filter `row_num > N`.
- `Random N%` → Sample recipe (built-in sampling).
- `1 in every N` → Window + modulo on row_num (`row_num % N == 0`).

---

## Unique

**Alteryx:** groups by the selected `UniqueFields` and keeps the first row per group; remaining rows go to a `Duplicates` output. **Non-key columns are preserved on the kept row.**

```xml
<Configuration>
  <UniqueFields>
    <Field name="Col1"/><Field name="Col2"/>
  </UniqueFields>
</Configuration>
```

**Dataiku:** this is where the naive `Distinct` answer is wrong. Distinct deduplicates on the full row — if you run it after dropping non-key columns, you lose them; if you run it without dropping, same-key rows with different non-key values all survive. Two correct paths:

1. **Window recipe** (preferred when order matters): partition by the Unique keys, order by a tiebreak column (e.g. RecordID), add `ROW_NUMBER` as `rank`, post-filter `rank == 1`. Every non-key column is preserved because Window carries them through.
   ```bash
   dku recipe create-window win_uniq -P PROJ -i in --output-ds deduped \
       --partition Col1,Col2 --order-by rec_id:asc \
       --agg 'rec_id:row_number:rank'
   # Then Prepare: FilterOnCustomFormula  rank == 1
   ```
2. **Group recipe with `first`** aggregation on every non-key column: GroupBy on the Unique keys, `first` on everything else. Output columns become `{col}_first` — follow with a Prepare `ColumnRenamer` to restore original names. Works when order sensitivity is explicit (requires an upstream Sort).

**Caveats:**
- Alteryx `Unique` is stable by input row order. On a SQL engine, a Window recipe's `ROW_NUMBER` needs an explicit `ORDER BY` — use `AddId` upstream if the input has no natural ordering key.
- If Alteryx's `Duplicates` output is consumed downstream (dup detection / DQ), wire it as a second output: Window with `rank != 1` filter.

---
