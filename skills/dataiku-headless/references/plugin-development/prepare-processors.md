# Prepare Processor Plugin Components

Start with [Plugin development](../plugin-development.md).

Create `jython-processors/<component-id>/processor.json` and `processor.py` locally,
using [the processor tutorial](https://developer.dataiku.com/latest/tutorials/plugins/processor/generality/index.html)
for the descriptor and `process(row)` interface. Read configured values from `params`.
Choose CELL, ROW, or ROWS mode to match what the function returns.

If the processor needs the plugin's Python code environment, set `useKernel: true`
in `processor.json`, as described in the
[processor reference](https://doc.dataiku.com/dss/latest/plugins/reference/preparation.html).
Check runtime and library support for the target Dataiku version. Avoid repeating
expensive setup for every row.

Test output types, nulls, and changes to the number of rows. Compare the Prepare
preview with the schema and data produced by a build.
[Holidays](https://github.com/dataiku/dss-plugin-holidays) is a compact example; check
its execution engine before reusing code.
