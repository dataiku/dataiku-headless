# Alteryx tool → Dataiku recipe translation

Open this when you are configuring a specific recipe. Each section: the Alteryx XML shape → Dataiku recipe / Prepare step → code recipe fallback → caveats.

**Conventions:** Alteryx field refs are `[Field Name]`; DSS GREL refs use bareword identifiers only when the column name is a valid identifier (`Price`, `Qty`). For column names with spaces or punctuation, use quoted-name accessors such as `numval("Sales Rep")`, `strval("Postal Area")`, or `val("Field Name")` — never backticks. Alteryx types map as: `Int32/Int64 → bigint`, `Double/Float → double`, `V_String/V_WString/String → string`, `Date → string` (leave as string at ingest; parse with `DateParser`), `DateTime → string`, `Bool → boolean`.

---

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

## Join

**Alteryx:** three outputs — `Left` (rows only in left), `Join` (matched), `Right` (rows only in right). A wire from each output can fan out independently.

```xml
<Configuration joinByRecordPos="False">
  <JoinInfo connection="Left"><Field field="id"/></JoinInfo>
  <JoinInfo connection="Right"><Field field="id"/></JoinInfo>
</Configuration>
```

**Dataiku:** Join recipe. Type depends on which Alteryx outputs are used:
- Only `Join` consumed → **Inner**
- `Join` + `Left` consumed (separately) → Inner into one output + **Antijoin** (first-class type in recent DSS; check `dku recipe create-join --help`) into another; fallback is Inner + Left-Outer with a downstream filter.
- All three separately → cleanest is **Full Outer Join** into one recipe; then downstream filter on match status.
- DSS Join's "non-matching columns" option (where available) can also emit an extra output containing the unmatched rows, so the three Alteryx outputs can come from one Join recipe with two outputs + an antijoin.

```bash
dku recipe create-join jn -P PROJ \
    --inputs left,right \
    --output-ds joined \
    --type inner \
    --condition 'left.id == right.id'
```

**Caveats:**
- Column collision: if both sides have `name`, the right side comes through as `name_1`. Rename upstream.
- `joinByRecordPos="True"` (positional join) — Alteryx aligns rows by record index. DSS has no positional-join visual recipe. **First, look for a derivable common key**: positional joins in Alteryx often exist because the data was extracted from text/CSV without a key column, but a key can be reconstructed (e.g., concat / strip-suffix / parse-prefix). Tested on Challenge_031: left side had `Surf Site = "Tamarack St."`, right side had `Site = "Tamarack St. - San Diego County"` — adding `add-formula Site = concat(Surf Site, " - San Diego County")` to the left and joining on `Site = Site` reproduces the positional-join result exactly (and is more robust to ordering changes). **Only when no common key is derivable** fall back to: Window with `--compute rowNumber::idx` on each side (no partition; default ordering by an existing positional column) → Join on the row-number columns. The Window+Window+Join chain is 3 recipes vs 1 for the derived-key approach. **If neither input has a stable order column** (raw uploaded CSV with no positional field), prepend a `row_id` column at upload time — DSS Prepare has NO row-counter processor (verified Challenge_033: `add-step --type Enumerator` accepts at step-add time but fails at run-time with the misleading `UnavailableTypeException: Type Enumerator was available in a plugin that is not installed`), and Window's `rowNumber` aggregation requires an order-by column. Pre-baking the index in the Python extraction (`csv.writer` with `enumerate(rows)`, schema-set `row_id` to `bigint`) is the cleanest path; if the source is already a managed dataset, materialize one Window-with-rowNumber over the full input first, then proceed. Tested on Challenge_033 (Nielsen reshape): `joinByRecordPos="True"` between filtered metadata (30 rows) and filtered metric (30 rows) collapsed to: pre-bake `row_id` at upload → Prepare for Branch A (filter+formula+rename, surfaces `Code = 1..30` as a natural position key) → Window for Branch B (`lead` + post-filter to identify metric rows) → Window for Branch B index (`rowNumber` 1..30) → Join on `Code = rownumber`. The `rowNumber` output column is hardcoded by DSS to `rownumber` (lowercase), the `--compute 'rowNumber::idx'` third segment is advisory and silently ignored — reference `rownumber` in the join key, or `--rename 'rownumber:idx'` to force the override (works for Window output schema; remember the post-filter ordering trap above).
- Alteryx Join silently drops rows where the key is null on either side (matches SQL semantics). DSS Join does the same.
- `--cols 'INDEX:c1,c2,c3'` is **silently ignored** at the moment (writes `selectedColumns` as a plain string list; DSS Join requires `[{"name", "table", "type"}, ...]` dict objects and falls back to AUTO mode when the dict shape is missing). Until fixed, drop unwanted columns via a downstream Prepare `add-step ColumnsSelector keep=false`. See `dku-cli/references/common-gotchas.md`.

---

## JoinMultiple

**Alteryx:** N-way join on a single key.

**Dataiku:** chain 2-way Join recipes (one per additional input) or use a SQL recipe with multiple `JOIN` clauses. For 3+ inputs on a SQL connection, the SQL recipe is cleaner; for all-in-memory, chain Joins.

---

## AppendFields (cartesian)

**Alteryx:** cartesian product of two inputs (Target × Source).

**Dataiku:** Join recipe with `type: CROSS` (if supported), else a SQL recipe: `SELECT * FROM a CROSS JOIN b`. In Python: `a.assign(_k=1).merge(b.assign(_k=1), on="_k").drop("_k", axis=1)`.

**Single-row broadcast (the most common Alteryx use of AppendFields).** When the Source side is **one row** synthesized upstream by `Sample(First 1) → Formula(extract field from row 0)` — i.e. the workflow is just stamping every Target row with a value derived from the input's first row (a date in the title cell, a report parameter, a global stamp) — there is no cartesian. Skip both the Sample/Formula branch AND the AppendFields. Instead, fold them into the Target's Prepare:

```bash
dku recipe add-formula PREP --column Date --expr 'if(startsWith(F1, "Ranks as of "), substring(F1, 12), null)'
dku recipe add-step PREP --type UpDownFiller -p '{"columns":["Date"],"up":false}'
```

The first row sets `Date`, every other row gets `null`, then `UpDownFiller(up:false)` fills `null` cells with the previous non-null value — broadcasting the row-0 value to all rows. **Only NULL triggers fill; empty string `""` does not** (see `dataiku/references/prepare-processors.md` § UpDownFiller). Returning `null` from the formula (not `""`) is critical. This collapse turns `Sample + Formula + AppendFields` (3 tools) into `CreateColumnWithGREL + UpDownFiller` (2 steps) inside whatever Prepare you already have — net cost zero recipes. See `ayx/overview.md` § Collapse triggers — the "messy-spreadsheet" row.

---

## Union / Stack

**Alteryx `Union`:** stacks inputs, matching columns by name (default) or position. Missing columns → null.

```xml
<Configuration>
  <Mode>ByName|ByPosition|Manual</Mode>
</Configuration>
```

**Dataiku:** Stack recipe.

```bash
dku recipe create-stack st -P PROJ \
    -i a -i b -i c \
    --output-ds stacked
```

Modes:
- `Union Fields by Name` → Stack with `--mode UNION` (default; union schema, missing → null).
- `Union Fields by Position` → DSS Stack maps by column name, not position. If the Alteryx workflow depends on position, pre-rename columns upstream to the intended names, then stack with `--mode UNION`.

**Caveats:** if two inputs disagree on a column's type (e.g. `int` vs `string`), Stack may upcast to `string`. Rename/cast upstream to avoid surprises.

---

## Summarize

**Alteryx:** group-by + aggregations, explicit.

```xml
<Configuration>
  <SummarizeFields>
    <SummarizeField field="Region" action="GroupBy" rename="Region"/>
    <SummarizeField field="Sales" action="Sum" rename="Total Sales"/>
    <SummarizeField field="Orders" action="CountDistinct" rename="Unique Orders"/>
  </SummarizeFields>
</Configuration>
```

**Dataiku:** Group recipe, `--no-global-count` (Alteryx doesn't emit an unrequested count).

```bash
dku recipe create-group grp -P PROJ -i in --output-ds agg \
    --group-by Region \
    --agg 'Sales:sum,Orders:count_distinct' \
    --no-global-count
```

### Alteryx action → DSS aggregation

| Alteryx | DSS |
|---|---|
| `Sum` | `sum` |
| `Count` | `count` |
| `CountDistinct` | `count_distinct` |
| `CountNonNull` | `count` (on a non-null column) |
| `Min` / `Max` | `min` / `max` |
| `Avg` | `avg` |
| `Median` | `median` |
| `First` / `Last` | `first` / `last` |
| `Concat` / `ConcatDistinct` | `concat` — careful on SQL connections (LISTAGG size cap, see § Caveats below and `dku-cli/references/sql-engines.md`) |
| `StdDev` / `Variance` | `stddev` / `variance` |
| `Percentile` | `percentile` (configure `percentile_value`) |
| `SumNo0` / `AvgNo0` / `MinNo0` / `MaxNo0` / `CountNo0` | **No direct DSS aggregation** — the `*No0` variants in Alteryx ignore zero values (in addition to nulls), which DSS aggregations don't. Lift the zero-exclusion to a `--computed-col` on the same Group recipe, then aggregate the computed column. Pattern: `--computed-col 'col_no0=if(val("col")==0\|\|isBlank(val("col")), null, val("col")):double' --agg col_no0:avg`. The `if … then null else col` construct converts zeros to nulls, then `avg` (which already ignores nulls) gives Alteryx-equivalent semantics. Tested on Challenge_030 (fantasy-baseball Avg_Age and Avg_Pitcher Rank by team): 1 Group recipe, exact match against expected. **GREL `==` not `=` for equality** — single `=` is assignment and the CLI errors `Unexpected '='. Did you mean '=='?` (good) but the underlying job log shows a misleading `EOFException: Unexpected end of ZLIB input stream` (bad — investigate later). See `ayx/semantics.md` § Aggregation null-handling for why this divergence exists. |

**Caveats:**
- Group recipe auto-names outputs `{col}_{func}` (`Sales_sum`). Use `--rename SRC:DST` to fix names inline (the Group recipe's `outputColumnNameOverrides` IS honored — unlike the Pivot recipe's, see `dku-cli/references/common-gotchas.md`). Or add a `ColumnRenamer` in a downstream Prepare to restore Alteryx aliases.
- `Concat` on Snowflake → LISTAGG, capped per-group. For large text, aggregate in a Python recipe.

### Sample (Mode=First, N=1) → TopN, not Sort+Sample

Alteryx's `Sample` tool with `Mode=First` and `N=1` (no `GroupFields`) takes the first row of the input — typically used after a `Sort` to grab the row with the min/max value. **Migrate as a single TopN recipe**, not Sort + Sample:

```bash
# Alteryx: Group → Sort by avg_age asc → Sample(First, N=1)  (3 tools)
# DSS:    Group → TopN(--n 1 --sort-col 'avg_age:asc')        (2 recipes — TopN sorts internally)

dku recipe create-topn youngest -P PROJ -i agg --output-ds youngest --n 1 --sort-col 'avg_age:asc'
```

Alteryx's `Sample` with `Mode=First, N=K` collapses to `--n K` on TopN. With `GroupFields` set, pass `--partition-key`. The Sort recipe is fully replaced — TopN is sort + limit in one pass.

---

## CrossTab

**Alteryx:** pivot wide. Group rows by `GroupFields`, columns from `HeaderField`, values from `DataField` with `Action` aggregation.

```xml
<Configuration>
  <GroupFields><Field field="Region"/></GroupFields>
  <HeaderField>Category</HeaderField>
  <DataField>Sales</DataField>
  <Methods><Method method="Sum"/></Methods>
</Configuration>
```

**Dataiku:** Pivot recipe.

```bash
dku recipe create-pivot pv -P PROJ -i in --output-ds wide \
    -r Region -c Category -v Sales --agg-type SUM --no-global-count
```

**Caveats:**
- Output columns are `<header_value>_<agg>`. If Alteryx used "Concatenate" for text aggregation, use `concat` agg but mind SQL LISTAGG limits.
- **Modality scan is UI-only.** A fresh `create-pivot` recipe builds and errors `RecipeSchemaComputer$DontWantToCompute: Modality lists stored in output schema are not up-to-date`. Setting `pivots[0].explicitValues = [["v1"], ["v2"], …]` via `set-settings` updates the recipe payload but DOES NOT populate the output dataset's modality cache, so the build still fails. There is no `dku` command that triggers the scan. **Workaround: restructure to avoid the pivot.** If you need a wide table with one column per modality for downstream joins, compute the per-modality aggregate inside each upstream branch (Prepare with `add-formula` per modality) and skip the pivot altogether. See `ayx/overview.md` § Collapse triggers — the `Summarize → CrossTab` row.

> **The job-not-the-tool reflex for CrossTab.** Many CrossTabs are mid-flow shape changes that downstream consumers don't actually need. Before reaching for Pivot, ask: *what does the next recipe do with the wide form?* If the answer is "join then aggregate again", you can usually fold the aggregation into the upstream Group recipe's `computedColumns` (per `dku-cli` SKILL.md rule 12) or just compute the per-category values per-component before any reshape.

---

## Transpose

**Alteryx:** pivot long. Key columns stay; data columns become (Name, Value) pairs.

```xml
<Configuration>
  <KeyFields><Field field="id"/></KeyFields>
  <DataFields><Field field="q1"/><Field field="q2"/></DataFields>
</Configuration>
```

**Dataiku:** Prepare recipe with `MultiColumnFold` (stock DSS — no plugin). Use the `add-fold` shortcut:

```bash
dku recipe add-fold prep1 --columns "q1,q2" --key-column Name --value-column Value -P PROJ
```

(`add-fold` emits `MultiColumnFold` with `foldRemoveFoldedColumns: true`. `MultiColumnByPrefixFold` is the regex-pattern variant — `add-fold --pattern '.*-25'`.)

> **`MultiColumnFold` SILENTLY DROPS rows where the value is null.** A row that has a null in one of the folded columns produces N-1 long rows instead of N. There is no warning. Two ways to handle this:
>
> 1. **For aggregation downstream** (most common — fold so you can `Group` over the long form): pre-impute with `FillEmptyWithValue` (one step per folded column) BEFORE the fold. Imputed rows survive and the Group result is unaffected by the imputation choice.
> 2. **For round-tripping back to long form preserving null status** (rare — e.g., the original wide values need to appear as `Value=""` in the final long output): use a sentinel-string approach. Cast each metric to a string column with `if(isBlank(strval("col")), "@@NULL@@", concat("", numval("col")))`, fold the sentinel-strings, then `add-find-replace` with `--matching FULL_STRING` to swap `@@NULL@@` back to empty. Six metric columns → ~10 step Prepare. Single Prepare; still visual.
>
> The default DSS auto-output behavior is option 1; only reach for option 2 when the null status itself is part of the contract.

> **DO NOT use `FoldColumnsByName`** — that's a plugin processor (different param names: `keyColumn`/`valueColumn`) and DSS errors with `UnavailableTypeException` on instances where the plugin isn't installed. Older `dku` versions emitted the plugin variant from `add-fold`; if you see that error, **reinstall the global CLI** (`uv tool install --from . dku-cli --force --reinstall`) before assuming you need a Python fallback. `pd.melt` is genuinely never needed for this — even on the rarest DSS instance.

> **The job-not-the-tool reflex for Transpose.** Most Alteryx Transposes exist to feed a downstream `Summarize` (group + agg) over the long form. In DSS the cleaner shape is to compute the aggregate **per-input, before any reshape**: one `add-formula` step per output key inside each upstream Prepare, and the long form is never materialized. Saves the unpivot, the lookup join, and the per-key Group all in one shot. See `ayx/overview.md` § Collapse triggers — the `Union → Transpose → Summarize` row.

> **Pivot/Transpose round-trip in Alteryx is just a long-form computation in disguise.** The pattern `Transpose → MultiRowFormula → CrossTab → JoinMultiple → AlteryxSelect → Transpose` (long → window → wide → join → wide → long) reduces in DSS to: compute everything in long form, then emit the final long output via Stack-of-projections. The CrossTab/JoinMultiple round-trip exists in Alteryx because MultiRowFormula operates on a single column and the original metric values must be re-attached to the moving averages — DSS Window can carry both Value and lagged columns through the long form, so the round-trip is wasted shape change. See `ayx/overview.md` § Collapse triggers — the `Transpose → MultiRowFormula → CrossTab → Transpose` row.

---

## Component-stat workflows (Transpose + Summarize + CrossTab macro chains)

A common Alteryx pattern: per-component datasets carrying wide stat columns (one column per category), chained through `Transpose` (wide→long) → `Summarize` (group + agg per category) → `CrossTab` (long→wide back to one column per category) → join across components → score. Often wrapped in a standard or batch `.yxmc` macro to repeat per category.

**The DSS rewrite skips both reshapes entirely.** When the goal is "for each component, produce one column per category, then combine across components", do the per-category arithmetic *inside each upstream Prepare* with `add-formula` (one formula per category) — the long form is never materialized.

Worked example (Mario Kart-style 4-component combo optimizer, validated migration `MARIOKART_FRESH`):

```bash
# Per component (drivers / bodies / tires / gliders): one Prepare with N add-formula
# steps, one per category to score on. No Transpose, no Summarize, no CrossTab.
for c in DRIVERS BODIES TIRES GLIDERS; do
  dku recipe create-prepare prep_${c} -P PROJ -i ${c}_RAW --output-ds ${c}_SCORED
  dku recipe add-formula prep_${c} -P PROJ --column speed_score \
      --expr 'numval("Anti-Gravity Speed") * 0.5 + numval("Ground Speed") * 0.5'
  dku recipe add-formula prep_${c} -P PROJ --column handling_score \
      --expr 'numval("Handling") * 0.7 + numval("Mini-Turbo") * 0.3'
  dku recipe apply-schema prep_${c} -P PROJ
done

# One CROSS join wires all four scored components into a single combo row
# (`-i` is repeatable; create-join handles N>2 in a single recipe).
dku recipe create-join join_combos -P PROJ \
    -i DRIVERS_SCORED -i BODIES_SCORED -i TIRES_SCORED -i GLIDERS_SCORED \
    --output-ds COMBOS --join-type CROSS

# Final score + sort: another Prepare with the weighted-sum formula, then Sort.
dku recipe create-prepare score_combos -P PROJ -i COMBOS --output-ds COMBOS_SCORED
dku recipe add-formula score_combos -P PROJ --column total_score \
    --expr 'speed_score * 0.4 + handling_score * 0.6'
dku recipe create-sort sort_combos -P PROJ -i COMBOS_SCORED \
    --output-ds COMBOS_RANKED --sort-col total_score:desc
```

**Why this collapses cleanly:**
- The Transpose/Summarize/CrossTab triplet only existed because Alteryx-style macros encourage looping over a category list. DSS expresses "per-category arithmetic" as N formulas in one Prepare — explicit, readable, and stays on whatever engine the input uses (no engine break for the long form).
- A `BatchMacro` repeating the chain per component becomes 4 sibling Prepares (one per component), all configurable via the same loop.
- The `CROSS` join is one recipe, not N-1 chained joins, because `create-join -i` is repeatable.

If you find yourself writing `Transpose → Summarize → CrossTab` (or its macro equivalent) in a draft DSS plan, stop and audit: usually the per-category formulas already live in the upstream component dataset, and the entire reshape was just a Alteryx-flavored loop.

---

## MultiRowFormula

**Alteryx:** per-row formula with access to prior/next rows (`[Row-1:Col]`, `[Row+1:Col]`) inside a `GroupByFields` partition, ordered by input row order.

```xml
<Configuration>
  <UpdateField value="False"/>
  <CreateField_Name>RunTotal</CreateField_Name>
  <CreateField_Type>Double</CreateField_Type>
  <OtherRows>Nearest</OtherRows>           <!-- ← boundary semantics; matters! -->
  <GroupByFields><Field field="Region"/></GroupByFields>
  <Expression>[Row-1:RunTotal] + [Sales]</Expression>
  <NumRows value="1"/>
</Configuration>
```

**`<OtherRows>` (boundary semantics) — read this BEFORE picking a translation.** Alteryx's `OtherRows` controls what `[Row-N:Col]` returns when offset N runs off the start (or end) of the partition. Three values, three translations:

| `<OtherRows>` | Alteryx behavior at boundary | DSS visual translation |
|---|---|---|
| `NULL` (default) | Off-partition refs return null | DSS Window's natural `Lag(col, k)` returns null at boundary too — semantics match. Just use Window directly. |
| `Empty` | Off-partition refs return empty string ("") | Same as NULL for numeric columns. Same Window translation. |
| `Nearest` | Off-partition refs return the **first/last value of the partition** (the "edge" value) | DSS Window's `Lag(col, k)` returns null at boundary — does NOT match. **Add a `FirstValue(col)` aggregation over the partition AND a Prepare formula `if(isBlank(lag_k), first_v, lag_k)` for each offset before computing the average/sum.** Example below. |

**Why `Nearest` is the trap:** Alteryx defaults to `NULL`, but `Nearest` is common in moving-average workflows because it makes the leading-edge averages well-defined (instead of producing nulls for the first N-1 rows). DSS Window's natural partial-window behavior at the boundary computes the average over the AVAILABLE rows (`avg(V[1])` for row 1, `avg(V[1], V[2])` for row 2, …), which is yet a third semantic. So a 3-row moving average at row 2 with input `(218, 200, …)`:

| Alteryx `Nearest` | DSS partial-window Window | DSS Window + lag-coalesce |
|---|---|---|
| `(218 + 218 + 200)/3 = 212` | `(218 + 200)/2 = 209` | `(218 + 218 + 200)/3 = 212` ✓ |

If you use a vanilla `create-window --compute 'avg:Value:r3mo' --window-frame -2,0` you'll get the partial-window answer (209), not Alteryx's (212). That's what to watch for.

**Dataiku (ordered by simplicity):**

1. **Simple prior/next-row reference in a Formula** (`OtherRows=NULL/Empty`) → Prepare recipe, Formula processor with `val("col", default, offset)`, `strval(...)`, or `numval(...)`. The `offset` argument is negative for prior rows, positive for next rows. Requires enabling **"Preserve ordering"** on the input dataset (or an explicit upstream Sort). Example — compounding inflation:
   ```
   val("Value", 50, 1) * ( 1 + (val("Inflation Rate", 0, 1) / 100) )
   ```
   This is the direct equivalent of `[Row-1:Value]` in Alteryx. It's a Formula Processor step — no separate Window recipe.

2. **"Fill empty with previous/next value"** → Prepare recipe, **up/down filler processor**. Dedicated processor for the most common Alteryx MultiRowFormula pattern.

   **For Window-based forward-fill** (when the data is already in a Window pipeline and you'd rather not branch out to a Prepare): DSS Window's `last(col)` aggregation does **NOT** do cumulative-up-to-current-row by default — it returns the current row's own value (frame is "current row only" even with `enableLimits: false`). Two workarounds:
   - **Monotonic data only:** use `--compute 'max:col:'` (cumulative max). Empty strings sort lexicographically before `'07'`, `'08'`, …, so `max` skips empty cells and the cumulative max picks up the latest non-empty value seen. Works for Year (`'07' < '08'`) but FAILS for non-monotonic data (e.g., `'08' → '09' → '08'` would lock at `'09'`).
   - **General-purpose forward-fill:** assign a `group_id` via cumulative `sum(is_set)` in one Window, then `--partition-key group_id --compute 'max:col:'` in a second Window (within each group only one row has the value set, so max = that value). Two recipes, but correct for any data shape. See `dku-cli/references/recipe-survey.md` § Window aggregation framing.

3. **`[Row+1:Col]` lookahead** (next-row reference inside MultiRowFormula) → Window recipe with `--compute 'lead:col:'`. Default offset is 1; for further-ahead, use `--lead-offsets 'col:1,2,3'` (multi-offset in one Window). Example (date disambiguation where the current-row month letter is ambiguous and the next-row letter resolves it):
   ```bash
   dku recipe create-window lookahead -i in --output-ds out -P PROJ \
       --order-key row_idx \
       --compute 'lead:raw_month:' \
       --rename 'raw_month_lead:next_month'
   # Then a Prepare with: if(month=='J' && next_month=='F', 'Jan', if(month=='J' && next_month=='J', 'Jun', …))
   ```
   The `--compute 'TYPE:COL:OUTPUT'` third segment is silently ignored by DSS — always rename via `--rename SRC:DST` instead.

   **Trap when folding the post-MRF Filter into `--post-filter`:** the canonical "MRF detects flag row, Filter keeps flagged" Alteryx pattern (`MultiRowFormula(Flag = if [Row+1:col] matches /^[(]/) → Filter(Flag IsTrue)`) folds to ONE Window with `--compute 'lead:col:'` + `--post-filter`. But `--post-filter` runs on the pre-rename schema — `--post-filter 'startsWith(strval("next_month"), "(")'` after `--rename 'raw_month_lead:next_month'` filters on a column that doesn't exist yet and silently emits ZERO rows. Reference the pre-rename name in the filter: `--post-filter 'startsWith(strval("raw_month_lead"), "(")'`. The output dataset still has the renamed `next_month` column. See `dku-cli/references/common-gotchas.md` § Window `--rename` ordering.

3. **Running total / lag with aggregation / partition-aware (`OtherRows=NULL`)** → Window recipe. Partition by group, order by an explicit column (add one with a Window `RowNumber` aggregation upstream if absent — Prepare has no `AddId` processor; use a Window with no partition + `RowNumber` instead).
   ```bash
   dku recipe create-window win -P PROJ -i in --output-ds windowed \
       --partition-key Region --order-key rec_id \
       --compute 'sum:Sales:'   # produces 'Sales_sum'
   ```

4. **Moving average with `OtherRows=Nearest` (boundary fill with edge value)** → Window with explicit lag aggregations + `FirstValue` aggregation, then a Prepare that null-coalesces lags against the FirstValue, then computes the average. The CLI's `--compute lag:col:` only sets the lag flag; multi-offset lags require a `set-settings` patch. Recipe (3-row MA, partition `Region`, order `rec_id`):

   ```bash
   # 1. Create window with lag + first
   dku recipe create-window w3 -P PROJ -i in --output-ds w3_out \
       --partition-key Region --order-key rec_id \
       --compute 'lag:Value:' --compute 'first:Value:'

   # 2. Patch the payload to enable lag offsets 1 AND 2 (CLI exposes only one default offset).
   dku recipe get-settings w3 -P PROJ -o json > /tmp/w3.json
   # In /tmp/w3.json, find payload.values[] entry where column == "Value":
   #   set lag=true, lagValues="1,2", first=true
   dku recipe set-settings w3 -P PROJ -s @/tmp/w3.json
   dku recipe apply-schema w3 -P PROJ && dku recipe run w3 -P PROJ --wait
   # → adds columns Value_lag1, Value_lag2, Value_first

   # 3. Prepare with null-coalesce + average
   dku recipe create-prepare ma_calc -P PROJ -i w3_out --output-ds ma
   dku recipe add-formula ma_calc -P PROJ --column r3mo \
       --expr '(if(isBlank(strval("Value_lag2")), numval("Value_first"), numval("Value_lag2")) + if(isBlank(strval("Value_lag1")), numval("Value_first"), numval("Value_lag1")) + numval("Value")) / 3.0'
   dku recipe add-delete-columns ma_calc -P PROJ --columns 'Value_lag1,Value_lag2,Value_first'
   dku recipe apply-schema ma_calc -P PROJ && dku recipe run ma_calc -P PROJ --wait
   ```

   Generalize: for window size W, request `lagValues="1,2,…,W-1"` and a 6+ formula null-coalesces. **Two Window recipes are needed when the same source has TWO moving averages with DIFFERENT partition keys** (e.g., `r3mo` partitioned by `(Region, Metric)` AND `r6mo` partitioned by `Metric` only) — partitioning is per-recipe in DSS Window. Chain them: rename the first window's output columns (Window's output names are `<col>_lag<k>` / `<col>_first` and DSS does NOT support custom names), then run the second window so its default names don't collide.

5. **Custom multi-row logic** → Window with a lag column + a trailing Prepare that references the lag column. **Reach for Python only when the recurrence references an as-yet-computed prior-row value of the SAME computed column** (rare).

**Caveats:**
- DSS Window's `Lag(col, k)` returns null at the boundary. To match Alteryx `<OtherRows>Nearest`, ALWAYS add a `FirstValue(col)` aggregation over the partition and null-coalesce the lags against it in a Prepare step (per option 4).
- `--compute lag:col:` accepts ONE default offset (1). Multi-offset windows need a `set-settings` patch on `payload.values[].lagValues` (comma-separated string like `"1,2,3,4,5"`).
- DSS Window output column names are NOT customizable — they default to `<src_col>_lag<k>` / `<src_col>_first`. Two Window recipes on the same source column will produce colliding names; insert a Prepare `add-rename` between them.
- For non-trivial recurrences (`Row-1` of the same output column), Python is the escape hatch.
- Window engine matters — SQL, DSS, and Spark differ in how they emit row numbers for ties; always add an explicit Sort upstream if determinism matters.

---

## RunningTotal

**Alteryx:** cumulative sum per partition, in input row order. Subset case of MultiRowFormula.

```xml
<Configuration>
  <GroupByFields><Field field="Region"/></GroupByFields>
  <RunningTotalFields><Field field="Sales"/></RunningTotalFields>
</Configuration>
```

**Dataiku:** Window recipe with PARTITION BY + ORDER BY + `sum`. With an `--order-key` set, DSS Window's default frame is "from start of partition to current row" — i.e. cumulative sum, matching SQL standard. No `--frame-preceding` flag needed.

```bash
# Alteryx RunningTotal needs an explicit row-order column. If the upstream pipeline
# already has one (e.g. Priority, date, sort key), pass it here. Otherwise add a
# RecordID upstream first.
dku recipe create-window runtot -P PROJ -i in --output-ds out \
    --partition-key Region --order-key sort_key \
    --compute 'sum:Sales:'   # produces 'Sales_sum' (column name not configurable)
```

**Caveats:**
- DSS Window output column is hardcoded to `<src_col>_sum` (NOT customizable at create time). If the downstream step references the Alteryx name like `RunTot_Sales`, either chain a Prepare `add-rename`, or just reference `Sales_sum` directly — usually simpler.
- Alteryx `RunningTotal` orders by **input row order** (which usually = the upstream Sort tool). DSS Window must have an explicit `--order-key`. If the input has no natural order column, either add a `RecordID`-equivalent upstream (`create-window … --compute 'rowNumber::rn'` with no partition) or fold the Sort tool's keys into the cumulative Window's `--order-key`.
- **Collapse hint:** when an Alteryx `RunningTotal` is followed by a `MultiRowFormula` that references `[Row-1:RunTot_X]` and `NumRows=1` (the typical "greedy fill" / "allocate by priority" pattern), do NOT add a separate Lag column — algebra: `[Row-1:RunTot_X] == RunTot_X - X`. The current cumulative minus the current row's value is exactly the previous cumulative. One Window + one `add-formula` instead of Window + Lag + Prepare. See `ayx/overview.md` § Collapse triggers — the `Sort → RunningTotal → MultiRowFormula` row.

---

## RecordID

**Alteryx:** adds a sequential integer.

```xml
<Configuration>
  <FieldName>RecordID</FieldName>
  <StartValue>1</StartValue>
  <FieldType>Int32</FieldType>
</Configuration>
```

**Dataiku:** Prepare `AddId` step (global row id, starts at 0; adjust with a `CreateColumnWithGREL: id + 1`).

```bash
--step '{"type":"AddId","params":{"outColumn":"RecordID"}}'
--step '{"type":"CreateColumnWithGREL","params":{"expression":"RecordID + 1","column":"RecordID"}}'
```

**Caveats:** if the data is partitioned across an engine (SQL / Spark), `AddId` is non-deterministic ordering unless an explicit Sort precedes it.

---

## TextToColumns

**Alteryx:** split one column into N new columns on a delimiter, or into N rows.

```xml
<Configuration>
  <Field>Range</Field>
  <NumFields value="2"/>
  <RootName>Range</RootName>
  <Delimeters value="-"/>
  <ErrorHandling>Last|Merge|Ignore</ErrorHandling>
  <Flags value="0"/>   <!-- 0 = split to columns; 1 = split to rows -->
</Configuration>
```

**Dataiku:**

Split to columns → Prepare `ColumnSplitter`:

```json
{
  "type": "ColumnSplitter",
  "params": {
    "inCol": "Range",
    "separator": "-",
    "outColPrefix": "Range",
    "target": "COLUMNS",
    "keepEmptyChunks": false,
    "limitOutput": false,
    "limit": 0
  }
}
```

Split to rows → Prepare `SplitFold` (split a column on a delimiter and emit one row per chunk).

**Caveats:**
- Alteryx `ErrorHandling=Last` puts the remainder in the last column if the delimiter appears more than `NumFields-1` times. **`ColumnSplitter` with `limitOutput: true, limit: N, startFrom: "beginning"` silently DROPS extras** (verified on `a,b,c,d,e` with `limit: 3` → `a, b, c` — `d,e` lost, no warning). Two fixes for "merge tail" parity:
  - **Regex extractor** (preferred for fixed N): one `ExtractRegex` step with `^([^,]*),([^,]*),(.*)$` + `targetColumns: ["c1","c2","c3"]` puts everything after the (N−1)-th delimiter into the last group.
  - **No-limit + concat tail**: `ColumnSplitter` with `limitOutput: false`, then a `CreateColumnWithGREL` that re-joins chunks `N-1..` with the original separator. Fragile — only use when N varies row-to-row.
- When `limitOutput: true`, `startFrom` is required (`"beginning"` or `"end"`, lowercase). Omitting it makes `apply-schema` reject the step.
- `ColumnSplitter` infers numeric types on its output columns when every row is numeric (e.g. `2000-2019` → `part0`,`part1` typed as `bigint`). You get the cast for free compared to a `CreateColumnWithGREL` + `toNumber(split(…)[i])` pair.

---

## RegEx

**Alteryx:** four modes — `Replace`, `Tokenize`, `Parse` (named capture groups → columns), `Match`.

```xml
<Configuration>
  <Method>Parse|Replace|Tokenize|Match</Method>
  <Field>Text</Field>
  <Pattern>(\d{3})-(\d{4})</Pattern>
  <Replace>$1$2</Replace>
  <CaseInsensitive value="False"/>
</Configuration>
```

**Dataiku Prepare steps:**
- `Parse` → `RegexpExtractor` (`column`, `pattern`, `extractAllOccurrences`). Output cols are named after the capture-group index — bare `1`, `2`, etc. — NOT `<col>_1`. Always follow with a `ColumnRenamer` step (`renamings:[{from:"1",to:"my_name"}]`); without it, downstream steps reference the cryptic numeric names. ColumnRenamer with a non-existent `from` is a silent no-op, so verify the index name with `dku dataset schema OUTPUT` after `apply-schema`.
- `Replace` → `FindReplace` with `matchingMode: REGEX`.
- `Tokenize` → `ColumnSplitter` with a regex separator.
- `Match` → `FilterOnCustomFormula` with `matches(s, /pat/)`.

**ParseComplex semantics — match Alteryx's "first decimal in segment" behavior.** Alteryx's `Method=ParseComplex` with a pattern like `(\d+\.?\d*)` returns the FIRST regex match anywhere in the field — there is no anchor. When migrating a `TextToColumns(split-to-rows) → RegEx(ParseComplex (\d+\.?\d*))` chain to DSS `SplitFold + RegexpExtractor`, do NOT add a closing-bracket / context anchor (e.g. `^([\d.]+)\]`) "to be safe" — it will silently drop rows where the value isn't followed by that context (truncated data, alternate group layouts where the bracket is positioned differently). Use `^([\d.]+)` (leading-decimal-only) for parity with Alteryx ParseComplex. Discovered in Challenge_022: input had two layouts — `[atm1.1/atm2.X]/atc1...` and `[atm1.1/atm2.X/atc1...]` — and rows truncated mid-string by a `Formula(size=N)` upstream had the trailing `]` cut off. The `]`-anchored regex matched neither, producing missing groups in the Group output (367 → 366 rows).

### XML-in-cell with N attributes per row (canonical "raw XML field" pattern)

**Pattern:** A column holds a multi-line XML document per row (e.g. `customer_OuterXML` containing `<customer><reference>X</reference><bill_to>...<contact><first_name>...</first_name>...</contact><address><city>...</city>...</address></bill_to><ship_to>...</ship_to></customer>`), and the goal is to flatten N nested attributes into N output columns of a wide table — one row per input row, no row multiplication.

**Alteryx solution (canonical 17-tool decomposition):** `RecordID + TextToColumns(split-to-rows on "<") + RegEx(ParseComplex "(.*?)>(.*)" → tag, value) + Filter(\w+) + MultiRowFormula(BillingShipping context = forward-fill on tag matching "bill"/"ship") + CrossTab(GroupBy=(RecordID,BS), Header=tag, Data=value, Concat) + AlteryxSelect(rename) + Filter(BS=="Bill") + DynamicRename(Billing_*) + Filter(BS=="Ship") + DynamicRename(Shipping_*) + Join(Bill,Ship on RecordID) + Filter(tag=="reference") on the original branch + Join(parent,wide on RecordID) + 2× Cleanse macro`. Decomposes into long form, pivots back, then self-joins.

**DSS collapse: ONE Prepare recipe with N `add-formula` regex-extract steps.** Skip the long-form decomposition entirely — extract each leaf value directly with one GREL `match()` call:

```bash
# Per-attribute extract (one add-formula per output column):
dku recipe add-formula prep_xml --column "Billing_first_name" \
  --expr 'match(strval("customer_OuterXML"), /(?s).*?<bill_to>.*?<first_name>(.*?)<\/first_name>.*/)[0]' -P PROJ
dku recipe add-formula prep_xml --column "Shipping_State" \
  --expr 'match(strval("customer_OuterXML"), /(?s).*?<ship_to>.*?<province>(.*?)<\/province>.*/)[0]' -P PROJ
# ... one formula per Billing_* and Shipping_* leaf ...
# Then: ColumnsSelector to drop customer_OuterXML.
```

**The pattern shape that makes this work**:
- The regex anchors on the **section-wrapper tag** (`<bill_to>`, `<ship_to>`, etc.) before the **leaf tag** (`<first_name>`, etc.). Without the section anchor, the `.*?` first-occurrence match would always land on the Billing copy of the leaf, even when extracting Shipping.
- `(?s)` inline flag enables DOTALL — required because the XML payload has newlines and `.*?` would not cross them otherwise.
- Surrounding `.*?` and `.*` make the whole expression match the entire input (GREL `match()` requires whole-string match — see `dataiku/references/formulas.md` § Regex). The captured group is at index `[0]`.
- Tags with attributes (`<line sequence="1">525 pemberton ave</line>`) need `<line[^>]*>(.*?)</line>` instead of `<line>...</line>`.

**Mapping ratio: 17:1.** Verified on Challenge_037 (10 input rows × 27 output cols, exact value match with all 21 nested attributes extracted in one Prepare). The Alteryx solution's TextToColumns+RegEx+MultiRowFormula+CrossTab+self-join chain exists because Alteryx Formula tools can't run regex against the *whole* XML cell — they're field-by-field. DSS GREL `match()` against `strval("col")` is a one-shot regex against the whole cell, eliminating the need to decompose-then-recompose.

**Falls back to a Python recipe ONLY when:** (a) the XML has variable-cardinality lists (e.g. multiple `<line>` entries per address with no fixed count) — regex first-match drops the rest; or (b) namespaces / attribute-driven branching require true XPath. For fixed-schema XML-in-cell (the typical e-commerce export shape), the visual approach is enough.

---

## DynamicRename

**Alteryx:** renames columns based on a pattern, an expression, or a second input (rename map).

**Dataiku (ordered by complexity):**

1. **`RenameMode=FirstRow` with known header content (most common Grand-Prix-style pattern)** → static `add-rename --mappings`. The Alteryx flow promotes row N's values as column names; in DSS, you read the source file once during inventory, copy the actual header values, and bake them into a static rename map. Drop the noise rows (header marker, decorative `***`, "Data Downloaded" stamps) with `add-filter-rows`, drop the header row itself with `add-filter-rows --formula 'strval("Field_1") != "Surf Site"'` (using the known header-row sentinel), then `add-rename --mappings '{"Field_1":"Surf Site","Field_2":"Swell Direction",…}'`. ONE Prepare collapses Filter+DynamicRename — no plugin, no Python. Tested on Challenge_031: 5 noise rows + header → 18 clean rows with proper column names, all in one Prepare recipe. Only fall back to (2) below when the header content is variable run-to-run.
2. **Mass renamings with a regex** (e.g. strip prefix / case conversion across many cols) → Prepare `RenameColumns` processor with the "mass renamings" option. Supports add/remove prefix/suffix, case conversion, and regex replace across many columns in one step.
3. **Variable-position header row** → either set on upload (formatting tab: skip N rows, parse next as headers), or — if the header position is variable — a Prepare recipe `Use values of row as column names` (check availability; this processor has been deprecated in some versions).
4. **Rename from a second dataset (dynamic rename map)** → Prepare's `fold multiple columns by pattern` + find/replace regex + pivot back (roundabout, unstable schema). Generally prefer a Python recipe:
   ```python
   rename_map = dict(zip(right["old_name"], right["new_name"]))
   out = left.rename(columns=rename_map)
   ```
5. **Conditional per-column rename (`[_CurrentField_]` expression)** → Python recipe — no visual equivalent for per-column expression evaluation.

**Caveats:** dynamic renaming destabilizes downstream schema. If the output column set changes run-to-run, downstream Join/Prepare schemas will silently mismatch. Consider freezing the schema with a `set-schema` + explicit rename map where feasible.

---

## DateTime

### DSS date types

Recent DSS distinguishes three date types (older DSS had only one, ISO-8601 datetime with timezone):

- **Datetime with tz** — full ISO-8601, e.g. `2025-12-31T23:05:43.123Z`. The long-established DSS default.
- **Datetime no tz** — `yyyy-MM-dd HH:mm:ss(.SSS)?`, no timezone. Good for source systems that report "wall clock" times.
- **Date only** — `yyyy-MM-dd`, no time component. Common for "export to Excel" targets that shouldn't carry a time.

When parsing an Alteryx `Date` column, pick **Date only**; for `DateTime`, pick **Datetime no tz** unless the source is explicitly ISO-8601 with Z/offset. To convert across types, use a Parse date or Format date processor with the target type selected in "Output type". If converting in place (same column), also change the column's type manually.

### Alteryx `DateTime` tool

**Alteryx:** parse string→date or format date→string.

```xml
<Configuration>
  <IsFrom value="False"/>   <!-- "False" / "True" boolean form, OR "String" / "Date" enum form depending on Designer version. False/String = parse string→date; True/Date = format date→string -->
  <InputFieldName>ds</InputFieldName>
  <OutputFieldName>ds_parsed</OutputFieldName>
  <Format>yyyy-MM-dd</Format>
  <Language>English</Language>
</Configuration>
```

**Dataiku Prepare:**
- String → Date: `DateParser` step (params: `appliesTo`, `columns` (LIST), `outCol`, `formats`, `outType`, `lang`, `timezone_id`).
  ```json
  {"type":"DateParser","params":{"appliesTo":"SINGLE_COLUMN","columns":["ds"],"formats":["yyyy-MM-dd"],"lang":"auto","timezone_id":"UTC","outCol":"ds_parsed","outType":{"name":"out","type":"datetimenotz"}}}
  ```
  ⚠ Param is `columns` (array) and requires `appliesTo: "SINGLE_COLUMN"` — the singular `column` shape silently fails. See `dataiku/references/prepare-processors.md` § DateParser.
- Date → String: `DateFormatter` (params: `inCol`, `outCol`, `format`).

**Caveats:**
- Alteryx format tokens match Java (`yyyy-MM-dd`), **not** C `strftime` — so `%Y-%m-%d` strings in Alteryx source are usually found in `DateTimeFormat` function calls inside a Formula tool, not in the DateTime tool itself. See Formula cheatsheet.
- ISO 8601: use `yyyy-MM-dd'T'HH:mm:ss'Z'` (single-quote the `T` and `Z` literals).
- `DateParser` without `outCol` silently nulls all rows — always specify `outCol`.
- Alteryx `DateTime(parse)` tolerates missing seconds (input `MM/dd/yyyy HH:mm` against format `MM/dd/yyyy hh:mm:ss` produces `:00` seconds). DSS `DateParser` is similarly lenient — list a format that matches the *actual* input precision (e.g. `M/d/yyyy H:mm` for unpadded inputs); the output `outType: datetimenotz` carries `:00` seconds automatically when the parse format omits them.

### Manual zero-padding macros (TextToColumns + padleft + concat + DateTime)

Alteryx workflows occasionally normalize date strings by **splitting → padleft each part → reconcatenating → parsing** — a 4-tool macro of the shape:

```
TextToColumns(field=date, delim="\s/:", NumFields=5)   # split MM/DD/YYYY HH:MM into 5 cols
Formula:                                               # padleft each numeric component
  [1] = padleft([1], 2, "0")
  [2] = padleft([2], 2, "0")
  [4] = padleft([4], 2, "0")
  [date] = [1]+"/"+[2]+"/"+[3]+" "+[4]+":"+[5]
AlteryxSelect (drop the 5 split cols)
DateTime(IsFrom=False, format=MM/dd/yyyy hh:mm:ss)     # parse to DateTime_Out
```

**DSS collapse: `DateParser → DateFormatter → DateFormatter` (one Prepare recipe).** The manual padleft dance is unnecessary — DSS `DateFormatter` zero-pads automatically when the format pattern uses `MM/dd/yyyy HH:mm` (vs the source's `M/d/yyyy H:mm`). Output column is just the formatted string.

```bash
# Step 1: parse the un-padded source
dku recipe add-step prep --type DateParser --params '{
  "appliesTo":"SINGLE_COLUMN","columns":["date_time"],
  "formats":["M/d/yyyy H:mm"],"lang":"auto","timezone_id":"UTC",
  "outCol":"_parsed","outType":{"name":"out","type":"datetimenotz"}}' -P PROJ

# Step 2: re-emit zero-padded version (overwrite source col)
dku recipe add-step prep --type DateFormatter --params '{
  "inCol":"_parsed","outCol":"date_time","format":"MM/dd/yyyy HH:mm",
  "lang":"auto","timezone_id":"UTC"}' -P PROJ

# Step 3: emit the ISO datetime variant
dku recipe add-step prep --type DateFormatter --params '{
  "inCol":"_parsed","outCol":"DateTime_Out","format":"yyyy-MM-dd HH:mm:ss",
  "lang":"auto","timezone_id":"UTC"}' -P PROJ

# Step 4: drop the parse intermediate
dku recipe add-step prep --type ColumnsSelector --params '{
  "appliesTo":"SINGLE_COLUMN","columns":["_parsed"],"keep":false}' -P PROJ
```

**4 Alteryx tools → 1 Prepare recipe (4 steps).** Verified Challenge_034. `DateFormatter` overwriting the source column is supported (set `outCol` to the existing column name).

---

## GenerateRows

**Alteryx:** repeats/emits rows based on an init/condition/loop expression.

```xml
<Configuration>
  <CreateField_Name>Area</CreateField_Name>
  <Expression_Init>[Start]</Expression_Init>
  <Expression_Cond>[Area]&lt;=[End]</Expression_Cond>
  <Expression_Loop>[Area] + 1</Expression_Loop>
</Configuration>
```

**Dataiku — pick by shape:**

1. **Range join (integer BETWEEN) on SQL** — the most common "GenerateRows then Join" pattern. Skip the row expansion entirely. SQL recipe:
   ```sql
   SELECT c.*, r.*
   FROM customers c
   JOIN ranges r ON c.postal_area BETWEEN r.start AND r.end
   ```
   Or Join recipe with a `CUSTOM` condition if the connection supports it.

2. **Prepare-only expansion (visual, filesystem or SQL)** — `ColumnSplitter` → `CreateColumnWithGREL` (`forRange`) → `ArrayFold`. This is the pattern the skill has always advocated; confirmed working on stock DSS:
   ```json
   {"type":"ColumnSplitter","params":{"inCol":"Range","separator":"-","outColPrefix":"part","target":"COLUMNS","keepEmptyChunks":false,"limitOutput":false,"limit":0}}
   {"type":"CreateColumnWithGREL","params":{"expression":"forRange(-1, part1 - part0, 1, v, part0 + v + 1)","column":"Area"}}
   {"type":"ArrayFold","params":{"column":"Area"}}
   ```
   Downstream: equi-join `customers.Postal Area = ranges_expanded.Area`, then group. `ColumnSplitter` auto-types `part0`/`part1` as `bigint` when every value is numeric, so no `toNumber`/`set-schema` is needed.

   For date spines, swap the middle step for `forRange(-1, diff(end,start), 1, v, v+1)` and add a trailing `CreateColumnWithGREL` with `computeDate(start, offset, "day")` to compute the date.

   `ArrayUnfold` is the sibling processor — it expands an array into columns, not rows. Pick `ArrayFold` for GenerateRows-style row expansion.

3. **No-Prepare fallback (pure visual, every recipe is a shortcut)** — "Cross-join → Filter → Group". Useful when the target team has no Prepare users or when the expanded row count would explode. Four recipes:
   1. Prepare: compute numeric `Start`, `End` from the range string. `toNumber(split(Range,"-")[0])` / `toNumber(split(Range,"-")[1])` via `add-formula` — `toNumber()` makes the output correctly typed as `bigint`; `numval(expr, default)` does NOT work here because `numval` takes a quoted column name, not an expression.
   2. Join with `-j CROSS`: customers × ranges_prep.
   3. `create-filter` on the cross product. Reference space-containing columns with `numval("Postal Area")` / `strval(...)` — backticked `` `Postal Area` `` is rejected by the GREL filter parser (`ParsingException at offset 0`).
   4. `create-group --no-global-count` with `--agg 'Customer ID:count'`.

4. **Dynamic loop (arbitrary init/cond/loop)** → Python recipe, only when neither option 1/2/3 applies.

5. **Cartesian product across two datasets** → Join recipe with `type: CROSS`, or SQL `CROSS JOIN`.

**Caveats:** row expansion can blow up. Check `count(ranges) * max(End - Start)` before running option 2, or `count(customers) * count(ranges)` for option 3 — pair with a SQL engine for large tables.

---

## JSONParse

**Alteryx:** parses a JSON column into `JSON_Name` + `JSON_ValueString` tall records, one row per leaf.

**Dataiku Prepare:**
- Flatten-one-level JSON → `UnfoldObject` step on the JSON column.
- Tall (one row per leaf) → `UnfoldObject` then a Python recipe to melt, or `JSON to columns` recipe (if plugin installed).
- Deep/irregular JSON → Python recipe with `json.loads` + `pandas.json_normalize`.

---

## Download

**Alteryx:** issues HTTP(S) requests per row; emits a response column.

**Dataiku:** Python recipe. No visual recipe for HTTP. Use `requests`.

```python
import pandas as pd, requests
df = dataiku.Dataset("in").get_dataframe()
df["response"] = df["url"].apply(lambda u: requests.get(u, timeout=30).text)
dataiku.Dataset("out").write_with_schema(df)
```

**Caveats:** for high-volume, throttle with `time.sleep` or parallelize with `concurrent.futures.ThreadPoolExecutor`. Long-running recipes should live in a scenario with retry.

---

## FindReplace

**Alteryx:** look up values in a second input of (find, replace) pairs and substitute — with options for whole-word match, append mode, and case sensitivity.

**Dataiku:**
- **Read replacements from a dataset** (the direct equivalent): Prepare recipe, Find and Replace processor, **Advanced: Read replacements from a dataset**. Point at an editable (or any) dataset with a "find" column and a "replace" column. No Join / Python needed. This is the preferred path.
- **Whole-word replacement inside a text** (not the Alteryx FindReplace normal mode) → Python recipe with regex boundary.
- **Exact match with join semantics** → Join (left) on `value = find` + Prepare `CreateColumnWithGREL: if(isnull(replace), value, replace)` + drop helper. Only use when the remap table is large or pushed-down SQL is critical.

---

## Spatial tools

Dataiku has more visual geospatial capability than is obvious — try the visual path before reaching for Python.

| Alteryx tool | Dataiku answer |
|---|---|
| `CreatePoints` (lat/lon → point) | Prepare `Create GeoPoint from lat/lon` processor. Inverse: `Extract lat/lon from GeoPoint`. |
| `Distance` (point-to-point) | Prepare `Compute distance between two points` (Haversine). Driving/walking/cycling distance → **GeoRouter plugin** (isochrones, routing) |
| `FindNearest` (kNN between two sets) | **GeoJoin recipe** with `within distance`, then Prepare compute-distance to pick closest. Supports contains, within-distance, beyond-distance, intersects, touches, disjoint, equality. **`--max-matches` caps but does NOT sort by proximity** — to replicate Alteryx's "1 nearest" semantics, GeoJoin all candidates within a generous radius, add `geoDistance` in a Prepare, then a Window (partition by left key, order by distance ASC, `rowNumber`) with postFilter `rn==1`. SQL haversine alternative below. |
| `FindNearest` — SQL alternative when inputs aren't on a geo-capable visual path | When inputs are file-backed and adding 2× `add-geopoint` Prepares + GeoJoin + Window-pick-min feels heavier than warranted, sync the inputs to a SQL connection (DuckDB, PostgreSQL, Snowflake — all have native `radians`/`sin`/`cos`/`asin`) and write a single `sql_query` recipe with haversine in a CTE: `2 * 3958.8 * asin(sqrt(pow(sin(radians(lat2-lat1)/2), 2) + cos(radians(lat1))*cos(radians(lat2))*pow(sin(radians(lon2-lon1)/2), 2)))`. CROSS JOIN the two sides + `ROW_NUMBER() OVER (PARTITION BY left_key ORDER BY dist ASC) = 1` picks the nearest. Expect 3 syncs + 1 SQL recipe (4 total) — competitive with the 5-recipe visual GeoJoin path. Same ~0.06% spheroid offset as `geoDistance`. |
| `Buffer` (expand/contract by value) | Prepare `Create area around geopoint` processor, or `geoBuffer` GREL formula. GeoRouter for routing-aware (isochrone) buffers |
| `Generalize` / `Smooth` (fewer vertices) | `geoSimplify` GREL formula |
| `SpatialInfo` (area, length, centroid, bbox) | `geoEnvelope` formula for bbox; Prepare geo-extract processor for area, centroid, length |
| `Spatial Match` (contains/intersects/touches) | `geoWithin` / `geoContains` GREL formulas for the simple case; GeoJoin recipe for full relation set (one recipe per relation) |
| `Heat Map` / `Binned Geo` | DSS Charts native (density and binned geo map types) |
| `PolyBuild` (point sequence → polygon/line) | **For the geometry itself** — Python (`shapely.geometry.Polygon` / `LineString`) — no visual path for ordering points into a single LineString WKT (Group `concat` does not preserve order). **For the typical downstream metric (`SpatialInfo.LengthMi` total trip distance)** — visual path: Prepare to build `point_wkt = "POINT(" + lon + " " + lat + ")"` → Window `lag(point_wkt)` partitioned by group, ordered by sequence column → Prepare `geoDistance(point_wkt, point_wkt_lag, "MILES")` (filter out first row per group where lag is empty) → Group `sum(leg_miles)`. See § PolyBuild + SpatialInfo below |
| `Spatial process` (polygon editing: union/intersection/…) | Python (`shapely` boolean ops) |
| `Trade area` | **GeoRouter plugin** (isochrones with transportation mode) |
| `MapInput` (user draws shape) | User-provided WKT/GeoJSON dataset; no UI drawing replacement |
| `Make Grid` | Python (shapely) — no direct visual equivalent |

Rule of thumb: if the flow has only 1–2 genuine-Python spatial tools (PolyBuild, Spatial Process, MakeGrid), collapse the spatial segment into a single Python recipe using `shapely` / `geopandas`. Everything else has a visual path via Prepare processors, GREL formulas, or GeoJoin.

### PolyBuild + SpatialInfo (sequence → length)

The `PolyBuild(SequencePolyline) → SpatialInfo(LengthMi)` pair is the most common Alteryx spatial pattern (compute total trip / route length per group). DSS resolves this WITHOUT building the LineString geometry, since `geoDistance(pt_wkt, pt_wkt, "MILES")` plus a per-leg sum gives the same total. 5 visual recipes, all push down to the SQL/local engine the input lives on:

1. **Prepare on cities** — extract `lon`/`lat` from the source coordinates (regex-extract if the source is JSON-like text — DSS will strip embedded `"` from CSV uploads, so use `match(Centroid, /.*\[\s*(-?\d+\.\d+),\s*(-?\d+\.\d+)\s*\].*/)[0|1]` against the de-quoted text), then build `point_wkt = "POINT(" + lon + " " + lat + ")"`. **Use WKT, not GeoJSON** — `geoDistance` accepts WKT `POINT(lon lat)` strings reliably; GeoJSON Point strings (`{"type":"Point","coordinates":[lon,lat]}`) returned empty in our test, with no warning. The column does not need to be re-typed to `geopoint` — string is fine for `geoDistance`'s input.
2. **Window** partitioned by `REP` (or your group key), ordered by the sequence column, `--compute lag:point_wkt:point_wkt_lag`. **Watch out:** the third segment of `--compute` (custom output name) is silently ignored by Window — output column is always `{column}_lag`.
3. **Prepare on the windowed dataset** — `add-filter-rows --action KEEP_ROW --formula 'length(strval("point_wkt_lag")) > 0'` (drops the first row per group, which has no predecessor) + **`add-geodistance --from point_wkt --to point_wkt_lag --output-column leg_miles --unit MILES`** (Prepare's `GeoDistanceProcessor`, NOT GREL `geoDistance()` — see the precision warning below).
4. **Group by REP** with `--agg leg_miles:sum --no-global-count`. Output is `leg_miles_sum` (total trip distance per rep).
5. **Sort** descending on `leg_miles_sum` (`--sort-col leg_miles_sum:desc`).

**GREL `geoDistance()` rounds to 2 decimals; `add-geodistance` Prepare processor is full-precision — and they use DIFFERENT spheroid math.** Tested on Challenge_032 (5-point trip, hotel + 4 surf sites in San Diego County):
| Method | Per-leg result | Sum (4 legs) | vs Alteryx 81.6396 |
|---|---|---|---|
| GREL `geoDistance(p1, p2, "MILES")` | 36.45, 3.55, 12.67, 29.02 (rounded to 2 decimals) | 81.69 | +0.06% (HIGHER) |
| Prepare `add-geodistance --unit MILES` | 36.375807100548414, 3.5480203538343713, 12.643350855533372, 28.94970912502732 (full precision) | 81.5169 | -0.15% (LOWER) |

**Always use `add-geodistance`** for trip-distance / route-length workflows where per-leg differences accumulate — full precision matters and the Prepare processor's spheroid model is closer to Alteryx than the GREL function (drift is smaller in absolute terms despite the opposite sign). Use GREL `geoDistance()` only for ad-hoc / per-row distance comparisons where 2-decimal precision is fine. **Both DSS implementations differ from Alteryx — Alteryx and DSS use different Earth ellipsoid parameters and there is no choice of Earth-radius constant that makes them match exactly.** SQL haversine (`R = 3958.8 mi`) drifts in the same direction as one of the DSS methods. Document the offset in the validation summary and treat as a "matches" result — do not chase the difference.

---

## PearsonCorrelation

**Alteryx:** emits a correlation matrix across numeric columns.

```xml
<Configuration>
  <Fields>
    <Field name="Hitter Rank" />
    <Field name="2015 Team Rank" />
    <Field name="Year" selected="False" />
    …
  </Fields>
  <Covariance value="False" />
</Configuration>
```

**Dataiku — preferred (visual-first, headless-safe):** Sync the input to a SQL connection, then SQL recipe with `CORR()`:

```bash
dku recipe create-sync sync_to_db -P PROJ -i input --output-ds input_db -c <sql_connection>
dku recipe run sync_to_db -P PROJ --wait

dku recipe create-sql pearson -P PROJ -i input_db --output-ds pearson_result \
    --connection <sql_connection> \
    --sql 'SELECT CORR(COALESCE("col_a", 0), COALESCE("col_b", 0)) AS "Result" FROM ${projectKey}_input_db'
dku recipe apply-schema pearson -P PROJ
dku recipe run pearson -P PROJ --wait
```

`CORR()` is in every standard SQL engine (Postgres, Snowflake, DuckDB, Redshift, BigQuery, Oracle). The Sync + SQL pair is two recipes, fully visual to the flow graph, no Python.

**Critical: `COALESCE(col, 0)` for null-handling parity.** Alteryx's PearsonCorrelation tool **treats null values as 0** when computing correlation — it does NOT use pairwise complete cases (the statistical convention used by SQL `CORR()`, pandas `df.corr()`, and numpy). Tested on Challenge_030 (fantasy-baseball draft, 253 rows where 104 had null `Hitter Rank`): pairwise-complete `CORR("Hitter Rank", "2015 Team Rank")` returned `-0.0337`; expected was `-0.0181`; wrapping in `COALESCE("Hitter Rank", 0)` reproduced the expected value exactly. **Always wrap nullable columns in `COALESCE(col, 0)` for Alteryx parity** — the value can differ by a factor of 2 or more on datasets with sparse null patterns. See `ayx/semantics.md` § Aggregation null-handling.

For multi-column correlation matrix, emit one row per column-pair via UNION ALL or a Python recipe (DSS `Statistics` cards in the UI are not headless / scenario-runnable). For interactive exploration, a Statistics card in the dataset UI is fine.

---

## Macros

Alteryx macros consolidate a group of tools into a reusable unit. Three flavors:

### Standard Macro

A sub-workflow with Input/Output tools, used to avoid repeating the same tool sequence at multiple call sites.

**Dataiku answer:**
- **App-as-recipe** is the closest equivalent — a project where specific datasets and variables are exposed as a "recipe" the user can drop into other flows. High adoption bar for low-code users; budget time for the first one.
- **Dataiku plugin recipes** (custom Python recipes packaged in a plugin) — higher investment, stronger UX than App-as-recipe for frequent reuse.
- **Inline duplication** — for macros called only 2–3 times, just inline the logic at every call site. The Flow becomes self-documenting.

### Batch Macro

A sub-workflow applied to each row (or each group) of a control dataset — the rest of the workflow stacks all outputs.

**Dataiku answer:**
- **If the batches are data-driven splits of one dataset** (same schema) → **partition the dataset**. Partitions with identical recipes applied in parallel. Requires designing the partition dimension up front.
- **If the batches are "apply process with different parameters per batch"** → **scenario-loop plugin** (`dss-plugin-scenario-loop`). Loop over a control dataset or a parameter list; each iteration runs a scenario step with substituted variables.
- **If the batches are "process many files with varying schema"** → native multi-file import (managed folder + regex + `Use as dataset`), or **Excel Sheet importer** plugin (one dataset per sheet), then Stack.

### Iterative Macro

Loop until a condition is met (N iterations or state-based). Classic uses: allocation problems (inventory, trade area assignment), transitive closure (hierarchy traversal, graph reachability), fixed-point computations.

**Dataiku answer — pick by shape:**
- **Hierarchy / transitive closure / graph reachability** (the most common iterative-macro pattern in real Alteryx flows — "walk up a parent chain", "find all descendants", "fan a tree out into ancestor pairs") → **one SQL recipe with a recursive CTE** on any SQL connection (PostgreSQL, Snowflake, DuckDB, etc.). `WITH RECURSIVE chain AS (base SELECT … UNION ALL recursive SELECT … FROM chain JOIN base ON …) SELECT …`. If the input dataset is on a filesystem connection, prepend ONE `dku recipe create-sync -i input --output-ds input_db -c <sql_conn>` so the SQL recipe has a SQL-backed input. Total: sync + sql = 2 recipes, regardless of hierarchy depth. **Visual alternative** for bounded depth (≤ 5 levels): N chained `create-join` recipes (each hop is one self-join), then `create-stack` of N projections to the long form. Recipe count grows linearly with depth.
- **Allocation problems** (inventory rebalancing, trade-area assignment) — these genuinely need an explicit termination test on aggregate state. **Scenario-loop plugin** (`dss-plugin-scenario-loop`) with a custom condition — cleanest visual-ish path.
- **Anything else state-based** that doesn't decompose into a fixed-point JOIN — **Python recipe with explicit loop**, last resort.

The "no code-free equivalent" disclaimer applies only to the allocation/state-based shape — transitive-closure macros DO have a clean visual-ish equivalent (SQL recursive CTE).

**Caveat:** macros often come bundled with Dynamic Input / Dynamic Rename tools. Migrate the whole cluster at once — the individual tools outside the macro context don't make sense.

---

## Dynamic Input

**Alteryx:** read from a database/file at runtime; row-driven or parameter-driven file/sheet/query selection.

**Dataiku:**

- **Parametric SQL / parametric export run N times** → **Dynamic Recipe Repeat** (native). Open the recipe's Advanced tab → "Dynamic recipe repeat" section → Enable → pick a parameters dataset. The recipe runs once per parameters row, expanding `${col}` variables from the current row into the query/body. For each column in the parameters dataset, a variable is created automatically; map columns to specific variable names to avoid shadowing.
  ```
  Parameters dataset:
    Col1    Col2
    Jan     2024
    Feb     2024
    ...
  SQL recipe body: SELECT * FROM sales WHERE month = '${Col1}' AND year = ${Col2}
  ```

- **"Pick the latest file in a folder by modification time"** → **Dynamic Dataset Repeat** (native). Chain:
  1. **List Contents recipe** on the managed folder → dataset with `path` + `last_modified` columns.
  2. **TopN recipe** sort `last_modified` desc, limit 1 → single-row dataset with the latest `path`.
  3. Create a dataset on the managed folder, enable **"Dynamic dataset repeat"** in Advanced, pick the TopN output as parameters, set **"Files to include"** to `${path}`. The dataset resolves at build time to the most recent file.

- **Read many files from one folder** (all at once) → managed folder + dataset with include-regex filter (`tab1_.*\.csv`). `dku dataset create --type FilesInFolder`.

- **Read all sheets of an Excel file** → native multi-sheet Excel reader (recent DSS), or Excel Sheet importer plugin (generates one dataset per sheet). Stack afterward.

- **Parametric SQL when Dynamic Recipe Repeat doesn't fit** (e.g. batching to overcome query-length limits) → Python recipe issuing queries via `dataiku.core.sql`, or pre-process the parameters dataset to batch rows (e.g. 10 at a time) and feed the batched form to Dynamic Recipe Repeat.

---

## YXDB files (native Alteryx binary format)

DSS reads `.yxdb` natively — no plugin, no Python conversion. Drop the file into a managed folder and create a dataset pointing at it; DSS parses the schema.

**Caveat:** `.yxdb` Date / DateTime fields have no timezone metadata. By default DSS reads them as **strings**. To read them as dates, set a timezone in the dataset's format configuration. Prefer parsing in a Prepare recipe downstream if the timezone is ambiguous.

**When to use:** if the user has only `.yxdb` outputs of an Alteryx workflow and no upstream access, migrate by consuming the `.yxdb` as a dataset and rebuilding the downstream logic. Often simpler than replicating the full upstream pipeline.

---

## Email output

Alteryx `Email` tool → **Send email** plugin recipe. The plugin iterates rows of an input contacts dataset, sending one email per row. Features:

- Mail channels configured at the instance level (no per-recipe SMTP config).
- Dynamic Recipient / Subject / Body pulled from input columns, with static fallbacks.
- Dataset attachments as CSV or Excel, or embedded inline as HTML table.
- **Conditional formatting** is preserved on Excel attachments and inline-HTML bodies.
- Full JINJA templating for the body.

For a simple "send a build-complete email to one recipient", skip the plugin and use a scenario `Send message` step. For per-row dynamic emails with attachments, use the plugin.

**Conditional formatting trick for inline HTML bodies:**
1. Configure conditional formatting on the dataset in Explore tab (column color rules, row rules).
2. In the scenario's Send Message step: Source = Inline, Send as HTML checked, attach the dataset as Excel with "Apply conditional formatting" and "embed as HTML variable" → reference as `${datasetHtml}` in the body.

---

## Excel Templater

Alteryx's "write to Excel template" pattern → **Excel Templater** plugin recipe.

- Input: the datasets to populate + a managed folder with the `.xlsx` template.
- The template has tagged cells (default tag: `DATASET.tablename`) — the plugin finds each tag and writes the matching dataset starting at the tag's position.
- Only dataset contents are written, not headers — the template controls headers.
- Output: the populated `.xlsx` in the output managed folder.

---

## Dynamic Filename

Alteryx often pairs Output with a dynamic filename pattern (e.g. `report_20240415.csv`). DSS answer: a scenario with two steps:

1. **Custom Python** step sets a project variable, for example `dynamic_filename_csv = f"report_{datetime.utcnow():%Y%m%d}.csv"`.
2. **Run the Export-to-Folder recipe** with output filename set to `${dynamic_filename_csv}`.

If the scenario also emails the file, attach `${dynamic_filename_csv}` from the managed folder in a Send Message step.

---

## Analytic Apps

Alteryx `Analytic App` (desktop interactive UI) → **Project variables** + **Dataiku Applications**.

- **Project variables** are referenced in visual/code recipes as `${var_name}`. Set on the project (not per-recipe) and updated via the UI or scenarios.
- **Applications** expose a visual form on top of a project — user fills in values, these populate project variables, then runs a scenario. The user never sees the Flow.
- **App-as-recipe** (see Macros above) packages a whole project as a callable recipe in other flows.

For Alteryx apps with heavy custom UI, expect HTML/JS customization in the Application layer. Non-trivial lift.

---

## Excel input / output

### Input

Alteryx excels here (pun intended). DSS options:
- **Multi-sheet file** → native DSS Excel import (recent versions), or **Excel Sheet importer** plugin.
- **Files behind cloud storage** → **SharePoint Online**, **OneDrive**, **Google Drive**, **Google Sheets**, **Dropbox**, **Box** plugins. Get the source off local drives first; nothing else works reliably for shared, repeating workflows.
- **Sheet name as dataset column** → native DSS, or Google Sheets plugin.
- **Named ranges** → no direct support. Export to CSV on the Excel side, or Python recipe with `openpyxl`.

### Output

Also Alteryx-strong. DSS options:
- **Excel export with conditional formatting** → DSS Explore conditional formatting is preserved when exporting to Excel.
- **Many datasets into one multi-sheet file** → **Multisheet Excel export** plugin.
- **Template-based Excel output (write to ranges)** → private plugin; contact internal TAM.
- **Dynamic per-partition Excel files / emails** → private plugin; else scenario with Python step.

Challenge the requirement first: is the Excel file the actual deliverable, or is it a dashboard/email/workspace that got implemented as Excel because Alteryx made it easy?

---

## Workflow patterns

Patterns that span multiple tools. Recognize the pattern, collapse the group into one recipe where possible.

### Pattern: Range join (GenerateRows → Join)

**Alteryx:** `TextToColumns` (split "start-end") → `AlteryxSelect` (cast to int) → `GenerateRows` (expand start..end) → `Join` (equi-join on expanded value).

**Dataiku:** collapse the whole group into one SQL recipe:

```sql
SELECT a.*, b.*
FROM customers a
JOIN ranges b ON a.postal_area BETWEEN CAST(SPLIT_PART(b.range,'-',1) AS INT)
                                   AND CAST(SPLIT_PART(b.range,'-',2) AS INT)
```

Or (non-SQL): Prepare split + Python merge with pandas `merge_asof` / explicit `apply`.

### Pattern: Filter → Union (conditional reroute)

**Alteryx:** `Filter` → True branch processed → `Union` with False branch.

**Dataiku:** use two Prepare recipes on the same input (one filters True, one False), apply different logic to each, then `Stack`. Or — cleaner — a single Prepare with a `CreateColumnWithGREL` that branches (`if(cond, procA(x), procB(x))`).

### Pattern: Cross-tab → Dynamic Rename (pivot with renamed columns)

**Alteryx:** `CrossTab` then `DynamicRename` to clean up auto-generated column names.

**Dataiku:** Pivot recipe + a trailing Prepare with static `RenameColumns` rules. DynamicRename-from-input-table requires a Python recipe.

### Pattern: Multi-Row Formula → Summarize (de-duped running state)

**Alteryx:** MultiRowFormula marks "first in group", then Filter to first-only, then Summarize.

**Dataiku:** Window recipe with `first_value` aggregation (no Filter needed), or Group with `first` agg.

## Predictive Tools (R-based macros)

Alteryx ships `Predictive Tools\\*.yxmc` macros that wrap R packages (`forecast`, `nnet`, `glmnet`, etc.). They appear in `.yxmd` as `<Node>` elements with `<EngineSettings Macro="Predictive Tools\\<Name>.yxmc" />` and an empty `<GuiSettings Plugin>` (the Plugin is the macro file path, not a built-in plugin name) — so XML parsing returns an empty plugin name. Always check `EngineSettings/@Macro` when you see an empty `Plugin` attribute.

### ARIMA + TS_Forecast (time-series forecasting)

**Alteryx:** `ARIMA.yxmc` (model fit) → `TS_Forecast.yxmc` (forecast + confidence intervals). Two macros, output schema: `Period, Sub_Period, forecast, forecast_high_95, forecast_high_80, forecast_low_80, forecast_low_95`.

The Configuration `<Value>` parameters on the ARIMA node map to:

| Alteryx param | Meaning | Python equivalent |
|---|---|---|
| `target_field` | Series column | `y = df[col]` |
| `freq_weekly` / `freq_monthly` / etc. | Series frequency (one is `True`) | `freq = "W"` / `"M"` / etc. (only used for date-index labelling, not for the model itself) |
| `max_p`, `max_q` | AR / MA order ceilings (non-seasonal) | `auto_arima(max_p, max_q)` |
| `s_max_P`, `s_max_Q` | seasonal AR / MA ceilings | `auto_arima(max_P, max_Q)` (only used if `seas_dif=True`) |
| `max_order` | upper bound on `p+q+P+Q` total | `auto_arima(max_order)` |
| `ic_aic` / `ic_aicc` / `ic_bic` | information criterion (one is `True`) | `auto_arima(information_criterion="aic"/"aicc"/"bic")` |
| `drift` | include linear time trend (drift) | `with_intercept=True` for d=0; for d>=1 wrap with statsmodels `trend="t"` or `"ct"` |
| `first_dif` / `seas_dif` | force differencing | `d=...` / `D=...` (else auto-detected) |
| `box_cox` | Box-Cox transform | `BoxCoxEndogTransformer` (statsmodels) — rare in practice |

**Dataiku:** No first-class visual auto-ARIMA recipe — Python is the right answer. Two viable libraries:

1. **`pmdarima`** (Hyndman-Khandakar algorithm, mirrors R's `forecast::auto.arima` closely). Cleanest port:
   ```python
   import pmdarima as pm
   model = pm.auto_arima(y, max_p=2, max_q=2, max_P=1, max_Q=1, max_order=5,
                         information_criterion="aicc", with_intercept=True,
                         seasonal=False, error_action="ignore", suppress_warnings=True)
   point, ci80 = model.predict(n_periods=horizon, return_conf_int=True, alpha=0.20)
   _,     ci95 = model.predict(n_periods=horizon, return_conf_int=True, alpha=0.05)
   ```

2. **`statsmodels.tsa.arima.ARIMA`** with manual grid search (when `pmdarima` is unavailable or pinned to an incompatible NumPy):
   ```python
   from statsmodels.tsa.arima.model import ARIMA
   import itertools
   best = None
   for p, q in itertools.product(range(0, 3), range(0, 3)):
       if p + q > 5: continue
       for trend in ["c", "ct"]:  # "c"=intercept only, "ct"=intercept+linear time (drift)
           res = ARIMA(y, order=(p, 0, q), trend=trend,
                       enforce_stationarity=False, enforce_invertibility=False).fit()
           if best is None or res.aicc < best[0]:
               best = (res.aicc, (p, 0, q), trend, res)
   res = best[3]
   fcst = res.get_forecast(steps=horizon)
   point, ci95, ci80 = fcst.predicted_mean, fcst.conf_int(alpha=0.05), fcst.conf_int(alpha=0.20)
   ```

**Output convention** (Period / Sub_Period): `Period = abs_idx // m + 1` (1-indexed period within frequency), `Sub_Period = abs_idx % m + 1` (sub-period within current Period), where `abs_idx = n + i` (i in 0..horizon-1, n is input length, m is the periodicity for the chosen frequency — 52 for weekly, 12 for monthly). Period/Sub_Period are macro-internal labels; for downstream join-back to a date axis, derive a real timestamp from the input series instead.

**Numerical fidelity warning.** Alteryx's R-based ARIMA and Python's pmdarima/statsmodels diverge by 5–15% on point estimates and 10–20% on confidence-interval widths even with identical hyperparameters. Optimizer choice (Nelder-Mead vs L-BFGS), default tolerances, and feature-search heuristics differ. **Treat this as a shape-based migration**: row count, schema, sub-period range, and forecast-trajectory direction must match; exact-string match across implementations is unreachable without invoking R from a Python recipe via `rpy2`. Acceptable validation: 6 rows, all 7 columns, point forecasts in the same magnitude band as the source, CIs widening over the horizon (low_95 < low_80 < forecast < high_80 < high_95).

**Code-env.** statsmodels and pmdarima are not in any default DSS env — install via `dku code-env set-packages <env> --packages 'pandas>=2,<3\nnumpy>=1.22,<3\nstatsmodels>=0.14\npmdarima'`. Pin numpy explicitly (pmdarima compiled against numpy<2 in some wheels — pin to `numpy<3` to allow the resolver flexibility). The Python recipe must `set-settings '{"envSelection":{"envMode":"EXPLICIT_ENV","envName":"<env>","envVersion":"BUILTIN_PINNED"}}'` to bind to the env.

### Other Predictive Tools macros

| Alteryx macro | DSS path |
|---|---|
| `Linear_Regression.yxmc` | Visual ML Lab Prediction recipe (Linear regression algorithm) — visual-first |
| `Logistic_Regression.yxmc` | Visual ML Lab Prediction recipe (Logistic regression) — visual-first |
| `Decision_Tree.yxmc` | Visual ML Lab Prediction recipe (Decision Tree) — visual-first |
| `Random_Forest.yxmc` | Visual ML Lab Prediction recipe (Random Forest) — visual-first |
| `Boosted_Model.yxmc` | Visual ML Lab Prediction recipe (XGBoost / LightGBM) — visual-first |
| `K_Centroids_Cluster_Analysis.yxmc` | Visual ML Lab Clustering recipe (K-Means) — visual-first |
| `Neural_Network.yxmc` | Visual ML Lab Prediction recipe (Deep Learning / MLP) — visual-first |
| `ARIMA.yxmc` + `TS_Forecast.yxmc` | Python recipe with statsmodels/pmdarima (above) |
| `ETS.yxmc` (exponential smoothing) | Python recipe with `statsmodels.tsa.holtwinters.ExponentialSmoothing` |
| `Spline_Model.yxmc` | Python recipe with `scipy.interpolate.UnivariateSpline` or `patsy.dmatrix("bs(...)")` |

The classification/regression cases are where visual-first applies — the DSS Lab fits the model graphically and produces a saved-model object, no Python required. Time-series and spline are Python-only.
