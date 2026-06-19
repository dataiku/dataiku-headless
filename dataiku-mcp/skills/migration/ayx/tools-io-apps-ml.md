# Alteryx IO, Apps & Macros → Dataiku

IO tools, apps, macros, dynamic input, YXDB, Excel/email output. **Spatial tools → `tools-spatial.md`. Correlation, optimization & predictive/ML → `tools-predictive-ml.md`.**

**Contents:** Download · FindReplace · Macros · Dynamic Input · YXDB files · Email/Excel/Filename output · Analytic Apps · Excel input/output.

## Download

Alteryx issues HTTP(S) per row → Python recipe (`requests`); no visual recipe for HTTP. Throttle high-volume with `time.sleep`/`ThreadPoolExecutor`; long fetches live in a scenario with retry. Visual fetch of a pinned URL → `dku recipe create-download --help`.

```python
df["response"] = df["url"].apply(lambda u: requests.get(u, timeout=30).text)
```

**Decision order — check for shipped rows BEFORE assuming Python/block:**

| Situation | Verdict |
|---|---|
| A second `TextInput` ships the full downloaded file's rows | **0 recipes, 0 Python** — extract rows to CSV, `dku dataset upload`; DSS's CSV reader does split + header-promote for free. The whole post-Download parse chain collapses to "read this CSV." |
| URL `TextInput` only, raw response NOT shipped | **Likely block.** `curl -sS -L -m 25 -w '%{http_code}'` the URL in Phase 2 FIRST — URLs rot (403/"Access Denied") and the source is time-variant. Block reason: "input referenced by external path, not shipped." |
| Dead URL on a **git host** (file renamed/moved as data grew) | **NOT a block — fetch the authoring-era snapshot by SHA.** Authoring date = the Alteryx `Filter` operand default; `curl -s "api.github.com/repos/<org>/<repo>/commits?path=<path>&per_page=100"` → latest commit on/before that date → fetch at the immutable SHA `raw.githubusercontent.com/<org>/<repo>/<SHA>/<path>`. Confirm with a distinct-key count == GT. Stage via `dku folder upload`. Residual cell diffs = source drift (archive backfill) — document, don't chase. |
| Binary-blob `Download` (image/PDF) with partially-dead URLs, but the rendered output ships | **NOT a block — recover the blobs from the shipped artifact.** `pypdf`: `for p in PdfReader(out).pages: p.images`; seed a managed folder (`dku folder upload-dir`), wire as a 2nd recipe input (`dku recipe add-input R FOLDER --type MANAGED_FOLDER`); try the live URL first, fall back to the recovered blob keyed by image number. |

"Download → Python recipe" applies ONLY to a LIVE per-row API fetch whose responses are not pre-shipped.

---

## FindReplace

Look up values in a 2nd (find, replace) input and substitute.

| Alteryx | Dataiku (preferred path first) |
|---|---|
| `FindReplace` / `DynamicReplace` (lookup-table replacement) | Prepare → **Find and Replace** processor → **Advanced: Read replacements from a dataset**. No Join/Python; target/find/replace columns map 1:1 |
| Whole-word replacement inside text | Python recipe with regex boundary |
| Exact-match join semantics (large remap / SQL push-down) | Join (left) on `value=find` + Prepare `if(isnull(replace), value, replace)` + drop helper |

`DynamicReplace` char→value (e.g. roman-numeral math) maps via Prepare FindReplace with a numeral TextInput as source; `MultiRowFormula` accumulation → Window `ROWS UNBOUNDED PRECEDING`. Fully visual.

---

## Macros

Macros consolidate tools into a reusable unit. Three flavors below.

**Macro interface questions (Date/NumericUpDown/DropDown/Boolean) → project variables**, read via `dataiku.get_custom_variables()` (Python) or `${var}` (visual/SQL). Set with `dku project set-variables PROJ --set start_date=2026-05-25`. A **no-input generator macro** maps to a no-input code recipe — `recipe create -t python` works with zero `-i` (no seed dataset; § GenerateRows case 6, `tools-state-parsing.md`).

**Encrypted `.yxmc` has no DSS equivalent and needs none** — DSS recipes are always readable. Work from TextBox annotations, validate by shape.

### Standard Macro
Sub-workflow with Input/Output tools. **App-as-recipe** (closest equivalent); **Plugin recipes** (frequent reuse, stronger UX, higher investment); **inline duplication** for 2–3 call sites.

### Batch Macro
Sub-workflow applied per row/group, outputs stacked. Data-driven splits (same schema) → **partition the dataset**; "same process, different params per batch" → **scenario-loop plugin** (`dss-plugin-scenario-loop`); "many files, varying schema" → native multi-file import + Stack.

### Iterative Macro
Loop until a condition. Pick by shape:

- **Deterministic per-step update + threshold stop → CLOSED FORM, no loop (check FIRST).** Fixed transform (×const=geometric, +const=arithmetic) looping only to cross a threshold → closed-form. Stop index `n_end = ceil(log_b(target/x0))` (geometric) or `ceil((target−x0)/step)` (arithmetic); collapse macro + wizard to **one Prepare**. GREL: `log_b(x)=ln(x)/ln(b)`, `ceil()`, `inc(parsed_date, n*step, "hours")` (**plural unit** — singular silently returns 0 rows; `formulas.md`). Seed must be `DateParser`-typed first. **Don't** route growth-until-threshold macros (cell doubling, compound interest, balance-to-zero) to scenario-loop/Python — one formula suffices.
- **Hierarchy / transitive closure / graph reachability** (walk-up-parent, descendants-of, ancestor pairs) → **one SQL recursive CTE** on any SQL connection: `WITH RECURSIVE chain AS (base SELECT … UNION ALL recursive SELECT … FROM chain JOIN base ON …) SELECT …`. Filesystem input → prepend `dku recipe create-sync -c <sql_conn>` (total 2 recipes, depth-independent). Bounded depth (≤5) **visual alt**: N chained `create-join` + `create-stack`.
  - **Multi-level BOM explosion** (effective qty = product of `Quantity` up the chain): recursive member carries a running aggregate DOWN — anchor = roots (`WHERE "Parent ID" IS NULL`) seeding `"Full Quantity"="Quantity"`; recursive = `child JOIN chain parent ON child."Parent ID"=parent."Line ID"` computing `"Full Quantity"=child."Quantity"*parent."Full Quantity"`.
  - **Float noise in a recursive product** (`0.1*6→0.6000000000000001` breaks string-match): round **only in the final SELECT** (`ROUND(x::numeric, 6)`), never inside the recursive member (compounds). PostgreSQL `ROUND(x,n)` needs `::numeric`.
  - Output may auto-create on `filesystem_managed` and still run (DSS executes the CTE on the SQL engine, streams to filesystem); pre-create on the SQL connection for a longer push-down chain. Pushing a GEO chain down: a local PostgreSQL without PostGIS rejects geopoint columns (`type "geography" does not exist`) — drop geopoints before the sync and compute distance from lon/lat in SQL.
  - Bounded-depth UNROLLING is brittle to data growth: a fixed round count **silently drops rows** if the data ever needs more rounds. Add a convergence guard (assert final leftover = 0) or prefer the loop with a generous counter bound.
- **Allocation problems** (inventory rebalancing, trade-area assignment — explicit aggregate-state termination test) → **scenario-loop plugin** with a custom condition.
- **Anything else state-based** not decomposing into a fixed-point JOIN → **Python recipe with explicit loop**, last resort.

The "no code-free equivalent" disclaimer applies only to allocation/state-based; transitive-closure has a clean SQL recursive-CTE path. **Caveat:** macros often bundle Dynamic Input/Rename — migrate the whole cluster at once.

---

## Dynamic Input

Read from a DB/file at runtime; row/parameter-driven selection.

- **Parametric SQL / export run N times** → **Dynamic Recipe Repeat** (native). Advanced tab → enable → pick a parameters dataset; runs once per row expanding `${col}`. Map columns to variable names to avoid shadowing.
  ```
  Parameters: Col1=Jan,Col2=2024 / Feb,2024 / …
  SQL body: SELECT * FROM sales WHERE month='${Col1}' AND year=${Col2}
  ```
- **"Pick the latest file by mtime"** → **Dynamic Dataset Repeat**: List Contents → `path`+`last_modified`; TopN sort desc limit 1; dataset on the folder, Advanced → Dynamic dataset repeat → **Files to include** = `${path}`.
- **Read many files from one folder** → managed folder + dataset include-regex (`tab1_.*\.csv`); `dku dataset create --type FilesInFolder`.
- **Read all Excel sheets** → native multi-sheet reader, or Excel Sheet importer plugin + Stack. **When every sheet shares ONE schema** (year-partitioned), extract + union offline into one CSV and upload — `DynamicInput ReadList(sheet)→union` collapses into the upload. Base env lacks the reader → `uv run --with openpyxl python …`.
- **Parametric SQL when Dynamic Recipe Repeat doesn't fit** (batching past query-length limits) → Python via `dataiku.core.sql`, or pre-batch the parameters dataset.

---

## YXDB files (native Alteryx binary)

DSS reads `.yxdb` natively — drop into a managed folder, create a dataset. **Caveat:** Date/DateTime fields have no timezone → DSS reads them as **strings**; set a timezone in the dataset format, or prefer a downstream Prepare `DateParser`.

**When to use:** if the user has only `.yxdb` outputs and no upstream access, consume the `.yxdb` and rebuild downstream — often simpler than replicating the upstream pipeline.

**Reading `.yxdb` offline** → `scripts/yxdb_read.py` (PyPI `yxdb`, pure Python):
- `uv run --with yxdb python scripts/yxdb_read.py file.yxdb --fields` — list fields
- `uv run --with yxdb python scripts/yxdb_read.py file.yxdb --csv out.csv [--spatial COL]` — dump CSV; `--spatial COL` decodes a SpatialObj column in-place to WKT.

**Spatial `.yxdb` (the `SpatialObj` BLOB) — DECODES, not a blocker.** The BLOB is ESRI-shapefile geometry encoding; `--spatial` decodes **Point, Polyline, Polygon** to WKT. Decode-check: a polygon/polyline BLOB length is exactly `44 + numParts*4 + numPoints*16` (mismatch = wrong offsets). After dumping, `set-schema` the geom column to `geometry` (polygon/line) or `geopoint` (point). This **lifts the "polygon `.yxdb` can't be read" blocker**: `SpatialMatch(Within/Contains)` → GeoJoin; `CreatePoints(x,y)` → `geoPoint` GREL. For value validation with no GT, recompute with `shapely` (`Point.within(polygon)`) from the same WKT. The whole "points + polygons in `.yxdb` → upload → CreateGeoPoint → GeoJoin Within → Group" flow is entirely visual post-decode.

---

## Email / Excel / Filename output

**Email** (`Email` tool → **Send email** plugin recipe; one email per input row):
- Mail channels are instance-level (no per-recipe SMTP). Dynamic Recipient/Subject/Body from columns + static fallbacks. Attachments as CSV/Excel/inline HTML; conditional formatting preserved on Excel + inline-HTML; full JINJA body templating.
- Simple "build-complete email to one recipient" → scenario `Send message` step (skip the plugin). Per-row dynamic with attachments → plugin.
- **Conditional formatting in inline HTML:** set it on the dataset in Explore; Send Message step Source=Inline, Send as HTML, attach as Excel with "Apply conditional formatting" + "embed as HTML variable" → `${datasetHtml}` in the body.

**Excel Templater** (Alteryx "write to template" → **Excel Templater** plugin recipe): input = datasets + a managed folder with the `.xlsx` template; tagged cells (default `DATASET.tablename`) get the matching dataset written at the tag's position (contents only, not headers).

**Dynamic Filename** (`report_20240415.csv`) → scenario two steps: (1) Custom Python sets `dynamic_filename_csv = f"report_{datetime.utcnow():%Y%m%d}.csv"`; (2) run the Export-to-Folder recipe with output filename `${dynamic_filename_csv}`.

---

## Analytic Apps

Alteryx `Analytic App` (desktop interactive UI) → **Project variables** + **Dataiku Applications**.
- **Project variables** referenced as `${var_name}`, set on the project, updated via UI/scenarios.
- **Applications** expose a visual form → fill values → populate variables → run a scenario; user never sees the Flow.
- **App-as-recipe** packages a whole project as a callable recipe.
- Heavy custom UI → HTML/JS in the Application layer (non-trivial). An *interactive map* app's honest analog is a webapp (Leaflet/Folium) — only when the input is runtime-interactive.

**A render/PDF deliverable is NOT automatically a block.** When a chain ends in `ReportMap`/`PortfolioComposerRender`/`Render`/`Report*`, policy is **produce the artifact** (`Pillow`/`reportlab`/`matplotlib` → managed folder) and **validate by artifact + shape** (file exists, right page/figure count, spot-check a page). **"No tabular ground truth" alone does NOT block.** The wall is the DATA, never the rendering. Block ONLY when:

| Block trigger | Detail |
|---|---|
| **Data wall: render source assets external + dead / not shipped** | `Download→BlobConvert→PortfolioComposerRender` pulling binary *images* from rotted URLs. Reason: "render source images unreachable, not shipped." |
| **Runtime input: geometry via interactive `MapInput` Draw** | Nothing reproducible offline (often paired with a drive-time/TeleAtlas wall) |
| **Output = function of a proprietary engine** | drive-time `FindNearest`/`TradeArea(Minutes)` over TeleAtlas. `FindNearest MaxDistanceUnits=DriveTime` is itself a block signal; only `Miles`/`Km` straight-line maps to GeoJoin/`geoDistance` |
| **Visual layout itself IS the answer** (tell = OUTPUT FILE TYPE) | `Formula` steps concatenating HTML/CSS strings + a `DbFileOutput` whose `<File>` ends `.htm`/`.html`/`.css`/`.pdf`/image — no PortfolioComposer node but still a rendered doc with no tabular GT. **Check the output file extension during inventory.** |

**Image-portfolio variant — same block, no map.** `TextInput(Movie,URL)→Download→BlobConvert→Sort→PortfolioComposerRender` downloads binary image blobs and composites a PDF; no row-level GT, no visual recipe for `BlobConvert`/`PortfolioComposer`. Block when the asset host is dead AND images aren't shipped AND there's no data-only deliverable. Doc/preview PNGs in the **solution** `.yxmd` are NOT source assets and don't unblock.

**Cosmetic-chrome counter-rule — a `PortfolioComposer`/`Download`-image terminal is NOT a block when the render is cosmetic chrome over a deterministic filtered table.** Ask: *is the analytical answer a row-subset that exists BEFORE the render?*
- "Whodunit geofence" (`RegEx(log)→TextToColumns→AppendFields(constant src loc)→Formula(st_distance)→Filter(dist≤R && time-window)→Download(suspect images)→PortfolioComposer`): the answer is the **filtered suspect shortlist**; the PDF only lets a human eyeball (out of scope). Front-end fully visual — `st_distance`→`add-geopoint`+`add-geodistance`, constant src lat/lon as two `add-formula` (the `AppendFields`-of-1-row cross-join = "attach a constant"), `RegEx`→`RegexpExtractor`+`add-formula`+`add-rename`, distance/time `Filter`→`add-filter-rows` (ISO `YYYY-MM-DD HH:MM:SS` compares lexically). Two traps: `add-geodistance`/`geoDistance` uses a different earth radius than `st_distance` (~0.3%) — survivor SET identical because the threshold isn't tight; **copy column names from `dku dataset get-schema`, NOT a stale terminal's `head` table** — case-sensitive, wrong-case silently extracts EMPTY groups.
- **Periodic-table archetype** (`Download(tool-icon PNGs from a dead S3 bucket)→PortfolioComposer→periodic-table`): the analytical answer is the processed metadata `.yxdb` (tool names, categories, anchor counts, macro/blocking flags) — that classification IS the answer; PNGs are cosmetic. Migrate the `Filter+Join+Summarize` against the metadata `.yxdb`, exact-match tool count per category + flags; validate by membership, not pixels. A spine-only variant migrates the metadata alone; a **full FINISH** variant ships icon PNGs as `<encsection>` blobs IN the `.yxdb` (image columns `Image`/`Anchor Image`/`Large Background`/`Icon Images`) — decode + composite (dead S3 is a red herring). Block only if the metadata `.yxdb` itself is missing.

**FINISH when images are bundled IN a yxdb as `<encsection>` blobs — they decode to PNG.** Decode with **`scripts/decode_encsection.py`**:
```
uv run --with yxdb python scripts/decode_encsection.py assets.yxdb --column "Icon Images" -o ./tiles
```
**Long-vs-short discriminator:** a yxdb column holding **long** `<encsection …PNG…>` strings → assets ARE shipped = **finish**; a column holding **short** *filenames* (join keys) → assets live at the (dead) URL = **block**. The script handles the bound trap — the blob may carry a trailing `<img src="….PNG" />` after `</encsection>`, so the base64 is bounded by the opening tag's first `>` and the **FIRST subsequent `<`** (split, not rsplit / not a greedy regex over the tail). Then `PortfolioComposer*` → Pillow render: decode each tile, composite the grid, `folder.upload_stream(...)`, validate by **artifact + shape** — no pixel diff. **Data may ship in a `.7z`** — no `7z` on stock macOS; extract with `py7zr` (`py7zr.SevenZipFile(path).extractall(dir)`).

**Counter-example — `ReportMap`/`PortfolioComposer` PDF render that IS fully migratable.** "Draw N small sketches tiled into a PDF" (`JSONParse→…→CreatePoints→ReportMap→PortfolioComposer→<name>.pdf`). When data **ships** (e.g. `.ndjson`, each record `drawing`=strokes `[[x…],[y…]]` 0–255, UTF-8-**BOM** → decode `utf-8-sig`) and render is deterministic → **ONE Pillow recipe** (`ImageDraw.line` per stroke into a grid, `save(format="PDF", save_all=True, append_images=...)`, `folder.upload_stream`, container NONE; validate by `%PDF-` + `/Type /Page` count). The canonical mapping for "render N small plots/sketches tiled into a PDF" (QuickDraw, per-row charts, contact sheets). **CLI gap:** `dku recipe create -t python -i <folder>` rejects a folder ("Input X not found") — create with `--output-folder` only, then wire the input via `dku recipe set-settings R -s '{"inputs":{"main":{"items":[{"ref":"<FOLDER_ID>","deps":[]}]}}}'`.

### Concrete parametric-app flow (the calculator archetype)

Form values in → computed result out = **3 Flow objects**: a 1-row trigger dataset → a Prepare reading `${var}` → an output dataset. The form writes variables; a scenario rebuilds; the result surfaces as a KPI.

```bash
dku dataset create app_trigger --type UploadedFiles -P PROJ
printf 'tick\n1\n' > /tmp/app_trigger.csv && dku dataset upload app_trigger /tmp/app_trigger.csv -P PROJ
dku project set-variables -P PROJ --set valeur=100 --set taux=0.2
dku recipe create-prepare app_calc -P PROJ -i app_trigger --output-ds app_result
dku recipe add-formula app_calc -P PROJ --column montant --expr '${valeur} * 1.0 * (1 + ${taux})'
```

**Type gotcha (i) — variable-driven numeric columns infer `bigint` and SILENTLY NULL decimals.** A `${var}` expanding to `100` types the column `bigint`; a later `120.5` is truncated/nulled. Fix needs **BOTH**: `* 1.0` in the formula (force float) AND `dku dataset set-schema app_result -d 'tick int, montant double'`. Chicken-and-egg: `apply-schema` alone trusts `bigint`; `set-schema double` alone gets re-inferred back on the next `* int` — the `* 1.0` makes the formula emit a decimal so `set-schema double` sticks.

**Type gotcha (ii) — result display is a KPI via a `DASHBOARD_LINK` tile, NOT an inline-rows tile.** App-designer has no "show these rows" tile; a dataset-explore tile stays blank headless. Build a KPI on `app_result`, drop it on a dashboard, link it:
```bash
dku app-designer add-tile --type DASHBOARD_LINK --dashboard <DASHBOARD_ID> -P PROJ
```
Wire form fields to write `valeur`/`taux` + a `SCENARIO_RUN` tile — payload shapes in `../../dku-cli/references/app-designer.md`.

---

## Excel input / output

**Input:** Multi-sheet → native DSS Excel import or Excel Sheet importer plugin. Cloud files → SharePoint/OneDrive/Google Drive/Sheets/Dropbox/Box plugins. Sheet name as column → native or Google Sheets plugin. Named ranges → no direct support (CSV export, or Python `openpyxl`).

**Output:** Excel export with conditional formatting → preserved from DSS Explore. Many datasets → one file → **Multisheet Excel export** plugin. Template-based / dynamic per-partition → private plugin (contact TAM) or scenario Python step. Challenge the requirement first — is Excel the deliverable, or a dashboard/email implemented as Excel because Alteryx made it easy?
