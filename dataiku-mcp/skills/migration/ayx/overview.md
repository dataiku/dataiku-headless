# Alteryx Migration

Source-specific entrypoint for migrating Alteryx workflows (`.yxmd`, `.yxzp`, `.yxdb`) to a DSS flow. Read the top-level `migration` SKILL.md first (cross-source rules, phases, common gotchas). This file holds only Alteryx-specific parts. Pair with `dku-cli` (execution) and `dataiku` (platform). SQL target → also read `dku-cli`'s `references/formulas.md` § GREL → SQL push-down.

**Contents:** [Approach](#approach--job-not-tool) · [Alteryx-specific rules](#alteryx-specific-rules) · [Phase 1 — parsing the source files](#phase-1--parsing-the-source-files) (`.yxmd`/`.yxzp`/`.yxwz`/`.yxdb`, TextInput extraction + upload traps, In-DB, inventory shape, non-migratable patterns) · [Tool → recipe quick reference](#tool--recipe-quick-reference) · [Collapse triggers](#collapse-triggers--running-the-phase-2-collapse-pass) · [Alteryx-specific gotchas](#alteryx-specific-gotchas) (parsing, verification, value-mismatch) · [Reference map](#reference-map-also-the-tool--file-router)

## Approach — job, not tool

Map the *job to be done*, not the Alteryx tool. Many Alteryx patterns (intermediate-dataset avoidance, desktop previews, manual layout) exist only because Alteryx is desktop-first — when a workflow leans on that behavior, it's an onboarding issue, not a migration gap. Read `frictions.md` when the user pushes back on a DSS concept.

## Alteryx-specific rules

1. **An Alteryx tool is not a recipe 1:1.** Formula/AlteryxSelect/TextToColumns/RegEx/DynamicRename/RecordID/DateTime → Prepare steps. Fan out only when semantics differ (Join→Join, Summarize→Group, CrossTab→Pivot, Union→Stack, Sort→Sort). Several tools also collapse INTO one recipe (`collapse-triggers.md`). Expected ratio **3:1 to 5:1** (tools ÷ recipes).
2. **Alteryx types are explicit; DSS inference is not.** `AlteryxSelect` carries `type="Int32"|"Double"|"V_WString"|"Date"|"DateTime"` per column. Always `dku dataset set-schema` right after upload from that metadata — don't trust DSS STRING-for-everything CSV inference.
3. **An app keeps its interface — don't migrate only the flow.** A `.yxwz`, or any workflow carrying `AlteryxGuiToolkit.Questions.*` / `Action.Action` tools, is an *interactive app*: its value is the self-service form, not just the output table. Migrate the flow first (literal substituted values keep it testable), THEN **rebuild the interactive surface** — **App Designer by default** (questions→form params→variables→scenario→result tiles), a webapp only for genuinely custom UI. The question/Action tools are dropped *as recipes* (they never become recipes) but their *semantics* — each question = a parameter, each Action = a `${var}` binding — are deliverables. Stopping at the flow is allowed only if you call it out as an explicit deviation; never drop the interface silently. How-to + the question→param map + the App-Designer-vs-webapp decision: tools-io-apps-ml.md § Analytic Apps.

## Phase 1 — Parsing the source files

> **Script paths are relative to this skill's `ayx/` folder.** The `scripts/*.py` helpers below resolve as written only when run from that folder; from any other working directory anchor with `AYX=/path/to/migration/ayx` and call `python "$AYX/scripts/<name>.py"` (or `uv run --with yxdb python "$AYX/scripts/<name>.py"`).

### `.yxmd`
Plain UTF-8 XML. `xml.etree.ElementTree.parse(f)`. Shape:
```xml
<AlteryxDocument><Nodes>
  <Node ToolID="N"><GuiSettings Plugin="…"/><Properties><Configuration>…</Configuration></Properties></Node>
</Nodes><Connections>…</Connections></AlteryxDocument>
```
- `GuiSettings.Plugin` → tool type (`AlteryxBasePluginsGui.Formula.Formula`, `…Join.Join`, `…TextInput.TextInput`).
- `Properties/Configuration` → tool params (schema per tool; the § Tool → recipe quick reference routes each tool to its leaf file).
- `<Connections>` → DAG. Each `<Connection>` has `<Origin ToolID="X" Connection="Output|Join|Left|Right"/>` + `<Destination ToolID="Y" Connection="Input"/>`. Join emits three outputs: `Left` (unmatched left), `Join` (matches), `Right` (unmatched right).
- `TextBox` / `BrowseV2` are presentation-only — ignore as recipes, but **read their text**: TextBoxes carry migration intelligence (source-table lists, prod-vs-test markers like "à retirer en PROD", delivery changelogs) that belongs in the Phase-2 gate. `dump_workflow.py` dumps them verbatim in its ANNOTATIONS block. **Exception in an app:** a *terminal* `BrowseV2` is the result the user saw → rebuild it as a result tile (KPI/chart insight + dashboard, or `DOWNLOAD_DATASET`), see tools-io-apps-ml.md § Analytic Apps.

### `.yxzp`
ZIP of the `.yxmd` + data files. `unzip`, work from the inner `.yxmd`. **Bundled macros live under `_externals/N/*.yxmc`** — parse a custom `.yxmc` (Knapsack/optimizer/Cleanse) with the same `ET` recipe to recover the real algorithm; the macro is source of truth, not the tool name. See tools-predictive-ml.md § Optimization & prescriptive macros.

**Encrypted/decoy macros — check the connection graph FIRST.** An encrypted/unreadable `.yxmc` is NOT automatically a blocker. A macro node with **no inbound/outbound connection is a decoy** the solution never runs — ignore it. "Catch me if you can" workflows ship encrypted decoy macros (`DynamicStringToNum_encrypted`, `UnknownFields2_Encrypted`) as red herrings. Even for a *connected* encrypted macro you rarely need internals: read the expected-output `.yxdb` + any lookup `.yxdb` and reverse-engineer from data (input→output→lookup mapping). Don't log "macro encrypted, can't read algorithm" until you've confirmed it's on the executed path AND data can't reveal the mapping.

### `.yxwz`
Alteryx **Analytic App** ("Wizard") — same XML schema as `.yxmd`, same parser. A workflow pair may ship `start_file.yxmd` + `solution.yxwz` (extension change is the only signal).

App-specific plugins (drop in inventory like `TextBox`/`BrowseV2`):

| Plugin | Purpose | Migration |
|---|---|---|
| `AlteryxGuiToolkit.Tab` | UI tab grouping | Drop |
| `…Questions.DropDown/TextBox/Date/NumericUpDown/…` | User-input widget | Drop — replaced by static value (see Action) |
| `AlteryxBasePluginsGui.Action.Action` | Wires a widget value into a tool's config at runtime | Drop the wiring; **substitute the user value statically** into the target tool before extracting. Connection `(question_tool, target_tool, "Action")` shows the feed |

**Action-target substitution.** A saved `.yxwz` already has the resolved value substituted literally (`[N] < 9`, not `%Question.levels%`) — migrate the literal expression, treat `Action`/question nodes as drop-on-sight UI; almost never decode the `Action` config. In-flow baked values are self-consistent with the solution's `BrowseV2` output. **Caveat (only when the Action feeds a separate `TextInput` *parameter* you upload):** the widget default sometimes ≠ the value that generated the documented expected output — pick the value the *expected output* uses (read from the `BrowseV2`-attached TextInput) and override your uploaded dataset to it. Static migration trades parametricity for test-case fidelity.

Static substitution migrates the *flow*; the *app keeps its interface* rule (§ Alteryx-specific rules) still applies — rebuild the surface afterwards: tools-io-apps-ml.md § Analytic Apps.

### `.yxdb`
Alteryx native binary dataset. **DSS reads these natively:** create a dataset on a managed folder containing the `.yxdb`; DSS parses the schema. Caveat: `.yxdb` date/datetime fields have no timezone → DSS reads them as strings by default; set a timezone in the dataset format config to parse as date. No Python needed for the native-folder path.

**CSV round-trip loses types — type each numeric column from its actual values; sibling columns can differ.** yxdb stores some numeric columns `Int`, others `Double`, so a decimal serializes as `"39.0"`. Declaring it `int` makes DSS read every `"39.0"` as **null** (silent); a downstream `add-fold` (`MultiColumnFold`) then **drops those rows**. Never blanket-type look-alike columns — inspect per-field `data_type`, type any `Double`/`Float` as `double`. Symptom: folded rows = `days×(N-1)` instead of `days×N`.

The expected-output `.yxdb` shipped alongside a `.yxmd` is **authoritative ground truth** — read it, walk every row, compare against `dku --format json dataset head` of the final dataset. Do NOT trust cached `BrowseV2` data (can be empty/absent). Reading + SpatialObj→WKT decode → `scripts/yxdb_read.py`.

**Spatial columns (`SpatialObj`) ARE decodable — not a blocker.** `scripts/yxdb_read.py --spatial COL` decodes geometry to WKT. Export a CSV with a `geom_wkt` column, `set-schema` it to `geometry`. The spatial op is then **VISUAL, not Python**: for point-in-polygon `SpatialMatch`, `add-geopoint` the point side, then `dku recipe create-geojoin --operator CONTAINS -g <polygon_geom> -g <point_geom> --join-type INNER` — DSS `CONTAINS` matches geopandas `within` exactly. Reserve Python/shapely for non-visual geometry (buffers, dissolve, densification). See tools-spatial.md.

**`.yxdb` columns can hold per-row image blobs** (render/portfolio assets): a `V_String` cell like `<encsection … enclen="N">BASE64…</encsection><img src="…"/>` is an embedded image, decodable with `scripts/decode_encsection.py`. Decode mechanics + folder-keying + the render recipe: tools-io-apps-ml.md (encsection FINISH block).

**No solution `.yxmd` and no expected `.yxdb`? Decode the embedded goal-preview image.** Some workflows ship ONLY a start `.yxmd`; the expected result is a **screenshot embedded in a reporting tool** — any tool with an `<EncodedImage>`/`<encsection>` (base64 PNG) in `<Configuration>`, usually on a **disconnected branch** (feeds only `BrowseV2`). That image IS ground truth: `base64.b64decode("".join(enc.text.split()))` → write `.png` → view → reverse-engineer the aggregation. For a **count crosstab** the count *signature* pins the filter: a per-year total = days-in-month (28/29-leap) means filter to **one month + one entity**, count days; a flat ~N is a fixed panel. The image title often encodes the filter; brute-force the entity that reproduces the preview cells.

### TextInput extraction
`scripts/extract_textinput.py workflow.yxmd -o ./out` → one `tool_<id>.csv` per TextInput. Then per file:
```bash
dku dataset upload <ds> -p PROJ -f tool_<id>.csv
dku dataset set-definition <ds> -p PROJ < def.json    # re-apply after EVERY upload (upload resets formatParams)
dku dataset set-schema <ds> -p PROJ --columns '<from AlteryxSelect types>'
```
See § Single-column TextInput upload traps for the format-param fixes, and the line-WRAPPED-records rule below.

**Mega-field input — DSS CSV reader has a hard 131072-byte per-field limit.** A single-row CSV whose one column holds a large blob (full HTML page, multi-page XML, big JSON) → `dku dataset head` errors `field larger than field limit (131072)` regardless of `formatParams.maxRowChars` (per-row, 100M default; 131072 is a CSV-reader internal, not configurable). Fix: **pre-split the blob into rows BEFORE upload** on a record-level delimiter mirroring the downstream parse intent (HTML on `<h3`, XML on the record-wrapper tag) — Alteryx's `TextToColumns(split-to-rows)` baked into the Python upload-prep.

**Fixed-width report with line-WRAPPED records → merge continuation lines in upload-prep, then ONE visual `RegexpExtractor`.** Legacy text reports (Census, mainframe) wrap a long field onto a 2nd physical line; Alteryx uses `MultiRowFormula` (look-behind merge) before parsing. DSS Prepare has **no look-behind/multi-row formula**, so merge in the Python upload-prep: a *record* line matches the key pattern; a non-matching non-blank line is a continuation → `out[-1]=out[-1].rstrip()+" "+s.strip()` (break on the footnote marker, skip title/header). Upload merged single-column (tab sep + `quoteChar:""` so names-with-commas survive — § traps), then the parse collapses to **one `RegexpExtractor`** (single anchored multi-group pattern; `../../dku-cli/references/prepare-processors.md` § RegexpExtractor) + `create-topn`. Canonical mapping for **`MultiRowFormula` rejoining wrapped lines** (distinct from lag/lead/cumulative — tools-state-parsing.md).

### Single-column TextInput upload traps
**"Fake-CSV-in-one-column" TextInput data mis-parses on autodetect.** After EVERY `dku dataset upload` re-apply `set-definition` (upload resets `formatParams`). Verify: `dku --format json dataset head` + row count (`dku --format json dataset info --recompute | jq .rows` vs `wc -l`).

| Data shape | Symptom | Fix |
|---|---|---|
| values contain `,`/`"` | `,` chosen as sep, quotes stripped, wrong shape / header-detect fails | write `.tsv`; `set-definition` `separator="\t"`, `quoteChar=""`, `parseHeaderRow=true`, explicit `schema.columns`; split later via `ColumnSplitter` |
| values contain `:`/`;`/`\|`/space | sep guessed as that char → `col_0/col_1`; space may also set `skipRowsBeforeHeader:1` (row-1 data promoted to header) | `set-definition` `separator=","`, `skipRowsBeforeHeader=0`, `parseHeaderRow=true`, explicit `schema.columns`. Two single-col files in one flow can disagree — fix each |
| clean single column, no delimiter | DSS flips `formatType:"csv"→"line"`; `head` returns N rows incl. header; your `formatParams` ignored | explicitly set `formatType:"csv"` AND full `formatParams` (`style:"excel"`,`charset:"utf-8"`,`separator:","`,`quoteChar:'"'`,`escapeChar:"\\"`,`parseHeaderRow:true`,`skipRowsBeforeHeader:0`). Verify `jq .formatType`=="csv" |
| rows start with `"` | leading `"` read as quote → unbalanced-quote rows silently DROPPED (fewer rows than source) | pre-strip ALL `"` (`line.replace('"','')`) before upload; re-apply `set-definition` after |
| cell values contain literal CR/LF (multi-line cells) | the pre-strip-quotes fix above un-quotes the newline-bearing cell → one record splits across rows | do NOT strip quotes here — KEEP CSV quoting, or merge each record to one physical line in upload-prep (cf. line-WRAPPED-records rule above) |

### External file inputs
`AlteryxBasePluginsGui.DbFileInput.DbFileInput` — config has a `<File>` path, usually shipped alongside; if missing, ask the user. `.yxdb` files → read via `scripts/yxdb_read.py` or the native-folder path above.

### In-Database workflows (`LockIn*`)

`LockInGui.LockIn*` plugins are Alteryx's In-DB variants — the whole flow runs as SQL push-down on one connection, a hard engine mandate ("one engine per flow", migration `SKILL.md`): keep every migrated dataset on that SQL connection. Without the connection, build on filesystem + DSS engine and document the engine deviation; re-point at delivery.

| In-DB tool | Dataiku recipe |
|---|---|
| `LockInInput` | **Not a source** — its `<Query>` is workflow logic (embedded-SQL rule, migration SKILL.md). Base tables it reads → source datasets (in prod, SQL datasets on the same connection); the query's joins/filters/aggregations/CASE → visual recipes. A pure single-table `SELECT col, …` with no logic → just the source dataset |
| `LockInFilter` | Prepare (filter) — `Mode: Simple` carries field/operator; `Custom` carries an expression |
| `LockInFormula` | Prepare (formula steps) — same `FormulaFields` schema as regular `Formula` |
| `LockInJoin` | Join — **one output only** (`JoinMode` INNER/LEFT/RIGHT/FULL), unlike the 3-anchor standard Join |
| `LockInSelect` | Prepare (rename/drop/retype) — same `SelectFields` schema, `*Unknown` semantics apply |
| `LockInUnion` | Stack — `Mode: ByName` ≙ UNION column alignment |
| `LockInSummarize` | Group |
| `LockInOutput` | The output dataset (`<Table>`, `CreateMode`). Wrapping write-side macros (Parquet rewrite, stats refresh, free-SQL DDL — e.g. `Hadoop_rewrite_table.yxmc`, `Passage_requete_libre*.yxmc`) are platform side-effects, not flow logic → DSS-native storage settings or a scenario SQL step; document the drop |

`dump_workflow.py` prints an In-DB banner, one EMBEDDED LOGIC block per query (clause census + tables read + verbatim SQL), and the INPUT CONTRACT (deduplicated base tables = the leaf datasets). Cross-check that contract against any source-table TextBox — the mechanical extraction is authoritative (annotations go stale; here-be queries the doc forgot).

### Inventory shape

Generate the skeleton mechanically — `scripts/dump_workflow.py workflow.yxmd` parses the tool list + connection DAG into this table (Tool ID / Plugin / Inputs / Outputs filled, presentation-only tools flagged); then fill *What It Does* + *Migratable?* by reading each tool's config. The size comment counts canvas tools **plus embedded-SQL operations** — plan on the sum, not the tool count. Tools carrying embedded SQL arrive pre-flagged `⚠ decompose`; the EMBEDDED LOGIC, INPUT CONTRACT and ANNOTATIONS blocks below the table are part of the inventory — read them before drafting Phase 2.

**The same script prints an OUTPUT CONTRACT block** — for each terminal tool (one feeding only a `BrowseV2`/sink) it reads the cached `Properties/MetaInfo/RecordInfo` of the anchor that feeds the sink and lists its fields *in order*. That ordered list is the output column contract: the migrated terminal dataset must match its set, names and order exactly. Record it in Phase 1 (it is the `columns` of your `--contract`) — the schema is pinned by the workflow even when no expected *values* ship, so "no ground-truth CSV" never excuses a wrong output column set. When Alteryx didn't cache the schema the block is empty → derive the contract from the terminal tool's own `AlteryxSelect`/config instead.

```
| # | Tool ID | Plugin | What It Does | Inputs | Outputs | Migratable? |
|---|---------|--------|--------------|--------|---------|-------------|
| 1 | 13 | TextInput | Customer records (2678 rows, 5 cols) | — | #29 | Yes → UploadedFiles dataset |
| 2 | 29 | TextToColumns | Split "Range" on "-" into Range1,Range2 | #13 | #30 | Yes → Prepare |
| 3 | 34 | Join | Join customers.Postal Area = ranges.Area | #13, #33 | #36 | Yes → Join recipe |
```

### Non-migratable patterns

| Alteryx pattern | Reason | Dataiku answer |
|---|---|---|
| `TextBox`, `ToolContainer` | GUI annotation | Ignore — use wiki / flow zone names |
| `BrowseV2` | Result viewer | DSS UI, or `dku dataset head` |
| **Chart/plot deliverable** (goal is "plot/visualize X"; start is `Input→BrowseV2`, solution ends in a Browse/Tableau viz, no expected table) | Deliverable is a chart, not a table | **NOT a block.** Reshape to tidy long, build a **native chart insight + dashboard** (`dku insight create --type chart` → `set-chart-type`/`add-dimension --slot 0/1`/`add-measure` → `dashboard create`+`add-tile`). Validate by artifact+shape (Phase 4): `insight validate` passes, tile `tileType:"INSIGHT"`+`insightType`, bound dataset has expected rows. JSON in `../../dku-cli/references/dashboards.md` |
| `Macro` (standard) | Reusable sub-workflow | **App-as-recipe**, or inline at each call site. tools-io-apps-ml.md |
| `BatchMacro` | FOR-EACH over a control dataset | **Partitioned dataset** (data-driven split), or **scenario-loop plugin**. tools-io-apps-ml.md |
| `IterativeMacro` | Until-condition loop | Classify by shape, in order: growth-to-threshold → CLOSED FORM (1 Prepare, check FIRST); hierarchy/transitive closure → SQL recursive CTE; allocation/state-termination → scenario-loop plugin; else Python. Full decision ladder: tools-io-apps-ml.md § Iterative Macro |
| `Dynamic Input` | Data-driven file/query selection | **Dynamic Recipe Repeat** (parametric SQL/export). **Dynamic Dataset Repeat** on a folder + List Contents + TopN (latest file). tools-io-apps-ml.md |
| `Detour` / build-container-on-condition | Conditional flow branch | Zones don't branch — **Split recipe** routing all rows to one output vs none. frictions.md |
| `AlteryxApp` / `Questions.*` / `Action.Action` (interactive prompts) | Desktop user input | **Not droppable** — *app keeps its interface* rule (§ Alteryx-specific rules); rebuild: tools-io-apps-ml.md § Analytic Apps |
| `Email` / `Render` / `Report*` | Desktop reporting | Dashboard + Scenario reporter |
| **Whole Reporting/Portfolio render chain** — `PortfolioCompose*` (`Render/Image/Layout/Text/Table`), base Reporting (`Report Text/Image/Layout/Render`), `Overlay`, `ReportMap`→PDF | Renders a binary doc/image (no DSS visual equivalent) | **NOT a block — collapse the ENTIRE chain into ONE Python recipe** (`reportlab`/`Pillow` → managed folder); validate by artifact+shape. **Highest-collapse (~6:1).** Block/finish decision + mechanics: tools-io-apps-ml.md § Analytic Apps |
| `Download` (binary blob: image/PDF) + `BlobConvert` | Fetches binary, not tabular | Part of the render recipe — `requests.get(url).content` written to the folder. Distinct from a CSV `Download` (migratable). Dead URLs with a shipped rendered output → recover blobs via `pypdf` — tools-io-apps-ml.md § Download |
| `FindNearest` `MaxDistanceUnits=DriveTime` | Road-network travel-time kNN | GeoRouter plugin (isochrone) or routing API; else **block**. NOT haversine — tools-spatial.md |
| `RunCommand` / `Python` tool | Shell / embedded Python | Python recipe or shell recipe |
| `Pre-SQL`/`Post-SQL Statement` | Side-effect SQL | Pre/post-run scenario step or SQL recipe |

Tell the user: *"Tools #N are Alteryx infrastructure — no recipe equivalent. Dataiku equivalents: [scenarios / dashboards / apps]."*

---

## Tool → recipe quick reference

This table is what to open first; it also routes to the leaf file documenting each tool.

| Alteryx Tool | Dataiku Recipe | Notes / leaf file |
|---|---|---|
| `TextInput` | Dataset (UploadedFiles) | Extract inline XML → CSV, upload, set-schema. tools-core.md |
| `DbFileInput`/`DbFileOutput` | Dataset | Map Alteryx ODBC → DSS SQL connection |
| `Formula` | Prepare (Formula step) | Alteryx formula → GREL; `[Field]`→bare `Field` for valid identifiers, else `val("Field")`/`numval(…)`/`strval(…)`. tools-core.md (GREL cheatsheet) |
| `AlteryxSelect` | Prepare (ColumnRenamer, ColumnsSelector, CastType) | Rename+retype+reorder+drop → always one Prepare. tools-core.md |
| `Filter` | Prepare (FilterOnCustomFormula) **or** Split | True branch only → Prepare filter. BOTH branches consumed → Split with `condition` pre-computed (cleaner than two inverse filters), or one Prepare with branching GREL. tools-core.md |
| `Sort` | Sort | |
| `Sample` | Top N | First/Last/Random/Every Nth — Top N + sort |
| `Unique` | Window+RANK=1 filter **or** Distinct | `Distinct` dedups on ALL columns — wrong if Alteryx `Unique` keys on a subset AND keeps others. Then Window: partition by keys, order by tiebreak, `ROW_NUMBER`, filter `rank==1`. tools-core.md |
| `Join` | Join | One DSS Join per consumed output (Left/Join/Right); anti-joins map directly. **3-output Join re-`Union`ed → ONE FULL OUTER join** + Prepare (`collapse-triggers.md`); FULL needs a SQL engine — **on filesystem inputs FULL fails at build → `Stack(LEFT, RIGHT_ANTI)`; FULL-anti → `Stack(LEFT_ANTI, RIGHT_ANTI)`**. Output-mapping table + mechanics: tools-join-reshape.md § Join |
| `FieldInfo` | **No recipe — schema becomes input data** | Emits one row per column (Name/Type/Size/Scale/Source/Description). Extract source column names to a 1-col CSV, upload as input. Field-list compare: `FieldInfo×2 → Formula(std name) → Join(3-out) → Union` → `2 Prepare → 1 FULL OUTER join → 1 Prepare` |
| `JoinMultiple` | **Multi-input Join** (`create-join` with N `-i`) | DSS Join takes N inputs in ONE recipe. `dku recipe create-join JN -i spine -i a -i b -i c --output-ds OUT -k spinekey -k 1:akey -k 2:bkey -k 3:ckey -P PROJ` (each `-k` after 1st targets pair index N). Cross-table key → set `joins[i].table1` to the owning table's index (`../../dku-cli/references/visual-recipe-payloads.md` § Join). tools-join-reshape.md |
| `AppendFields` (cartesian) | Join (`CROSS`) or SQL | |
| `Union` | Stack | Column-alignment modes (`UNION`/`INTERSECT`/`REMAP`): `../../dku-cli/references/visual-recipe-payloads.md` § Stack |
| `Summarize` | Group | Pass `--no-global-count` (Summarize is explicit) |
| `CrossTab` | Pivot **or restructure to skip the pivot** | ⚠ A fresh `create-pivot` fails its modality scan at build — fix with the `--value-limit` flags (`set-settings explicitValues` does NOT work): tools-join-reshape.md § CrossTab. High-cardinality headers → compute per-modality columns inline upstream |
| `Transpose` | Prepare `add-fold` (`MultiColumnFold`) **or restructure to skip** | NEVER `pd.melt`. If `add-fold` errors `FoldColumnsByName not installed`, the build is outdated (current emits stock `MultiColumnFold`). **Fold-before-clean:** when the SAME per-cell cleanup applies to every measure col, fold FIRST then ONE formula on the single value col (N→1). tools-join-reshape.md |
| `MultiRowFormula` | Prepare `val()` offset, up/down filler, or Window | Prefer Prepare `val("col", default, offset)` for prior-row refs (needs "Preserve ordering"). "Fill empty w/ previous" → up/down filler. Complex lag/lead/cumulative → Window. tools-state-parsing.md |
| `RunningTotal` | Window | Cumulative sum over partition |
| `Tile` | Window `percentRank` + Prepare bin, **or** Prepare nested-`if` | Equal-records/quantile tiles → Window `--compute 'percentRank:col:'` (no partition) then Prepare `if(pr<0.2,1,…)`. Manual/fixed-threshold tiles → just the nested `if`. See `collapse-triggers.md` "per-entity KPI scoring & segmentation" row |
| `RecordID` | **Pre-bake at extraction** (`enumerate(rows,1)`) or Window `rowNumber` | ⚠ NO `AddId` Prepare processor (`{"type":"AddId"}` throws `UnavailableTypeException` at run). Prefer baking into the file; Window `rowNumber` needs `--order-key`. tools-state-parsing.md § RecordID |
| `TextToColumns` | Prepare (`ColumnSplitter`) | `NumFields`→`limit`; delimiter→`separator`; auto-types numeric outputs as bigint |
| `RegEx` | Prepare (ExtractRegex/ReplaceRegex) | Parse→Extract; Replace→Replace; Tokenize→`ColumnSplitter` with regex separator. tools-state-parsing.md |
| `DynamicRename` | Prepare (ColumnRenamer + bulk rules) | Rename-from-a-lookup → still ONE visual Prepare: materialize the map into a static `ColumnRenamer`+`ColumnsSelector(keep)`, NOT Python. tools-state-parsing.md § DynamicRename |
| `DateTime` | Prepare (DateParser, DateFormatter) | tools-state-parsing.md + `dataiku` prepare reference |
| `GenerateRows` | **First ask WHY rows are generated** | (a) *Expand-then-join* (range join): SQL `BETWEEN` > `forRange`+`ArrayFold` then equi-Join > cross-join+Filter > Python — `create-join` is EQ/CROSS only. (b) *Expand-then-count*: no join — closed form, never expand. (c) *Expand-then-reduce, non-additive* (factorial/product): cross-join + log-sum-exp Group, no Python. Counting ≠ range join. Full shapes 1–8: tools-state-parsing.md § GenerateRows |
| `JSONParse` | Prepare (`UnfoldObject`, `ColumnSplitter`) | Flat JSON. Deep nesting → Python |
| `JSONBuild` (table → ONE JSON doc) | **Python recipe → managed folder** | DSS's only built-in JSON export is per-row JSONL — no visual recipe emits a single wrapped document. The `RecordID→Transpose→Formula→JSONBuild→Select→DbFileOutput` chain → one Python recipe: read, `json.dumps(ensure_ascii=False)`, `folder.get_writer("out.json").write(text.encode("utf-8"))`. The long-format dance is Alteryx's JSONBuild input convention — skip it. **Gotcha:** `get_dataframe(infer_with_pandas=False)` or numeric-looking text serializes as `1000000.0` (`../../dku-cli/playbooks/tabular-flow.md`). |
| `Download` | Python (live API), **or 0 recipes if rows ship as a `TextInput`** | `requests` only for a LIVE per-row fetch; bundled rows → just upload, dead URL is NOT a blocker. tools-io-apps-ml.md § Download |
| `FindReplace` | Prepare (Find and Replace, "Read replacements from a dataset") | No Python — "Advanced" mode reads the remap table from an editable dataset. Whole-word-in-text replacement → Python |
| Spatial.* (`CreatePoints`, `SpatialMatch`, `Distance`, `FindNearest`, `Buffer`, `PolyBuild`, `TradeArea`, `MapInput`, …) | **Mostly VISUAL** — `add-geopoint`/GeoJoin/`add-geodistance`/`geoBuffer` after decoding `SpatialObj` to WKT (`scripts/yxdb_read.py --spatial`) | Check `MaxDistanceUnits`/`Units` first (DriveTime = block without GeoRouter). Full tool→recipe table + Python escape hatches: tools-spatial.md |
| `PearsonCorrelation` | **Usually analysis-only → don't migrate as a recipe.** If genuinely a required output: visual sum-of-products algebra (Group no-key → Prepare), or SQL *code* recipe `CORR(COALESCE(col,0), …)` when code is acceptable | Analysis-only test + both paths + null-as-0 parity: tools-predictive-ml.md § PearsonCorrelation |

---

## Collapse triggers — running the Phase-2 collapse pass

The migration skill's "N source steps → far fewer recipes" rule requires a collapse pass after the 1:1 draft: open **`collapse-triggers.md`** and walk its table — one row per pattern (find it → collapse before showing the plan), each with the DSS collapse, the one non-obvious trick, and the ratio.

---

## Alteryx-specific gotchas

Cross-source CLI/Dataiku gotchas → `../../dku-cli/playbooks/tabular-flow.md`. Alteryx *language* gotchas (null propagation, `IF THEN ELSE`, `[_CurrentField_]`, `ToString(date, format)`) → semantics.md.

### Alteryx parsing

| Gotcha | Details |
|---|---|
| `.yxmd` is UTF-8 XML (SAS `.egp` is UTF-16) | Standard `ET.parse()` works |
| TextInput data is inline — no external file | Extract `<Data>` rows to CSV before upload |
| `BrowseV2`/`TextBox` not migratable | Skip in inventory |
| Join has THREE outputs (Left/Join/Right) | Only wire the one(s) consumed downstream |
| Field names often contain spaces | Quote in GREL: `numval("Customer ID")`/`strval("Customer ID")` — DSS rejects Alteryx `[brackets]`; GREL parser rejects backticks in `create-filter` (`../../dku-cli/playbooks/tabular-flow.md`) |
| Join/Select `<SelectConfiguration>` prunes columns; `*Unknown selected="True"` = "keep every UNLISTED column" | The listed `selected="False"` rows are DROPS, not a keep-list — branch working columns (running dates, interim `Count`, the duplicate `Right_<key>`) are pruned **at the join/select** and never reach the output. Reproduce the pruning: end with a `ColumnsSelector`/Group projection to the terminal `RecordInfo`'s exact set; don't ship every column you computed. (No "match any future column" in DSS — handle schema drift upstream.) |
| Alteryx `Null()` is the null literal | Map to GREL empty string / DSS NULL — `isnull()` in GREL |
| TextInput numerics with thousands separators (`1,234`) | Strip commas in Prepare before cast — Alteryx auto-coerces, DSS doesn't |
| digit-only column infers bigint → blanks become null | Pin to string: set-schema + re-run WITHOUT apply-schema (`../../dku-cli/references/formulas.md`) |
| Flow left all-`string` "to keep join keys clean" → a **measure** lands `string`, `column_is_numeric`/schema parity fails | String-pinning is for keys, identifiers, ID-like digits (rows above) — never measures: a join matches on the key columns, so a measure carries no join risk. Re-type every `Double`/`Int` measure from the `AlteryxSelect`/`.yxdb` schema (`set-schema`, or `infer-types --apply`) even when you string-pin the keys. |

### Source-specific verification

Column-set parity is mandatory and always runnable — doctrine and the always-derivable `columns` contract: migration `SKILL.md` (integration-test rule) + `../references/workflow.md` § Phase 4. The Alteryx contract source is the OUTPUT CONTRACT block (§ Inventory shape); parity is names **and types** — `AlteryxSelect`/`.yxdb` pin `Double`/`Int` (§ Alteryx parsing gotcha table). After the column diff, compare row count + a 3-row sample against the Alteryx result; counts differ → investigate before continuing.

Ground-truth situations:

| Situation | Rule |
|---|---|
| Solution `.yxmd` params disagree with its cached `BrowseV2` / pre-baked ground-truth `TextInput` (author edited params after capturing output) | Trust the **cached output**: read params for *what to do* (fields, renames); cached values are the validation target |
| Bare problem-statement `.yxmd` (TextInputs + TextBoxes + BrowseV2, zero transform tools) — its embedded expected-output `TextInput` may be a NON-EXHAUSTIVE sample | Validate by **containment, not equality**: `expected EXCEPT produced` = ∅; do NOT run the reverse — a correct flow legitimately finds MORE valid rows (extras at the same top score) |
| Free-form visualization workflow — input data + "analyze in any way you choose", no expected table | **BLOCK**("free-form analysis, no fixed expected output"). A workflow folder absent from the archive for this reason = this block class, not "archive gap" |
| `*_start_file.yxmd` (inputs + expected-output TextInput, no transforms) + `*_solution.yxmd` (runnable flow, own inputs) — data versions can differ, and the start file's expected output can be inconsistent with its own inputs | Extract start inputs AND its expected-output TextInput separately; confirm the output is derivable from those inputs under the solution's tool graph (hand-simulate a few rows); only then pick the input set. No shipped input set yields the table → **BLOCK**("inconsistent data; expected output not reproducible from shipped inputs"). Never migrate against a self-simulated output |

### Source-specific value-mismatch debugging

| Symptom | Likely cause |
|---|---|
| Row count mismatch | Nulls in join keys (Alteryx drops nulls on Inner join — DSS too, but double-check filters). String-vs-numeric comparisons. Unique/Distinct semantics (both hash-based, stable) |
| Value mismatch on decimals | Alteryx `Double` ≈ IEEE 754 but display-rounded to 6 digits; DSS prints full precision. Compare rounded |
| Filter matched different rows | Alteryx `Null()` returns a true null; GREL with missing inputs returns empty string by default. `isnull()` ≠ `isBlank()` |

---

## Reference map (also the tool → file router)

Seeing a tool in the quick-reference? Open the leaf file named in its "Notes" column. General routing:

| Reference | Covers / when to read |
|---|---|
| `collapse-triggers.md` | The Phase-2 collapse table — one row per chain pattern: DSS collapse + the one trick + ratio |
| `semantics.md` | *Why* a tool produces a given value — data types, null handling, formula syntax, Join's three outputs, multi-row window semantics, rounding/value-mismatch |
| `tools-core.md` | TextInput, DbFile, Formula (+GREL cheatsheet), Select, Filter, Sort, Sample, Unique |
| `tools-join-reshape.md` | Join, JoinMultiple, AppendFields, Union/Stack, Summarize, CrossTab, Transpose |
| `tools-state-parsing.md` | MultiRowFormula, RunningTotal, RecordID, TextToColumns, RegEx, DynamicRename, DateTime, GenerateRows, JSONParse |
| `tools-io-apps-ml.md` | Download, FindReplace, Macros, Dynamic Input, YXDB, Email, Excel, Apps |
| `tools-spatial.md` | All spatial: CreatePoints, SpatialMatch, Distance, FindNearest, Buffer, PolyBuild, TradeArea, coverage %, shapefile/GeoJSON readers |
| `tools-predictive-ml.md` | PearsonCorrelation, Optimization (LP/MILP/knapsack), Predictive Tools (regression/classification/clustering/ARIMA/ETS) |
| `frictions.md` | Onboarding frictions: intermediate-dataset philosophy, record counts, `*Unknown` columns, build semantics, flow layout. Read when the user pushes back on a DSS concept |
| `scripts/dump_workflow.py` | Parse `.yxmd` → tool list + connection DAG as the Phase-1 inventory skeleton |
| `scripts/extract_textinput.py` | Extract inline TextInput data → one `tool_<id>.csv` each |
| `scripts/yxdb_read.py` | `.yxdb`: list fields / dump CSV / decode SpatialObj → WKT |
| `scripts/decode_encsection.py` | Decode `<encsection>` image blobs in a `.yxdb` column → PNG |
| `../references/workflow.md` | Phase-by-phase mechanics |
| `../references/flow-collapse.md` | Graph-shape collapse (Tier-2) |
| `../../dku-cli/playbooks/tabular-flow.md` | Recipe selection, collapse mechanics, SQL engines & cross-connection landing, flow organization (zones/naming/wiki), cross-source gotchas |
| `../../dku-cli/references/formulas.md` | GREL reference + § GREL → SQL push-down |
