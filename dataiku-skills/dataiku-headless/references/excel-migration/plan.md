# Plan

Read this when inspecting a workbook bundle and writing the three phase plans. Return to [Excel Migration](../excel-migration.md) for the operating contract.

## Phase 1: Plan

Purpose: inspect the complete source bundle, recover its business contract, and write the plans used by later phases.

1. Resolve the source bundle path. Create `<bundle_dir>/migration_v<n>/`, where `<n>` starts at `1` and increases if present.
2. Inspect the bundle before DSS planning. Always read [Reading Workbooks](./reading-workbooks.md) to classify the workbook and recover its DAG. Then read by condition:
   - Typed, formatted, dated, or identifier-bearing cells in scope, or VBA, Solver, slicers, or external connections present → [Excel Semantics](./excel-semantics.md).
   - Workbook classified as a model or forecast workbook → [Model Workbooks](./reading-workbooks.md#model-workbooks).
   - Planning how workbook tables enter DSS → [Ingest and Reshape Traps](./build.md#ingest-and-reshape-traps).
   - An expected output, cached pivot, or other parity anchor exists → [Validate](./validate.md).
3. Write `<bundle_dir>/migration_v<n>/migration_plan.md`. Include:
   - Business intent and a manifest of every workbook root, shared intermediate, and cross-file dependency.
   - Every query, formula block, engine block, true input leaf, and requested deliverable.
   - Ordered output columns and types, plus the full parity reference or strongest available parity anchor.
   - Named cells, prompts, modes, scenarios, and other interface inputs that must remain configurable.
   - Source logic dispatch across flow transformations, scenarios, checks, reporters, and analyst-facing surfaces.
   - Source-step to DSS-object mapping, with a named reason for every separation retained under the entry's collapse principle.
   - Time semantics. `TODAY()` and `NOW()` remain `now()` in delivery; use a temporary as-of pin for historical parity, then restore and re-verify live behavior.
4. Write `<bundle_dir>/migration_v<n>/validation_plan.md`. Name the parity tier and reference, the chosen verdict path and why (see [Validate](./validate.md#parity-mechanism)), behavioral probes for parameterized logic, the temporary time pin and restore step when needed, requested surfaces, and documented deviations.
5. Write `<bundle_dir>/migration_v<n>/documentation_and_cleanup_plan.md`. Cover the project's short and long descriptions; one-line descriptions for each zone, dataset, and recipe; stage- or area-based Flow Zones with no default-zone members; Wiki evidence; blocked items; surviving assets; and migration-created cleanup candidates.
6. If the workbook has more than 20 source steps or unresolved `needs-human-input` questions, pause and surface the inventory, plans, and open questions. Otherwise print the plans and continue; unattended runs never stop.

## Gap Resolution

Classify non-obvious constructs as `derivable`, `hand-authored`, or `needs-human-input`. Carry unresolved items in the migration plan and surface them at the conditional gate.

## Before the First Build Turn

Read [Build and Cleanup](./build.md) before opening `../cobuild.md` and before sending the first build turn. `../cobuild.md` is the delegation mechanism, not the migration's build rules, and it does not link back here. Build and Cleanup carries the ingest configuration and project-variable rules that must be correct on the first turn rather than repaired after it.
