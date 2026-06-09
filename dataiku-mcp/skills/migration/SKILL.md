---
name: migration
description: Migrate legacy ETL / analytics workflows to a Dataiku DSS flow. Currently routes to SAS (.sas / .egp / .flw), Alteryx (.yxmd / .yxzp / .yxdb), and Excel (.xlsx) sub-skills. Use when the user provides any of those source files or asks to convert / migrate / translate a legacy workflow.
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
  # Excel
  - xlsx migration
  - migrate xlsx
  - excel migration
  - migrate excel
  - convert excel
  - .xlsx file
metadata:
  author: dataiku
  version: "0.1.113"
  tags: migration, sas, alteryx, xlsx, visual-recipes, dataiku
---

# Migration

Migrate a legacy ETL / analytics workflow to a Dataiku DSS flow — source-agnostic frame; per-source parsing and step→recipe mapping live in the folders below. Pair with `dku-cli` (execution) and `dataiku` (platform knowledge).

## Dispatch — read the source overview as soon as you know the source

| Source | Read first |
|---|---|
| `.sas` / `.egp` / `.flw`, or SAS code (`proc …`, `data <name>;`, `%macro`) | `sas/overview.md` |
| `.yxmd` / `.yxzp` / `.yxdb`, or any Alteryx tool | `ayx/overview.md` |
| `.xlsx` workbook | `xlsx/overview.md` |

Each `<source>/overview.md` carries its own source rules, collapse triggers, and reference map.

## Five phases — mechanics in `references/workflow.md`

0. **Preflight** — auth, connection, project.
1. **Inventory** — parse sources → table (step/tool, in, out, what, migratable?). Surface for a sanity check when >20 tools.
2. **Plan** — map each step to a recipe (`../dku-cli/playbooks/tabular-flow.md` + `<source>/overview.md`), folding neighbours via `<source>/overview.md` § Collapse triggers. **Present inventory + plan, get user confirmation — the gate.**
3. **Build & verify** — one functional unit at a time: configure → `$status.ok` → `apply-schema` → run → verify (`head` + count). Parallel branches concurrently; never cascade 10+ unverified recipes.
3.5. **Flow collapse (Tier-2)** — on the *built* graph, hunt graph-shape redundancy (identical siblings, grouping fan-out, broadcast aggregate, join chains); emit the Verdict table before Phase 4. Source-agnostic: `references/flow-collapse.md`.
4. **Integration test** — flow walk-through, summary, document deviations.

## Rules (every source)

1. **Recipe altitude: Visual → SQL → Python.** SQL only for `LAG`/`ROW_NUMBER`/`PERCENTILE_CONT`/median/range-joins/multi-CTE, or a hard engine mandate. Python is the last resort, never the tidy default. A *blocked* visual recipe → reinstall the CLI or restructure the flow, not Python (state-machine & pivot decompositions: `../dku-cli/playbooks/tabular-flow.md`).
2. **One engine per flow.** SQL-source flows keep every intermediate on that connection; a mid-flow Python recipe forces all rows through DSS memory and kills push-down. A single non-translatable Prepare *step* does the same (`dku recipe status` → `Engine: DSS`) — pick SQL-translatable processors/GREL functions. SQL targets → read `../dku-cli/playbooks/tabular-flow.md` + `../dku-cli/references/prepare-processors.md`.
3. **N source steps → far fewer recipes (expect 3–5×).** Recipes encode jobs, not atomic ops — fold neighbours as you draft Phase 2 (graph-shape collapse: `references/flow-collapse.md`).
4. **Build in functional units, verify each** — row counts are cached, so `dku dataset info DS -P PROJ --recompute` after every build.
5. **Organize as you build** — clear recipe names + stage zones (`dku flow zones`/`move`) mandatory; descriptions + wiki opt-in, ask first (`ai-describe --save`). See `../dku-cli/playbooks/tabular-flow.md`.
6. **Prefer `dku` over `dataikuapi`** — drop to the API only when no verb fits; note the missing noun+verb.

Source-specific rules (DATA step ≠ Python; PROC FORMAT inlines; Alteryx tool ≠ 1:1; AlteryxSelect explicit types) live in each `<source>/overview.md`.

## Top gotchas — full catalog in `../dku-cli/playbooks/tabular-flow.md`

| Symptom | Fix |
|---|---|
| Upload auto-types all columns STRING → numeric aggregations break | `set-schema` with correct types right after upload |
| `set-schema type: date` on a CSV → every row null | Keep `string`; parse with a Prepare `DateParser` (ISO sorts chronologically) |
| **Group can't do median/percentile** (`--agg` = sum/avg/min/max/count/count_distinct/concat/stddev) | Median/quantiles → **SQL recipe** (`PERCENTILE_CONT`) or Python; never a plain Group. `sas/procs.md` |
| Group adds an extra `count` column | `--no-global-count` |
| Sampling-recipe filter silently drops the predicate | Use `dku recipe create-filter`; for visual-recipe formula filters set `uiData.mode: "CUSTOM"` |
| `apply-schema` skipped → computed columns missing | Run it before the first build |
| `int → string` lost on SQL push-down | `concat("", col)`, not `"" + col` or `toString()`. `../dku-cli/playbooks/tabular-flow.md` |
| Whole Prepare recipe falls to `Engine: DSS` on SQL data | One non-translatable step (geo/array/NLP/fold/`PythonUDF`/`Coalesce`/`TypeSetter`, or GREL `split`/`hash`/`strval`/`arrayContains`) demotes it all. `../dku-cli/references/prepare-processors.md` |
| Window gives per-row identity, not a global aggregate | Group(no key) + CROSS Join, or `--frame-unbounded`. `../dku-cli/playbooks/tabular-flow.md` |
| PROC LOGISTIC/REG/GLM landed as a Python recipe | Anti-pattern — use the `dku ml` chain (`create-prediction → set-algorithm → train → deploy`). `sas/ml-scenarios.md` |

## Reference map

**This skill** — `references/workflow.md` (phase mechanics) · `references/flow-collapse.md` (graph-shape collapse). Per-source deep refs live in each `<source>/overview.md`.

**External (read often)** — `../dku-cli/playbooks/tabular-flow.md` (pick a recipe, 4→1 collapse, CLI commands, SQL engines/push-down, flow organization, common gotchas — *mandatory* for SQL targets) · `../dku-cli/playbooks/project-ops.md` (scenarios, schedules, checks). `../dku-cli/references/`: `visual-recipe-payloads.md`, `prepare-processors.md` (incl. which steps/GREL fns keep SQL push-down), `formulas.md` (GREL).
