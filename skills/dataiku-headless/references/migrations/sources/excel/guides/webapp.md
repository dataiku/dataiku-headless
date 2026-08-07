# Overview Webapp

Read this when delivering the migration overview webapp. Return to [Excel](../excel.md) for the delivery contract.

Every migration delivers one STANDARD webapp named after the workbook (for example "Project Finance Overview") that lets an SME read the migrated outputs without opening the Flow: one tab per terminal dataset mirroring the source sheets, a KPI header, optional charts, and per-tab Excel export. Deliver it after validation passes and before writing the final documentation evidence.

## The Template Is the Code

Cobuild does not design or author webapp code. The webapp is the shipped template in `../webapp/`:

| File | Role |
|---|---|
| `template.html` | HTML tab, delivered verbatim |
| `template.css` | CSS tab, delivered verbatim |
| `template.js` | JavaScript tab, delivered verbatim |
| `template.py` | Python tab: a `CONFIG` dict to fill, then a fixed engine delivered verbatim |

The only authored artifact is the `CONFIG` dict at the top of `template.py`. Everything below its end marker is a tested rendering engine; changing it, "improving" it, or letting Cobuild restate it in its own words is a defect. The engine already handles missing datasets, row caps, numeric formatting, chart pivots, and Excel export.

## Filling CONFIG

Author CONFIG from the migration plan, not from imagination:

- `sheets`: one entry per terminal dataset, in source-workbook sheet order, reusing the plan's sheet-to-terminal-dataset table. `label` is the source sheet name the SME knows. Mark money and ratio columns in `column_formats` (`money`, `number`, `number2`, `percent`, `date`, `text`); unlisted columns render automatically. `total_row: True` only where the source sheet printed a totals row.
- `kpis`: 3 or 4 headline numbers the workbook itself surfaced (summary cells, dashboard figures). Supported: `agg` of `sum|mean|min|max|first|last|count` over one column with an optional single-column equality `filter`. A headline number that needs more than that comes from a small terminal dataset instead (aggregate it in the flow, then use `first`).
- `badges`: source workbook filename, and other pinned facts such as horizon or scenario variables.
- `charts`: only series the workbook plotted or an SME plainly needs; empty is valid. Types: `line`, `area`, `bar`, `stacked_bar` (requires `series` column), `horizontal_bar`, `donut`, `scatter` (`series` optional), `combo` (`y` bars plus a `y2` line on a right axis formatted by `format2`). An optional `dash` spec (`{"column": ..., "when": ...}`) draws matching rows dashed and fades their bars — the actual-versus-forecast idiom. `first`/`last` KPIs and chart ordering follow dataset row order, so point them at datasets whose order is the delivery contract.
- `currency` and `locale` come from the workbook's number formats, not defaults. `percent` expects fractions (0.12 renders as 12%). `money` renders the full value with exactly two decimals, never compacted to k/m/bn; a tab must read like its sheet.

Before the handoff, splice the filled CONFIG into `template.py` and check it parses (`python -c "import ast; ast.parse(open(...).read())"`). A syntax error found after delivery costs a Cobuild repair turn.

## Cobuild Handoff

One Cobuild turn creates and fills the webapp. The prompt must contain, in this order:

1. Create a STANDARD webapp with the chosen name, `backendEnabled: true`, `autoStartBackend: true`, libraries `["dataiku"]` (the frontend needs `getWebAppBackendUrl`, nothing else), code environment left at inherit.
2. The instruction that the four code blocks are finished, tested code to paste byte for byte — not rewritten, reformatted, or annotated.
3. All four tabs as fenced code blocks: HTML, CSS, JavaScript, Python (the filled file).
4. Start the backend; change nothing else in the project.

Never send a partial tab set, and never ask Cobuild to "build a webapp showing the outputs" without the code: an unconstrained Cobuild webapp is exactly the unreliable path this template exists to remove.

## Verify, Then Claim

Cobuild's completion report is not evidence. After the turn:

1. `get_webapp_settings` and compare each tab against the local filled files. Require equality up to leading/trailing whitespace; any other drift gets one repair turn per drifted tab: "Replace the entire <tab> tab content with exactly:" plus the block. Re-read and re-compare after repair.
2. `get_webapp_state` until the backend is running. A `ModuleNotFoundError: flask` failure means the inherited code environment lacks Flask: have Cobuild set the webapp's code environment selection to the Dataiku builtin env and restart.
3. A running backend with drift-free tabs is the delivery proof. Record the webapp id, backend state, tab-comparison verdict, and the view URL (`.../webapps/<id>_<kebab-case-name>/view`) in `<bundle_dir>/migration_v<n>/webapp_evidence.md`, and list the webapp in the documentation evidence.

The webapp reads only delivered terminal datasets. If a tab needs a dataset that validation did not cover, the sheet list is wrong — fix CONFIG, not the flow.
