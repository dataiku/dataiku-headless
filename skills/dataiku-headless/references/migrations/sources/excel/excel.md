---
name: source-excel-reference
description: "How to read an Excel bundle (.xlsx / .xlsm / .xls) and the Excel semantics needed to extract its business logic faithfully."
---

# Excel

Excel source subskill. The migration workflow, phases, and invariants live in the parent `references/migrations.md`; this directory carries what is Excel-specific.

## Source Identification

`.xlsx`, `.xlsm`, and `.xls` are source bundles. Sibling `.csv` exports are evidence only, never source of truth.

## Delivery Contract

- Minimize recipe count during planning and after build. Read [Data Prep Recipes](../../../recipes/recipe-types/data-prep-recipes.md) and fold compatible pre-filters, computed columns, the core action (including custom or global aggregations), post-filters, and output controls into one recipe unless semantics, sharing, delivery, or engine preservation requires separation.
- Collapse applies to intermediates, never to the delivery contract. Each reviewable source output (report sheet, output table, pivot) lands as its own terminal dataset carrying that sheet's column contract, so an SME can diff one source sheet against one dataset without filtering. A shared long-format spine feeding per-sheet terminals through cheap splits satisfies both rules.
- Every Excel migration delivers an SME-facing overview webapp built from the shipped template, after validation passes and before documentation and cleanup. Cobuild receives finished, locally filled code to paste verbatim — never a design brief to author webapp code from.
- Complete only after independently re-reading the final flow and outputs, checking the output contract, and finishing documentation and cleanup. Never report a partial project as completed.

## Plan Additions

- Classify the workbook and recover its DAG through [Reading Workbooks](./guides/reading-workbooks.md) before Dataiku planning. Read [Excel Semantics](./guides/excel-semantics.md) when typed, formatted, dated, or identifier-bearing cells are in scope, or when VBA, Solver, slicers, or external connections are present.
- The Migration Plan additionally includes: a manifest of every workbook root, shared intermediate, and cross-file dependency; every query, formula block, engine block, true input leaf, and requested deliverable; ordered output columns and types plus the full parity reference or strongest available parity anchor; named cells, prompts, modes, scenarios, and other interface inputs that must remain configurable; source logic dispatch across flow transformations, scenarios, checks, reporters, and analyst-facing surfaces; a source-step to Dataiku-object mapping with a named reason for every separation retained under the collapse principle; a sheet-to-terminal-dataset table naming one terminal dataset per reviewable source output (a consolidated table covering several sheets is an intermediate, not a deliverable); and the overview webapp CONFIG (see [Overview Webapp](./guides/webapp.md) for the CONFIG contract).
- The Validation Plan names the parity tier and reference, the chosen verdict path and why (see [Validate](./guides/validate.md#parity-mechanism)), behavioral probes for parameterized logic, the temporary time pin and restore step when needed, requested surfaces, and documented deviations.
- Read [Ingest and Build Traps](./guides/build.md) before the first build turn; it carries the ingest configuration that must be correct on the first turn rather than repaired after it.

## Routing

| When | Read |
|---|---|
| Identifying sources, inspecting bundle structure, recovering intent, or inventorying a model workbook or report snapshot | [Reading Workbooks](./guides/reading-workbooks.md) |
| Preserving workbook meaning or handling unavailable features | [Excel Semantics](./guides/excel-semantics.md) |
| Ingesting workbook tables or reshaping them in Dataiku | [Ingest and Build Traps](./guides/build.md) |
| Selecting a parity anchor, proving parity, or judging completion | [Validate](./guides/validate.md) |
| Delivering or repairing the overview webapp | [Overview Webapp](./guides/webapp.md) |
