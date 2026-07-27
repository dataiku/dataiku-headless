---
name: excel-migration
description: Migrate Excel workbook logic (.xlsx / .xlsm / .xls) into runnable Dataiku flows through Cobuild. Use when the user supplies an Excel source bundle and asks to migrate, rebuild, port, or recreate its logic in DSS.
---

# Excel Migration

Translate Excel workbook business logic into runnable Dataiku flows.

Apply the shared operating rules in `../SKILL.md` for routing, direct exceptions, and validation. Read the routed Excel references as needed.

Migration has four phases: plan, build, validate, and document and cleanup. Build and validate may loop until validation passes.

## Operating Contract

- Visual recipes are the default and must be searched genuinely first; code is allowed only as a documented last-resort deviation.
- Begin from the same logical source datasets at equivalent grain. Never upload a locally derived substitute for a source input, and never upload a cleaned, filtered, joined, aggregated, ranked, summarized, or final-result table as if it were a source dataset. Expected outputs may be uploaded only as parity reference datasets during validation, never wired into the delivered flow, and are deleted during cleanup.
- Produce the requested output inside DSS from migrated source datasets through Dataiku recipes.
- Minimize recipe count during planning and after build. Fold operations into native recipe slots unless semantics, sharing, delivery, or engine preservation requires separation.
- Complete only after independently re-reading the final flow and outputs, checking the output contract, and finishing documentation and cleanup. Never report a partial project as completed.

## Routing

| When | Read |
|---|---|
| Writing the migration, validation, and cleanup plans | [Plan](./excel-migration/plan.md) |
| Building the flow, ingesting workbook tables, or applying documentation and cleanup | [Build and Cleanup](./excel-migration/build.md) |
| Proving parity and completion | [Validate](./excel-migration/validate.md) |
| Identifying sources, inspecting the bundle, recovering intent, or inventorying a model workbook | [Reading Workbooks](./excel-migration/reading-workbooks.md) |
| Preserving workbook meaning or handling unavailable features | [Excel Semantics](./excel-migration/excel-semantics.md) |
