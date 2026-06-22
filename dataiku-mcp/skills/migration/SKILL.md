---
name: migration
description: Migrate legacy ETL / analytics workflows to a Dataiku DSS flow. Currently routes to SAS (.sas / .egp / .flw), Alteryx (.yxmd / .yxzp / .yxdb), KNIME (.knwf / .knar), and Excel (.xlsx) sub-skills. Use when the user provides any of those source files or asks to convert / migrate / translate a legacy workflow.
triggers:
  # SAS
  - sas migration
  - migrate sas
  - convert sas
  - translate sas
  - .sas file
  - .egp file
  - .flw file
  - proc sql
  - data step
  - proc format
  # Alteryx
  - alteryx migration
  - migrate alteryx
  - convert alteryx
  - translate alteryx
  - .yxmd file
  - .yxzp file
  - yxmd
  - alteryx workflow
  # KNIME
  - knime migration
  - migrate knime
  - convert knime
  - translate knime
  - .knwf file
  - .knar file
  - knwf
  - knime workflow
  # Excel
  - xlsx migration
  - migrate xlsx
  - excel migration
  - migrate excel
  - convert excel
  - .xlsx file
  - .xlsm file
  - power query
  - migrate workbook
  - migrate spreadsheet
metadata:
  author: dataiku
  version: "0.1.115"
  tags: migration, sas, alteryx, knime, xlsx, visual-recipes, dataiku
---

# Migration

Migrate a legacy ETL / analytics workflow to a Dataiku DSS flow — source-agnostic frame; per-source parsing and step→recipe mapping live in the folders below. Pair with the `dku-cli` skill (capability choice + execution).

## Dispatch — read the source overview as soon as you know the source

| Source | Read first |
|---|---|
| `.sas` / `.egp` / `.flw`, or SAS code (`proc …`, `data <name>;`, `%macro`) | `sas/overview.md` |
| `.yxmd` / `.yxzp` / `.yxdb`, or any Alteryx tool | `ayx/overview.md` |
| `.knwf` / `.knar`, a `workflow.knime` directory, or any KNIME node | `knime/overview.md` |
| `.xlsx` / `.xlsm` workbook — analysis sheets, Power Query / M, pivot tables, or a formula engine | `xlsx/overview.md` |

Each `<source>/overview.md` carries its own source rules, collapse triggers, and reference map.

## Five phases — mechanics in `references/workflow.md`

0. **Preflight** — auth, connection, project.
1. **Inventory** — parse sources → table (step/tool, in, out, what, migratable?). Surface for a sanity check when >20 tools.
2. **Plan** — map each step to a recipe (`../dku-cli/playbooks/tabular-flow.md` + `<source>/overview.md`), folding neighbours via `<source>/overview.md` § Collapse triggers. **Present inventory + plan, get user confirmation — the gate. If no user can respond (unattended/benchmark/scheduled run), print the plan and continue to Phase 3 immediately — never end the turn on a question.**
3. **Build & verify** — one functional unit at a time: configure → `$status.ok` → `apply-schema` → run → verify (`head` + count). Parallel branches concurrently; never cascade 10+ unverified recipes.
3.5. **Flow collapse (Tier-2)** — on the *built* graph, hunt graph-shape redundancy (identical siblings, grouping fan-out, broadcast aggregate, join chains, consecutive/empty Prepares); emit the Verdict table before Phase 4. Source-agnostic: `references/flow-collapse.md`.
4. **Integration test** — finish gate first (`dku project audit -P PROJ` — one verdict over orphans, descriptions, wiki, built outputs; add `--contract @file.json` to sweep a Phase-1 parity reference), then flow walk-through, summary, document deviations.

## Rules (every source)

1. **Recipe altitude: Visual → SQL → Python.** SQL only for `LAG`/`ROW_NUMBER`/`PERCENTILE_CONT`/median/range-joins/multi-CTE, or a hard engine mandate. Python is the last resort, never the tidy default. A *blocked* visual recipe → reinstall the CLI or restructure the flow, not Python (state-machine & pivot decompositions: `../dku-cli/playbooks/tabular-flow.md`).
2. **One engine per flow.** SQL-source flows keep every intermediate on that connection; a mid-flow Python recipe forces all rows through DSS memory and kills push-down. A single non-translatable Prepare *step* does the same (`dku recipe status` → `Engine: DSS`) — pick SQL-translatable processors/GREL functions. SQL targets → read `../dku-cli/playbooks/tabular-flow.md` + `../dku-cli/references/formulas.md` § GREL → SQL push-down.
3. **N source steps → far fewer recipes (expect 3–5×).** Recipes encode jobs, not atomic ops — fold neighbours as you draft Phase 2 (graph-shape collapse: `references/flow-collapse.md`).
4. **Build in functional units, verify each** — row counts are cached, so `dku dataset info DS -P PROJ --recompute` after every build.
5. **Organize as you build, document as you go** — all mandatory unless the user opts out: clear recipe names; stage zones (`dku flow create-zone`/`zones`/`move`) with a zone `--short-desc` (shown on the flow UI); a hand-written one-liner on every dataset *and* recipe (`set-metadata --short-desc` / `recipe set-description`); and at least one wiki article. Descriptions follow the project's working language. See `../dku-cli/playbooks/tabular-flow.md`.
6. **Prefer `dku` over `dataikuapi`** — drop to the API only when no verb fits; note the missing noun+verb.
7. **Migrate the logic, not the cells.** A source can be *transcribed* — reproduce its cached *output* values cell-for-cell — or *logic-migrated* — rebuild the computation from the real *inputs* as reusable, re-runnable recipes. Transcription is a frozen photograph: it breaks the moment an input changes and can never re-run, switch scenario, or extend a horizon. **Default to logic-migration — it is the deliverable.** The tell-tale of accidental transcription is a recipe that reads the source's cached *output* (a join back to an output sheet's values) to produce the flow's output — that line is a screenshot, not a migration; rebuild it from inputs. Cached outputs are the *parity reference* (`references/workflow.md` Phase 1), never an *input*. Excel formula engines tempt this hardest — cached cells are right there: `xlsx/model-workbooks.md` § Approach.
8. **Surface what you can't derive — before you build, not after.** The Phase-2 gate is not just "is the plan right," it is "here is what I genuinely cannot know from the source." Triage every non-obvious construct: **derivable** (a function of inputs → migrate), **hand-authored** (manual overrides, hand-keyed reference data, values pasted from upstream → preserve source values, document, never re-derive), **needs-human-input** (provenance, redaction artifacts, contradictory config, business-nonsensical wiring → ask). Present the doubts and open questions explicitly and get answers before building. An honest "I can't know X without you" beats a confident wrong build that gets torn down.

Source-specific rules (DATA step ≠ Python; PROC FORMAT inlines; Alteryx tool ≠ 1:1; AlteryxSelect explicit types) live in each `<source>/overview.md`.

## Top gotchas — full catalog in `../dku-cli/playbooks/tabular-flow.md`

| Symptom | Fix |
|---|---|
| Upload auto-types all columns STRING → numeric aggregations break | `dku dataset infer-types DS --apply` right after upload (re-infers numeric/boolean from data; identifiers and dates stay string) |
| `set-schema type: date` on a CSV → every row null | Keep `string`; parse with a Prepare `DateParser` (ISO sorts chronologically) |
| Source output is date-ONLY but the DSS date column renders `… 00:00:00` → every row fails exact-match parity | Finish with `DateFormatter` → string `yyyy-MM-dd`. `ayx/tools-core.md` § Date RENDERING parity |
| FULL outer join fails at build on filesystem/uploaded inputs (engine cascade) | Build FULL as `Stack(LEFT, RIGHT_ANTI)`; FULL-anti as `Stack(LEFT_ANTI, RIGHT_ANTI)`. `ayx/tools-join-reshape.md` § Join |
| **Group can't do median/percentile** (`--agg` = sum/avg/min/max/count/count_distinct/concat/stddev) | Median/quantiles → **SQL recipe** (`PERCENTILE_CONT`) or Python; never a plain Group. `sas/procs.md` |
| Group adds an extra `count` column | `--no-global-count` |
| Sampling-recipe filter silently drops the predicate | Use `dku recipe create-filter`; for visual-recipe formula filters set `uiData.mode: "CUSTOM"` |
| `apply-schema` skipped → computed columns missing | Run it before the first build |
| `int → string` lost on SQL push-down | `concat("", col)`, not `"" + col` or `toString()`. `../dku-cli/playbooks/tabular-flow.md` |
| Whole Prepare recipe falls to `Engine: DSS` on SQL data | One non-translatable step (geo/array/NLP/fold/`PythonUDF`/`Coalesce`/`TypeSetter`, or GREL `split`/`hash`/`strval`/`arrayContains`) demotes it all. `../dku-cli/references/formulas.md` § GREL → SQL push-down |
| Window gives per-row identity, not a global aggregate | Group(no key) + CROSS Join, or `--frame-unbounded`. `../dku-cli/playbooks/tabular-flow.md` |
| PROC LOGISTIC/REG/GLM landed as a Python recipe | Anti-pattern — use the `dku ml` chain (`create-prediction → set-algorithm → train → deploy`). `sas/ml-scenarios.md` |

## Reference map

**This skill** — `references/workflow.md` (phase mechanics) · `references/flow-collapse.md` (graph-shape collapse). Per-source deep refs live in each `<source>/overview.md`.

**External (read often)** — `../dku-cli/playbooks/tabular-flow.md` (pick a recipe, 4→1 collapse, CLI commands, SQL engines/push-down, flow organization, common gotchas — *mandatory* for SQL targets) · `../dku-cli/playbooks/project-ops.md` (scenarios, schedules, checks). `../dku-cli/references/`: `visual-recipe-payloads.md`, `prepare-processors.md`, `formulas.md` (GREL, incl. § GREL → SQL push-down).
