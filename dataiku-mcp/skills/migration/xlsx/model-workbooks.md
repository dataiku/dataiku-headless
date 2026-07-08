# Model / Formula-Engine Workbooks

Excel workbooks that are *calculation engines* — calendars, assumption sheets, formula blocks per entity, forecast/output sheets. Read `overview.md` first (triage, shared rules, parsing scripts, ingestion).

## Approach — engine, not cells

A formula workbook is a hand-unrolled program: the same calculation block copy-pasted once per entity (product, region, account), with entities in rows or blocks and time across columns. Migrate the *program*, not the unrolled copies — entities become **rows** in long format, and ONE generic set of recipes computes every block, driven by small editable catalog/assumption datasets. ~20 near-identical blocks should not become 20 recipe chains; they become one chain plus a 30-row catalog dataset.

## Model-specific rules

1. **Diff interpretations against cached values BEFORE building** (the "cached values are the contract" shared rule, applied aggressively here — what a wrong reading costs: `../references/workflow.md` § Parity reference). Export the shipped output sheet's cached values as a dataset — it is the Phase-4 parity reference.
2. **Sample each row's formula at several columns** — early-actual, late-actual, and first-forecast at minimum. Formulas routinely change along a row: literal zeros for early years, an extra `+ 'In2'!X51` term appearing mid-history, actual-vs-forecast branches, totals that include different rows in different column ranges. One formula per row is not a spec.
3. **Sheet identity is part of the series key.** The same row label often exists on several input sheets with different numbers (SAP extract vs management view). Export a `source_sheet` column and join on `(key, sheet)` — joining on the label alone fans out silently.
4. **Reshape to long *inside the flow*, with visual recipes — not a Python export script.** Target shape is one row per series × month, dates normalized to month-end. Why, the reshape toolkit, the Python-fallback conditions, and the Excel-read traps: `ingestion.md`.
5. **Single-cell knobs become project variables.** The "Actuals Up To" cutoff, scenario selector, mode switch: each becomes a project variable (`dku project set-variables -P PROJ --set date_reference=2024-03-31`) read in a Prepare/preFilter (`'${var}'` expands inside GREL). The whole actual/forecast split should derive from one variable.
6. **Mode-router sheets: export BOTH layers, switch with a variable.** A sheet of `IF(Summary!$C$1="DEFAULT", Default!X, Overlay!X)` cells is a router between assumption layers. Export both layers stacked under a `version` column (a multi-sheet excel dataset with `sheetsToColumn: true` does this with zero recipes — the sheet-name column IS the version), fill group keys down (only the first row of a merged block carries them), keep monthly-profile columns wide — the mode switch becomes a project variable + filter, not a re-export. Variable changes do NOT mark datasets stale: scenario flips need a forced recursive build.
7. **Manual math stays visual.** Hand-written least squares (`SUMPRODUCT` slope/intercept), `TREND` arrays, expanding means — all are computed-columns + Group sums + a closed-form Prepare. Two identities do the heavy lifting: Σŷ = Σy over an OLS fit window, and rolling/anchored lookups become joins. A workbook of formulas never justifies a Python recipe.
8. **No constant is a constant.** Every literal-looking bound in an engine formula — window length, window start/end, divisor, anchor month, growth base, sign — is usually an `INDEX(Assumps!…)` resolved per (entity, scenario-year). Trace every bound in a SUMIF/AVERAGEIF/INDEX to its source cell; when it lands in a catalog sheet, export it as data and JOIN it per entity-year. Hardcoding the value observed for one series/year is the dominant divergence source — it outproduces mistranslated formulas.
9. **Headers lie; consumers don't.** Classify every catalog column by the formula that READS it, never by its label — a column block headed "Seasonality Average" turned out to be the manual overlay's monthly profile (its consumer was `J × month-factor`). Name exported columns after their role in the consuming formula.
10. **Sign is part of the series contract.** The same metric can be stored positive in one block and negative in another on a single input sheet, the engine flipping per block (`=-INDEX(…)` vs `=INDEX(…)`). Scan engine pulls for a leading minus per block, carry the sign in the series catalog (never bake it into the export — exports stay faithful to source), and verify each derived ratio's SIGN against a cached cell, not just its magnitude. Residual/plug rows absorb sign errors on actuals and release them at forecast.

## Phase 1 — Parsing

> Script path and dependency conventions: `overview.md` § Phase 1.

```bash
uv run --with openpyxl python "$XLSX/scripts/dump_workbook.py" book.xlsx /tmp/xlsx_dump [SHEET ...]
```

The dump gives one line per non-empty cell: `COORD <tab> F|A|V <tab> formula-or-value [<tab> => cached]` (`A` = array formula, with its spilled range). From there:

- **Sheet roles first**: inputs (value-only wide tables), parameters (calendar, rules, assumptions), engine (dense formula sheets), outputs (sheets that only re-project engine cells), dead (empty dividers, `#REF!` named ranges, Lotus/VBA remnants — drop without inventory entries).
- **Block anatomy on engine sheets**: find the label columns, list the row labels, then for each block read every row's formula at the sampled columns (the sample-several-columns rule). Big engine sheets (30k+ cells) are worth a fan-out: one explorer per sheet, each reporting layout, representative formulas, and cross-sheet references.
- **Array formulas**: `openpyxl` returns `ArrayFormula` objects (`.text`, `.ref`). The `ref` range tells you the unit of computation — a 12-cell `{=TREND(...)}` block is one fit per calendar year evaluated across its cells, not 12 independent fits. Mis-reading array extents is the classic source of subtly-wrong seasonality/trend translations; verify against cached values (they are the contract).
- **Self-references in time**: `INDEX(21:21, …, MATCH(EOMONTH(...)))` on its own row is a T-N lookup. Telescope the recursion by hand: chains of "value 12 months ago" usually collapse to *anchor month in the last actual year* — a closed form computable with a join, no iteration.

### Inventory shape

One row per sheet-role or engine block (not per cell): block name, what it computes, inputs (sheets/ranges), actual-months source, forecast-months rule, migratable→target. Surface for sanity check when the engine has >15 blocks.

## Construct → recipe quick reference

| Excel construct | DSS target |
|---|---|
| `INDEX/MATCH` / `VLOOKUP` cross-sheet pull | Join (key columns exported with the data) |
| `SUMIF`/`AVERAGEIF`/`COUNTIF` over a date/window range | Join to window bounds + Group (window as postFilter) |
| Manual OLS (`SUMPRODUCT` slope/intercept), `TREND`, `LINEST` | computed `x·y`,`x²` cols → Group sums → Prepare closed form |
| Rolling / forward window over months | range self-join (`seq BETWEEN seq AND seq+N` via computed col) + Group — see tabular-flow.md on Window-recipe frame limits |
| `EOMONTH` date arithmetic | exact month arithmetic on ISO strings (`year*12 + month` diffs); `ROUND((d1-d2)/365*12)` ≡ month diff for month-end series |
| T-N self-row lookup (YoY chains) | anchor join on `(anchor_year, month_num)` after telescoping |
| `IF(status="Actual", …, …)` | status column from the cutoff variable; actuals and forecast as separate branches stitched by a Stack |
| Scenario selector (`SUMIF` on a name cell) | scenario column + project variable matched via computed-flag join condition |
| Mode router sheet | both layers + `version` column (mode-router rule) |
| Reconciliation / plug rows (`=LineTotal − SUM(components)`; forecast = window average of the plug) | Residual layer: components from the generic chain; residual = anchor total − Σcomponents on actuals, window-averaged per (line, scenario-year) at forecast — window from the catalog ("no constant is a constant"). Flag business-nonsensical anchors (e.g. an income line bound to a value row) as confirm-with-customer; replicate, don't "fix" |
| Per-entity copy-pasted blocks | long format + catalog dataset + one generic chain |
| Output/report sheets (wide re-projections) | drop as presentation; export cached values as the parity reference dataset |
| 12 monthly factor columns (K:V profiles) | keep wide; pick with a nested `if(month_num==1, m1, …)` in one Prepare formula |

## Collapse triggers (Excel)

- **N near-identical engine blocks** → one generic chain + catalog rows (the dominant collapse; expect blocks ÷ recipes ≫ 5).
- **Diagnostic / comparison rows** (prior-forecast deltas, `-(a/b-1)*100` checks) with no downstream consumer → drop.
- **Literal-zero histories** (rows hardcoded `0` for early columns) → a fill in the ingest Prepare (`add-fill-empty` / a `0` default), not a separate flow branch.
- **Derived totals that re-sum other blocks with sign flips** (e.g. rebates = −Σ fee lines) → tag components in the assembly map and mirror with a filtered Prepare, instead of re-computing the lines.
- Don't expect the 3–5× tool ratio of Alteryx/SAS: the unit is the *formula construct*, so a ~200-construct engine landing at 30–40 visual recipes is a good outcome. (Cross-input math does NOT need a Join→Prepare pair — the Join's payload-level `computedColumns` is post-join; `create-join --computed-col`.)

## Model-specific gotchas

| Symptom | Fix |
|---|---|
| Join on series label fans out rows silently | `(key, source_sheet)` composite key (sheet identity is part of the series key) |
| A category total disagrees only in some months | column-variant formulas — re-sample that row across column ranges |
| Trend/seasonality close but not exact | array-formula extent misread (calendar-block vs rolling); check `ArrayFormula.ref` and diff cached values |
| Engine divides by unexpected day counts | workbooks often carry several day-count sets (calendar, trading, accrual); read which Control column the engine row actually INDEXes — labels lie |
| `#N/A`-era months before inputs begin | clamp the export to the months that have input data; verify the first exported month matches the engine's first computed column |

### Verification

Coverage unit: **one series per forecast method × catalog window variant** — not per sheet family. A method you didn't verify is a method that's wrong (an uncovered method once sat 38.6% off while every covered family passed). For each covered series: the seam month (first forecast month) against `data_only=True` cached values **to full float precision** (`abs(got-exp) < |exp|·1e-9`), then sampled months across the whole horizon (e.g. Aug + Dec per year) — `scripts/diff_series.py book_dump.tsv --row 33 --dataset series_final --series UKPOS_Int` does the month sweep against a flow series and prints a signature hint. Phase 4: sweep *every* line × month of the exported output-sheet reference against the flow's outputs (quirk handling: `../references/workflow.md` § Parity reference).

**When parity diverges, diff series × month BEFORE writing a cause** — wrong-cause documentation compounds into wrong fixes. Signatures:

| Signature | Likely cause |
|---|---|
| Constant % offset from the first forecast month | wrong window/anchor — a hardcoded bound; re-trace it to its catalog cell ("no constant is a constant") |
| Magnitudes equal to full precision, sign mirrored | per-block sign convention ("sign is part of the series contract") — fix in the catalog, re-verify ratio signs |
| Exact at the seam, drift grows with horizon (often only after the first 12 forecast months) | path dependence — T-N recursion/window-roll telescoped wrong; re-derive the anchor (window-aligned month, not "year − 1") |
| Stable ratio ≈ a day-count ratio (~0.65–0.75) | wrong day-count basis (calendar vs trading vs accrual) |
| Months exact, annual totals wrong | rollup composition — missing component or plug row |

## Reference map

Shared routing lives in `overview.md`. Model-specific: per-cell parsing helper → `scripts/dump_workbook.py` · month-sweep parity diff with signature hints → `scripts/diff_series.py` · parity-reference quirk handling → `../references/workflow.md` § Parity reference.
