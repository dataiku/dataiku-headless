# File Format Plugin Components

Start with [Plugin development](../plugin-development.md).

Use `python-formats/<component-id>/format.json` and `format.py` to read or write a
file format regardless of which connector supplies the file. Follow the [format reference](https://doc.dataiku.com/dss/latest/plugins/reference/file-format.html)
and [Formatter APIs](https://developer.dataiku.com/latest/api-reference/python/plugin-components/custom_formats.html).

Make schema discovery, row reading, and end-of-file handling agree. Add an output
formatter if export is needed. Use small test files to check schemas, encodings,
nulls, empty or truncated input, and round-trips where supported. In Dataiku, verify
format selection, preview, and a full import.
[SAS Format](https://github.com/dataiku/dss-plugin-sas-format) illustrates parsing
helpers and fixture-based tests.
