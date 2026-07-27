# Build and Cleanup

Read this when building the DSS project, ingesting workbook tables, or applying documentation and cleanup. Return to [Excel Migration](../excel-migration.md) for the operating contract.

## Phase 2: Build

Create the Dataiku project and resolve a writable target connection. Read `<bundle_dir>/migration_v<n>/migration_plan.md` and build the project through Cobuild (`../cobuild.md`).

Before issuing the first ingest instruction, apply [Ingest and Reshape Traps](#ingest-and-reshape-traps) below. Uploading only lands the file: `create_upload_dataset` takes no sheet, header, number-format, or storage-type argument, and every uploaded dataset defaults to the workbook's first sheet. The Excel parse configuration is applied in the Cobuild turns that follow, and must arrive there already decided rather than reconstructed turn by turn.

Configure ingest in several narrow turns, not one wide one. A Cobuild turn runs under a server-side time cap (see `../cobuild.md`), and one workbook can produce a dozen or more ingest targets. Send a small batch of datasets per turn, confirm the resulting columns and row counts, then send the next. A single turn covering every target risks the whole run on one timeout.

Preserve configurable workbook behavior:
- Create every referenced project variable before a formula uses it. An unset `${var}` remains literal text and can silently select the wrong branch.
- Blank is a valid live-time value. Use `if('${var}' == '', <now() path>, <pinned path>)` for a proven live/pin switch.
- After changing a variable, explicitly rebuild the smallest affected branch before reading outputs. Make that rebuild part of any surfaced scenario run path.

Apply the collapse principle from the entry before documentation and cleanup.

## Ingest and Reshape Traps

- One workbook can feed several logical datasets. Upload the workbook once, then create one Uploaded Files dataset per logical table, each re-reading that same file with its own sheet selection and header offset. One file does not mean one dataset. See [Uploaded Files Datasets](../datasets/uploaded-files-datasets.md) for the generic upload surface and connection choice.
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

## Query and Formula Traps

- A Power Query `let ... in` chain usually represents one preparation chain, not one flow object per line.
- Parameter-query and sample-file scaffolding can disappear only after native ingest replaces its function.

## Phase 4: Document and Cleanup

Read `<bundle_dir>/migration_v<n>/documentation_and_cleanup_plan.md` and apply it fully through Cobuild. Zone the Flow by stage or functional area, leaving no default-zone members. Set the project's short and long descriptions and one-line descriptions for each zone, dataset, and recipe. Re-read the saved descriptions, zones, Wiki evidence, and surviving assets; never trust the Cobuild report alone.
