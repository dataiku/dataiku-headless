# Dataset Connectors And Filesystem Providers

Start with [Plugin development](../plugin-development.md). Choose a dataset connector
for records with a schema, or a filesystem provider to browse and read files.

## Dataset Connectors

Use `python-connectors/<component-id>/connector.json` and `connector.py`, following
[Connector and CustomDatasetWriter](https://developer.dataiku.com/latest/api-reference/python/plugin-components/custom_datasets.html).

- Derive readers from `dataiku.connector.Connector`. `get_read_schema()` returns a
  `columns` schema or `None` for inference; `generate_rows(...)` yields dictionaries
  keyed by column name.
- Make sure the returned types and schema match the descriptor. Handle pagination,
  partitions, and preview limits; avoid fetching every page for a small preview.
- Add a `CustomDatasetWriter` if the connector needs to write data. Define how it
  appends or overwrites, sends batches, finishes, and handles a failure partway through.
- Put service calls in shared helpers. Retry only when repeating the operation is
  safe, and close clients and streams even when a call fails.

Test pagination, type conversion, preview limits, and supported writes. In Dataiku,
check both the dataset preview and a full read or build.
[API Connect](https://github.com/dataiku/dss-plugin-api-connect) illustrates service
connectors, pagination, and authentication helpers.

## Filesystem Providers

Use `python-fs-providers/<component-id>/fs-provider.json` and `fs-provider.py`, following
[FSProvider](https://developer.dataiku.com/latest/api-reference/python/plugin-components/custom_fsproviders.html)
and the [descriptor reference](https://doc.dataiku.com/dss/latest/plugins/reference/fsproviders.html).

- Keep paths relative to the configured root. Handle path formats and missing objects
  consistently when listing files, reading metadata, enumerating, and streaming.
- Distinguish files from directories and return accurate sizes and modification times.
  Stream large files and close resources as the API requires.
- Advertise only operations the provider implements. Test writes and deletion on
  disposable files, including attempts to leave the configured root and partial failures.

Test nested paths, empty directories, pagination, streaming, and cleanup. Verify
browsing and actual reads in Dataiku.
[OneDrive](https://github.com/dataiku/dss-plugin-onedrive) provides provider and shared-client examples.
