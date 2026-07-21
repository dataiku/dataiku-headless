# Move an Excel workbook into DSS

Use this playbook for `.xlsx` and `.xlsm` workbooks whose formulas, queries,
pivots, or sheet-to-sheet logic must become a runnable DSS flow. A single clean
table needs native ingestion, not a reconstructed flow.

Read `../soul.md` first, use `build-via-cobuild.md` for each construction turn,
and verify each unit with `verify-cobuild-output.md`.

## 1. Inventory the workbook

Inspect the workbook locally before delegating anything. Load it twice: once with
formulas and once with cached values. Record:

- every sheet, hidden state, used range, table name and table range;
- formulas by repeated shape, cross-sheet references, and array/spill ranges;
- Power Query connections and M source when present;
- pivot sources, row/column fields, filters, and aggregations;
- charts, named ranges, macros, and hand-entered assumption blocks;
- the logical input tables and the exact ordered terminal schema.

Classify the workbook:

- **Data table:** ingest the table and stop.
- **Analysis workbook:** recover the implicit graph from Power Query, pivots,
  formulas, and sheet dependencies.
- **Formula model:** reconstruct the calculation engine from inputs and formulas;
  do not treat cached outputs as inputs.

Formulas and M define the logic. Cached output and pivot cells are parity evidence.
If a cleaned column cannot be derived consistently from its inputs, classify it as
hand-authored, preserve it as source data, and ask rather than inventing a rule.

## 2. Write the contracts

Before building, state:

- the business intent and each logical source table;
- the planned visual recipe units and their exact DSS inputs and outputs;
- the storage connection for every planned output, chosen from `list_connections`
  and confirmed working with `test_connection` — never left for Cobuild to pick;
- each unit's grain, ordered columns, types, and known source row count;
- the terminal output contract and cached-value parity reference;
- open questions, especially macros, external connections, volatile formulas, and
  ambiguous hand edits.

Use visual recipe families by default. Map lookup formulas to Join, row-local
formulas to Prepare, keyed `SUMIF`/`COUNTIF` logic to Group plus Join or Window,
append logic to Stack, deduplication to Distinct or Top N, and pivots to Group or
Pivot. A chain of Power Query steps normally becomes a small number of visual
recipes, not one recipe per M expression.

## 3. Land the workbook natively

Use the upload bootstrap once per logical dataset, even when several datasets read
the same workbook. Then ask Cobuild to select the exact sheet or sheet set, header
offset, and stored-cell schema.

Verify every landed source:

- the sample comes from the intended sheet and the header is not a data row;
- the schema matches stored cell types and excludes used-range junk columns;
- the row count matches the table range, not the sheet's often-inflated used range;
- multi-sheet unions contain only same-layout sheets and retain a sheet-origin
  column when the sheet name is business data.

Excel-specific traps:

- autodetection starts from the first sheet and may select a cover page;
- stale formatting creates phantom blank rows and columns outside the real table;
- merged cells read as a value followed by blanks and may require visual fill-down;
- displayed values are not stored values: percentages, dates, and rounded numbers
  must be checked against the stored cells;
- typed Excel dates can land as dates, while mixed date/serial/text columns need an
  explicit parsing contract;
- long numeric identifiers may already be corrupted by Excel's precision limit.

## 4. Build and verify sequentially

Delegate one functional unit at a time on the same project conversation. Name its
exact inputs, target output, visual family, grain, columns, connection, and parity
checks. For Group and Pivot units, spell out the output column order explicitly —
aggregation recipes emit their own ordering otherwise, and reordering costs an
extra turn. Do not start a dependent unit until the current one is verified.

After each unit:

- compare the exact ordered schema with `get_dataset_info`;
- use `get_dataset_profile` for fresh bounded row evidence and require
  `truncated: false` when claiming an exact count;
- spot-check values with `get_dataset_sample` against cached workbook values;
- confirm the intended nodes and edges with `get_flow_graph`;
- inspect job logs when output is unexpectedly empty or malformed.

For final parity, compare every output row and column when cached expected values
exist. Keep a mismatch dataset and data-quality rule in the flow when practical so
the proof can be rerun. With synthetic inputs, prove the exact ordered schema and
the logic's invariants instead of claiming value parity.

## 5. Finish safely

Run `audit_project` with required columns, types, and minimum rows, then independently
check exact order, width, and fresh row evidence. Ask Cobuild to complete zones,
descriptions, and a wiki explaining sources, grain decisions, workbook deviations,
and rebuild steps.

Delete only failed attempts and orphans created by this work. Inspect every
confirmation scope and follow `../references/safety-and-confirmations.md`; never
delete pre-existing assets without explicit user intent.
