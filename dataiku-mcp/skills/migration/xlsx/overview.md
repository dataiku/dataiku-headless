# Excel Migration

Source-specific entrypoint for migrating Excel workbooks (`.xlsx`, `.xlsm`, plus sibling `.csv` exports) to a DSS flow. Read the top-level `migration` SKILL.md first (cross-source rules, phases, common gotchas). Pair with `dku-cli` (execution); recipe mechanics live in `../../dku-cli/playbooks/tabular-flow.md`.

## Triage — three workbook archetypes

Decide what the workbook *is* before inventorying; the playbooks differ:

| Archetype | Tell | Read next |
|---|---|---|
| **Data table** | One sheet, one rectangular table, no formulas/pivots that matter | Not a migration — ingest it (§ Ingestion) and stop |
| **Analysis workbook** | Sheet pipeline (raw → cleaned → pivot sheets → dashboard), Power Query / M, pivot tables, charts, lookup formulas | `analysis-workbooks.md` |
| **Model / formula engine** | Calendars, assumption sheets, dense formula blocks per entity, forecast/output sheets, array formulas | `model-workbooks.md` |

Mixed workbooks exist (an engine fed by query tables): inventory once, then apply each leaf's playbook to its part.

**Redacted/anonymized workbooks** (MNDA samples): names are find-replaced and lossy — one entity may carry a different alias per sheet, labels can be mangled mid-word, and references may be rewired into nonsense (an income line bound to a value row). Trust formula topology over labels: identity is what a formula *references*, not what a cell says. Build the alias map explicitly (it becomes the series catalog), replicate nonsensical wirings faithfully, and flag them as confirm-with-customer — parity follows the workbook; sense-making follows the engagement.

## Shared rules

1. **Formulas/M are the spec; cached values are the contract.** Load the workbook twice (`openpyxl` `data_only=False` and `True`) and keep both. Diff any ambiguous interpretation against the cached values of the cells it replaces; shipped output/pivot sheets' cached values are the Phase-4 parity reference.
2. **Upload the workbook itself — never round-trip through CSV.** DSS reads `.xlsx` natively (`formatType: excel`): typed cells survive, dates stay dates, no charset/quoting layer. CSV round-trips reintroduce every classic trap (string-typed everything, date ambiguity, encoding).
3. **The used range lies.** DSS reads the sheet's used range, not the Table (ListObject) ref: stale formatting leaves phantom all-null rows below the table and junk columns to the right. The Table ref from the inventory is the row-count contract; guard with a blank-row filter and compare counts.
4. **Formatted value ≠ stored value.** Display formats round decimals, render `0.2` as `20%`, shorten dates to `1/3/14`. DSS reads *stored* values (full precision). Validate against stored values; expect user-visible "mismatches" that are formatting, not data.

## Phase 1 — Parsing the source

> Scripts are relative to this skill's `xlsx/` folder; anchor with `XLSX=/path/to/migration/xlsx`. `openpyxl` is the only dependency (`uv run --with openpyxl python …`).

Two complementary dumps — run anatomy first, cells only where formulas live:

| Script | What it gives | When |
|---|---|---|
| `scripts/dump_anatomy.py book.xlsx` | Structure inventory: per-sheet dims, tables + refs, **pivot definitions** (rows/cols/filters/aggs + source), charts + series, distinct formula shapes with counts, merged ranges, defined names, connections, **embedded Power Query M source**. `--schema "Sheet"` emits a ready DSS schema JSON (typed from stored cells, clamped to header extent) | Always — the inventory skeleton; sufficient alone for analysis workbooks |
| `scripts/dump_workbook.py book.xlsx /tmp/dump [SHEET …]` | Per-cell dump `COORD F\|A\|V formula [=> cached]` (array formulas with spilled ranges) | Engine/formula sheets — block anatomy, formula sampling, array extents |
| `scripts/diff_series.py dump.tsv --row N --dataset DS --series ID` | Month-by-month parity diff: a workbook engine row (located via its date row) vs a flow series via `dku dataset download`, with a divergence-signature hint (constant offset → wrong window; sign mirror → block sign; seam-exact drift → path dependence) | Phase 3/4 verification — one series per forecast method (see `model-workbooks.md` § Verification) |

Anatomy facts the scripts already handle (don't re-derive): `.xlsx` is a ZIP; M code lives in `customXml/item*.xml` → `<DataMashup>` base64 → MS-QDEFF container `[version:4][len:4][package ZIP]` → `Formulas/Section1.m` — the customXml part is usually **UTF-16** and the package ZIP must be sliced by declared length. `xl/connections.xml` lists external sources. Pivot definitions come from `openpyxl` `ws._pivots`.

## Ingestion — native Excel format

```bash
# One step: create + upload + target the data sheet + typed schema
dku dataset create-from-file book book.xlsx --sheet "Cleaned & Formatted Data" -P PROJ
dku dataset head book -P PROJ -n 3                 # verify by DATA, not by info row count
```

Autodetect reads the FIRST sheet — in analysis workbooks usually a doc/dashboard sheet (garbage `col_0…` schema). `--sheet` (exact name) / `--sheet-indices` (0-based) / `--all-sheets`, plus `--sheets-to-column` (sheet-name tag column), exist on both `upload` and `create-from-file` — they retarget `formatParams.sheets`, re-assert `parseHeaderRow`, and re-infer a typed schema for the *selected* sheet(s). After hand-editing format params yourself, re-infer columns with `dku dataset detect --keep-format --infer-types --save` (plain `detect --save` re-detects the format and snaps back to the first sheet).

Two cases still want the manual path (`set-definition --deep-merge` + an explicit schema from `dump_anatomy.py --schema`): clamping used-range junk columns (detection returns ALL used-range columns — 200+ on polluted sheets), and any sheet where inferred types disagree with stored cell types.

Format params that matter (`formatType: excel`):

| Param | Values / behavior |
|---|---|
| `sheetSelectionMode` + `sheets` | `NAMES` + `"*Sheet Name"` (single sheet — the `*` prefix is mandatory serialization, exact name after it; a non-matching name silently falls back to another sheet). `INDICES` + `"0,2"` / `"1-"` (**0-based**, despite 1-based examples in the product docs). `ALL` |
| `sheetsToColumn: true` | Multi-sheet append prepends the sheet name as the **first** column — native replacement for per-sheet-query + append + tag-column |
| `parseHeaderRow`, `skipRowsBeforeHeader`, `skipRowsAfterHeader` | Title rows above headers → `skipRowsBeforeHeader: N`; M `Table.Skip(n)` + `PromoteHeaders` maps here, not to a Prepare |
| `preserveNumberFormatting` | **Keep `false`.** `true` renders numerics with display formatting (thousands separators) — a `bigint`/`double` schema then reads every cell null |
| Cell range | The UI supports `Sheet!A1:D10` range clamping; not probed via API — use a blank-row guard instead (rule 3) |

Multi-sheet caveat: sheets are unioned **positionally** against the single schema — a different-layout sheet silently lands values in wrong columns. Only union same-layout sheets. Multi-file: N same-format files uploaded into one UploadedFiles dataset append automatically (no filename column); when the filename IS data (Power Query `Source.Name`), use per-file datasets + `create-stack --origin-column`.

**Date columns**: uniformly date-typed → schema type `date` directly (the opposite of the CSV rule — typed cells parse). Schema `date` does NOT serial-convert numeric cells, and real-world columns mix datetimes/serials/text — those stay `string` and branch-parse by **render class** (full table + GREL in `analysis-workbooks.md` § Mixed/dirty date columns).

## Reference map

| Reference | Covers |
|---|---|
| `analysis-workbooks.md` | Implicit-DAG recovery (M > pivots > formulas > sheet diffing), M→DSS + formula→DSS tables, dedup/order semantics, hand-authored-column doctrine, collapse triggers, gotchas |
| `model-workbooks.md` | Engine-not-cells doctrine, formula sampling, array extents, construct→recipe table, catalog-dataset collapse, parity verification |
| `scripts/dump_anatomy.py` | Structure/pivots/M inventory + `--schema` emitter |
| `scripts/dump_workbook.py` | Per-cell formula/cached dump for engine sheets |
| `scripts/diff_series.py` | Month-sweep parity diff (workbook row vs flow series) + divergence-signature hints |
| `../references/workflow.md` | Phase mechanics (cross-source) |
| `../references/flow-collapse.md` | Graph-shape collapse (Tier-2) |
| `../../dku-cli/playbooks/tabular-flow.md` | Recipe selection, CLI commands, SQL push-down, flow organization |
| `../../dku-cli/references/` | `prepare-processors.md`, `formulas.md` (GREL), `visual-recipe-payloads.md`, `dashboards.md` |
