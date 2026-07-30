# Ingest and Build Traps

Read this before the first build turn and when ingesting or reshaping workbook tables. Return to [Excel](./excel.md) for routing.

Uploading only lands the file: `create_upload_dataset` takes no sheet, header, number-format, or storage-type argument, and every uploaded dataset defaults to the workbook's first sheet. The Excel parse configuration is applied in the Cobuild turns that follow, and must arrive there already decided rather than reconstructed turn by turn. One workbook can produce a dozen or more ingest targets; batch them across the narrow Cobuild turns the parent's build phase prescribes.

Create every project variable before a formula references it, and rebuild the smallest affected branch after changing one; an unset `${var}` stays literal text and can silently select the wrong branch.

## Ingest and Reshape Traps

- One workbook can feed several logical datasets. Upload the workbook once, then create one Uploaded Files dataset per logical table, each re-reading that same file with its own sheet selection and header offset. One file does not mean one dataset. See [Uploaded Files Datasets](../../../datasets/uploaded-files-datasets.md) for the generic upload surface and connection choice.
- Set sheet selection, header offset, and number-format behavior explicitly for each ingest target.
- Excel ingest defaults to the first sheet unless selection is explicit. After changing sheet or format parameters, re-infer schema without re-detecting the format.
- Use explicit schema when used-range junk or inferred types disagree with stored cell types.
- Keep display-number preservation off when schema expects numbers; formatted strings can null typed columns.
- Cell-range clamping is insufficient by itself. Guard blank rows and count-match the real table.
- Append only sheets with the same layout. Multi-sheet append is positional and can add sheet name as the first column; preserve that provenance when it carries meaning.
- Preserve source filename when it is business data.
- Express title rows as header-skip ingest parameters, and fill down keys represented by merged cells.
- Month-label parsing requires explicit month-end arithmetic.
- Guard blanks explicitly instead of returning a bare formula null.
- Contract renames live in recipe configuration (Prepare or Group), never in an edited output schema; schema propagation reverts schema-level renames on the next recursive build.
- Pivot recipes generate their own output column names and omit never-observed cells. Plan a terminal Prepare per pivot for contract renames and zero-filled sparse cells.

## Query and Formula Traps

- A Power Query `let ... in` chain usually represents one preparation chain, not one flow object per line.
- Parameter-query and sample-file scaffolding can disappear only after native ingest replaces its function.

## Collapse Timing

Apply the collapse principle from [Excel](./excel.md) before documentation and cleanup, keeping the per-sheet delivery contract intact.
