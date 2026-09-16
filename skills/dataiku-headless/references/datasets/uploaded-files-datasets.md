# Uploaded Files Datasets

Read this reference only when the user wants to bring supplied data into a project as a new Uploaded Files dataset.

This reference covers the generic upload surface only. Excel ingest configuration — sheet selection, header offset, number-format behavior, identifier typing, and splitting one workbook into several datasets — is owned by [Ingest and Reshape Traps](../migrations/sources/excel/guides/build.md#ingest-and-reshape-traps).

## When To Use Direct Upload

Direct upload is the exception to the Cobuild route. Use it only to create a new Uploaded Files dataset from user-supplied local data or tabular rows.

Do not use it to replace an existing dataset. Use a new name or, to re-use a name, first delete the existing dataset through Cobuild. Do not use it as a general substitute for creating managed or external datasets.

## Connection Selection

Uploaded Files datasets require a file-compatible connection. Discover the exact connection name through `../connections.md` before creating the dataset unless the user has already provided a valid connection.

Use the surrounding flow's storage context when it is clear. Otherwise, ask the user to select from compatible discovered connections.

## Creation

In stdio, use `create_upload_dataset` with a local file path visible to the MCP
server process. In Streamable HTTP, pass `columns` and `rows` directly instead; the
server accepts at most 10,000 rows and never reads a host-local path.

## Validation After Upload

After creation, inspect the new dataset with `get_dataset_info` and `get_dataset_profile`.

Autodetection can leave numeric, date, boolean, or categorical values as strings. If storage types need correction, inspect samples and profiles first, then route the supported schema change through Cobuild. Do not infer a storage type solely from a column name.
