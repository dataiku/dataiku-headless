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
  version: "0.1.35"
  tags: migration, sas, alteryx, xlsx, visual-recipes, dataiku
---

# Migration

Migrate a legacy ETL / analytics workflow to a Dataiku DSS flow. This file is the source-agnostic frame: the rules and phases apply to every source. Source-specific parsing, tool/step → recipe mapping, and language semantics live in the per-source folders below.

Pair with `dku-cli` (CLI execution) and `dataiku` (platform knowledge). External skill references you'll reach for repeatedly during a migration are listed at the bottom of this file under "External skill references".

## Dispatch

Read the source-specific overview the moment you know what you're migrating.

| Source | Read first | Then |
|---|---|---|
| `.sas`, `.egp`, `.flw`, or any SAS code (`proc …`, `data <name>;`, `%macro`) | `sas/overview.md` | `sas/translation.md`, `sas/semantics.md` |
| `.yxmd`, `.yxzp`, `.yxdb`, or any Alteryx tool reference | `ayx/overview.md` | `ayx/translation.md`, `ayx/semantics.md`, `ayx/frictions.md` |
| `.xlsx` workbook | `xlsx/overview.md` | — |

## Rules (apply to every source)

1. **Visual → SQL → Python.** SQL only for `LAG`/`ROW_NUMBER`/`PERCENTILE_CONT`/range joins/multi-CTE push-down, or when an engine constraint rules visual out (customer SQL mandate, push-down perf budget, CTAS/hint/partition tuning the visual recipe doesn't expose). Python is the last resort, never the tidy default. When a visual recipe seems blocked (`FoldColumnsByName` plugin missing, `create-pivot` modality scan, **BY-group state machine ("RETAIN + first./last.") feels like a Python-only problem**, weird CLI error), the fix is reinstall-the-CLI or restructure-the-flow — not Python. State machines decompose into a four-recipe Window-lag → Prepare-markers → Window-aggregate → Prepare-final pipeline (composite "date|prev_value" marker + max + split); see `sas/data-step.md`. Pivots/Unpivots whose only consumer re-aggregates → compute per-group aggregates *before* the reshape, the Pivot disappears. See `dku-cli/references/recipe-survey.md` and `dku-cli/references/common-gotchas.md`.
2. **One engine per flow.** If the sources live on a SQL connection, every intermediate dataset (extracts, lookups, reference CSVs, fan-ins) must live on the same connection. A single Python recipe in the middle forces every upstream row through DSS memory and destroys push-down for the rest of the flow.
3. **Build incrementally, in functional units.** A unit is one recipe, or a small group of independent recipes that share no dependencies. Per unit: configure → check `$status.ok` → `apply-schema` → run → verify (`head` + row count). Independent branches can be built concurrently; what to avoid is cascading 10+ unverified recipes where one bad upstream silently propagates. See `dku-cli/references/recipe-survey.md` § Validate before you run.
4. **Prefer the `dku` CLI for every step.** It's composable in shell, error messages are agent-friendly, and outputs are uniform. Drop to `dataikuapi` only when no `dku` verb fits and the workaround would be heavier than ~5 lines of Python — when you do, note the noun + verb that *would have* helped so the gap can be filed later.
5. **Verify with `--recompute`.** `dku dataset info DS -P PROJ --recompute` — DSS caches row counts and does not auto-refresh after a build.
6. **Date columns stay STRING at ingest.** Parse with a Prepare `DateParser` step after upload; `set-schema` with `type: date` on a CSV silently nulls every row. ISO strings compare and aggregate chronologically anyway.
7. **Use `dku recipe create-filter`, not the Sampling recipe.** The Sampling filter's `uiData.expression` is silently dropped on save (DSS rewrites `uiData` to `{mode: "CUSTOM", conditions: []}`); `create-filter` builds a Prepare with `FilterOnCustomFormula` whose schema isn't mutated. See gotchas table below.
8. **Group recipe adds a `count` column by default.** Pass `--no-global-count` for PROC SQL / PROC MEANS / Alteryx Summarize parity.
9. **For `int → string` casts in a Prepare recipe pushed down to SQL, use `concat("", col)`.** `"" + col` compiles to SQL numeric addition and fails. `toString(col)` is Shaker-side and does not always survive push-down. See `dku-cli` skill's `references/sql-engines.md` § GREL → SQL push-down gotchas.
10. **Organize the flow into zones as you build.** A migrated project yields dozens of recipes and datasets — a flat flow is unreadable. Group by stage (ingest, prepare, join, aggregate, output) or functional area with `dku flow zones` / `dku flow move`. See `dku-cli/references/flow-organization.md`.
11. **Documentation: clear names mandatory; wiki + descriptions opt-in.** Clear recipe names and zones (rule 10) are non-negotiable. Per-dataset descriptions and a project wiki are heavier — ask the user first; `dku dataset ai-describe --save` and `dku project ai-describe --save` bootstrap both quickly.
12. **Use the visual recipe pipeline — collapse N recipes into 1.** Every visual recipe (Group, Window, Join, Distinct, TopN, Pivot) is internally `preFilter → computedColumns → ACTION → postFilter`. CLI shortcuts only configure the action; fold neighbouring filters and computed columns into the slots before adding a separate Prepare. See `dataiku/references/visual-recipe-payloads.md` for per-recipe schemas and the `uiData.mode` filter-mode pitfall (must be `"CUSTOM"` for formula filters, else the formula is silently ignored).
13. **N source steps → far fewer DSS recipes — expected ratio 3–5×.** Source tools encode atomic operations; DSS recipes encode jobs to be done, and most jobs fold 3–8 atomic steps into one. Apply the collapse triggers from `<source>/overview.md` § Collapse triggers *as you draft* Phase 2, not after. Print the ratio (`Source: N tools → Plan: M recipes (N/M ≈ X×)`) at the top of the plan; <2× on a >20-tool workflow warrants a re-walk or an explicit reason (fully parallel branches, output-only chain). Same recipe count as source tools = transliteration, not migration. Detailed mechanics in `references/workflow.md` § Phase 2.

Source-specific rules (DATA step ≠ Python; PROC FORMAT inlines; Alteryx tool ≠ 1:1 recipe; AlteryxSelect explicit types; …) live in each `<source>/overview.md`.

## Migration plan — source-agnostic skeleton

Every migration follows the same five phases. Bash recipes and verification mechanics in `references/workflow.md`. Source-specific parsing for Phase 1 lives in the corresponding `<source>/overview.md`.

- **Phase 0 — Preflight.** Auth, connection, project. Identical for every source.
- **Phase 1 — Extract & inventory.** Parse the source files; produce a complete inventory table (step / tool, inputs, outputs, what it does, migratable?). For complex sources (>20 tools) surface the inventory for a sanity check; for small sources roll straight into Phase 2 — the gate that matters is the one before building.
- **Phase 2 — Migration plan.** Map each migratable step to a DSS recipe using `dku-cli/references/recipe-survey.md` and `<source>/translation.md`, applying the collapse triggers from `<source>/overview.md` § Collapse triggers as you go (rule 13). Before presenting, sanity-check the collapse ratio (rule 13). Present inventory + plan together and get user confirmation before Phase 3 — this is the consequential gate.
- **Phase 3 — Build & verify.** Build incrementally per functional unit (rule 3): configure → `apply-schema` → run → verify the unit's terminal output. Independent branches can be built concurrently; cascading 10+ unverified recipes is the anti-pattern.
- **Phase 4 — Integration test.** Final flow walk-through, summary table, document deviations.

## Top common gotchas (quick reference)

Full catalog in `dku-cli/references/common-gotchas.md`. Source-specific gotchas (parsing quirks, language traps) in each `<source>/overview.md`.

| Gotcha | Fix |
|---|---|
| Upload auto-detects all columns as STRING | `set-schema` with correct types right after upload |
| `set-schema` with `type: date` on CSV → all null | Keep as `string`; parse with `DateParser` in a Prepare step |
| Sampling recipe with `uiData.expression` filter silently drops the predicate (no error, output row count = input row count) | DSS rewrites `uiData` to `{mode: "CUSTOM", conditions: []}` on save. Use `dku recipe create-filter` (Prepare + `FilterOnCustomFormula`) — that schema isn't mutated |
| Group recipe adds an extra `count` column | Pass `--no-global-count` |
| `dku dataset info` row count is stale after build | Pass `--recompute` |
| `apply-schema` required before first run | Otherwise computed columns silently missing |
| ML setup as a Python recipe in the Flow (PROC LOGISTIC / PROC REG / PROC GLM landed as `dataiku.api_client()` script) | Anti-pattern. Recipes produce data, not status. Use the `dku ml` namespace: `create-prediction → set-algorithm → train → deploy → recipe create-prediction-scoring`. See `sas/ml-scenarios.md`. |
| Window recipe doesn't produce global aggregates per row (`MEAN(col)` over the whole table → still per-row identity) | Use Group(no key) + CROSS Join + Prepare instead. See `sas/procs.md`. |
| `.sas7bdat` numeric IDs export as `1077430.0` (float) — `set-schema id:bigint` silently nulls every value, joins produce 0 rows | Cast to nullable `Int64` in pandas before `to_csv`. See `sas/overview.md` § `.sas7bdat` source tables. |

## Reference map

### Within this skill

| Reference | When to read |
|---|---|
| `references/workflow.md` | Phase-by-phase mechanics — the source-agnostic Phase 0–4 playbook |
| `sas/overview.md` | SAS-specific entrypoint — file parsing, source-specific rules, non-migratable patterns |
| `sas/translation.md` | SAS translation entrypoint and focused reference map |
| `sas/data-step.md` | DATA step, RETAIN, ARRAY, DO, SELECT/WHEN, and external file I/O |
| `sas/procs.md` | PROC mapping, SQL, transpose, univariate, formats, and stats |
| `sas/functions-formats.md` | Function mapping, GREL/SQL equivalents, rounding, and dates |
| `sas/ml-scenarios.md` | Visual ML, scheduling, checks, reporting, and scenarios |
| `sas/flow-patterns.md` | Enterprise driver scripts, passthrough extracts, fan-in/split, and parity checks |
| `sas/semantics.md` | PDV, MERGE semantics, missing values, macro patterns — read when a value disagrees |
| `ayx/overview.md` | Alteryx-specific entrypoint — file parsing, source-specific rules, non-migratable patterns |
| `ayx/translation.md` | Alteryx translation entrypoint and focused reference map |
| `ayx/tools-core.md` | TextInput, DbFile, Formula, Select, Filter, Sort, Sample, and Unique |
| `ayx/tools-join-reshape.md` | Join, JoinMultiple, AppendFields, Union, Summarize, CrossTab, and Transpose |
| `ayx/tools-state-parsing.md` | MultiRowFormula, RunningTotal, RecordID, TextToColumns, RegEx, and DateTime |
| `ayx/tools-io-apps-ml.md` | Download, FindReplace, spatial, macros, dynamic input, yxdb, email, Excel, apps, and predictive tools |
| `ayx/workflow-patterns.md` | Range joins, reroutes, component-stat chains, correlation, and recurring collapse patterns |
| `ayx/semantics.md` | Alteryx data types, null/join semantics, MultiRowFormula boundary rules |
| `ayx/frictions.md` | DSS-vs-Alteryx onboarding pushbacks (intermediate datasets, previews, layout) |
| `xlsx/overview.md` | Excel-specific entrypoint |

### External skill references (read often)

- **`dku-cli/references/recipe-survey.md`** — picking a recipe type. Decision rationale (Visual → SQL → Python), the visual-recipe pipeline-collapse pattern (4 recipes → 1), filter-mode rule, custom aggregations, `$status.ok` validation.
- **`dku-cli/references/recipe-decision.md`** — code examples + quick-reference decision tree for creating recipes via CLI. Companion to `recipe-survey.md` (rationale lens).
- **`dku-cli/references/common-gotchas.md`** — Dataiku/CLI traps that bite every `dku` user (upload→STRING, `--recompute`, `apply-schema` required, Sampling-filter trap, GREL push-down quirks).
- **`dku-cli/references/flow-organization.md`** — zones, recipe naming, wiki, dataset descriptions. Hygiene knobs that make a 30+-recipe flow readable.
- **`dku-cli/references/sql-engines.md`** — *mandatory* read whenever the target connection is SQL (Snowflake / Postgres / BigQuery / Redshift / …). Covers cross-connection landing, GREL → SQL push-down gotchas, stale-physical-table recovery. The "engine constraint" carve-out in rule 1 lives here.
- **`dku-cli/references/commands.md`** — full CLI reference with every command's flags. The skill's quick examples are abbreviated; this file is the authoritative index.
- **`dataiku/references/prepare-processors.md`** — the index of all Prepare-recipe processors with their JSON shape. You will translate dozens of source steps into Prepare-step JSON; this is the canonical reference. The Golden Rule from the file: prefer a purpose-built processor over `CreateColumnWithGREL`.
- **`dataiku/references/formulas.md`** — GREL function reference. Translating source formulas (`Formula` tools in Alteryx, DATA-step assignments in SAS, Excel formulas) is mostly "find the GREL equivalent of this function". Case-sensitive, has surprises (`toTitlecase` not `toTitleCase`).
- **`dataiku/references/scenarios.md`** — orchestrating multi-step builds. Useful when the migrated flow needs scheduled rebuilds, cross-project quality gates, or composing leaf scenarios. Read after Phase 4 when wiring the flow into automation.
