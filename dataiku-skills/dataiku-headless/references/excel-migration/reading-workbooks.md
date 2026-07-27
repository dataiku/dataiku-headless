# Reading Workbooks

Read this when identifying workbook sources, inspecting bundle structure, recovering intent, or inventorying a model workbook. Return to [Excel Migration](../excel-migration.md) for routing.

## Source Identification

- `.xlsx`, `.xlsm`, and `.xls` are source bundles. Sibling `.csv` exports are evidence only, never source of truth.
- `.xls` is valid input but `openpyxl` cannot parse it. Use an alternate inventory path or one-time conversion, and keep the original as the uploaded source.
- Classify the workbook as a plain data table, analysis workbook, model workbook, or mixed workbook. Inventory mixed workbooks by logical object, not sheet count.
- Redacted labels can be misleading. Trust formula topology, keep an alias map per sheet or entity, and flag broken-but-shipped bindings for confirmation.
- Named cells, cutoff values, modes, scenarios, and router knobs are logic inputs, not incidental constants.

## Reading the Bundle

- Read formulas and M from a structural load, and parity values from a cached-value load. Output sheets and pivot caches are parity references.
- Used range is not a reliable table boundary. Prefer the ListObject ref or real header extent, guard blank rows, and count-match the table.
- A sheet can contain several tables, title rows, documentation, pivots, and outputs. Sheet is not dataset boundary.
- Pivot definitions live in workbook metadata, not rendered cells. Pivot and report sheets are validation targets, not logical inputs.
- Hidden and very-hidden sheets can feed logic; inventory them like any other sheet.
- Query-like sheet tables are often cached query outputs. Author-machine paths require a shipped-file match, cached-output fallback, or user escalation.
- Raw and cleaned sheets without formulas require a complete sheet diff.
- Sample formulas across early actuals, late actuals, and the first forecast. One cell is not a row specification.
- Literal-looking forecast constants can vary by entity, scenario, or year. Trace every bound to its source cells.
- Array formula extent is the computation unit. One spilled block is not a set of independent formulas.

## Recovering Intent

- Recover the workbook DAG in order: Power Query M, pivot definitions, formula edges, then raw-versus-clean differences.
- The Power Query M graph is the highest-fidelity workflow. `shared Query = ...` references are flow edges.
- Formula columns are derivations and cross-sheet references are flow edges.
- If cleaned values vary for the same stored value and render class, classify the column as hand-authored instead of inventing a rule. Preserve source values and validate the downstream deliverable.
- Workbook deduplication is first-row-in-sheet-order. Exact parity needs explicit ranking or a preserved row index when order matters.
- Classify catalog columns by their consuming formulas, not their headers.
- Self-row time lookups can telescope to an anchor-month closed form. Recover recurrence intent before translating syntax.

## Model Workbooks

A model workbook is a hand-unrolled program. Migrate its logic, not cached outputs or copied blocks. Inventory it by engine block or logical role, not individual cell.

- A mode-router sheet means both routed layers are source logic. Preserve the version dimension and switch through a project variable.
- Actual and forecast branches remain distinct until their source status or phase logic stitches them together.
- Reconciliation and plug rows are residual logic derived from components and anchor totals, not decorative report rows.
- Repeated per-entity blocks represent one generic engine over a catalog, not separate copied implementations.
- Keep monthly profiles wide when formulas consume a month-number selector; folding them changes the lookup contract.
