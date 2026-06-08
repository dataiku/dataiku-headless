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

Pair with `dku-cli` (CLI execution & platform knowledge). External skill references you'll reach for repeatedly during a migration are listed at the bottom of `references/workflow.md`.

## Dispatch

Read the source-specific overview the moment you know what you're migrating.

| Source | Read first | Then |
|---|---|---|
| `.sas`, `.egp`, `.flw`, or any SAS code (`proc …`, `data <name>;`, `%macro`) | `sas/overview.md` | `sas/translation.md`, `sas/semantics.md` |
| `.yxmd`, `.yxzp`, `.yxdb`, or any Alteryx tool reference | `ayx/overview.md` | `ayx/translation.md`, `ayx/semantics.md`, `ayx/frictions.md` |
| `.xlsx` workbook | `xlsx/overview.md` | — |

## Rules

1. **Visual → SQL → Python.** State machines decompose into a four-recipe Window-lag → Prepare-markers → Window-aggregate → Prepare-final pipeline (composite "date|prev_value" marker + max + split); see `sas/data-step.md`. Pivots/Unpivots whose only consumer re-aggregates → compute per-group aggregates *before* the reshape, the Pivot disappears. See `../dku-cli/playbooks/tabular-flow.md`.
2. **One engine per flow.** If the sources live on a SQL connection, every intermediate dataset (extracts, lookups, reference CSVs, fan-ins) must live on the same connection. A single Python recipe in the middle forces every upstream row through DSS memory and destroys push-down for the rest of the flow.
3. **Build incrementally, in functional units.** A unit is one recipe, or a small group of independent recipes that share no dependencies. Per unit: configure → check `$status.ok` → `apply-schema` → run → verify (`head` + row count). Independent branches can be built concurrently; what to avoid is cascading 10+ unverified recipes where one bad upstream silently propagates. See `../dku-cli/playbooks/tabular-flow.md` § Validate before you run.
4. **Prefer the `dku` CLI for every step.** It's composable in shell, error messages are agent-friendly, and outputs are uniform. Drop to `dataikuapi` only when no `dku` verb fits and the workaround would be heavier than ~5 lines of Python — when you do, note the noun + verb that *would have* helped so the gap can be filed later.
5. **Verify with `--recompute`.** `dku dataset info DS -P PROJ --recompute` — DSS caches row counts and does not auto-refresh after a build.

Source-specific rules (DATA step ≠ Python; PROC FORMAT inlines; Alteryx tool ≠ 1:1 recipe; AlteryxSelect explicit types; …) live in each `<source>/overview.md`.

## Plan

Phase 0–4. See `references/workflow.md`.
