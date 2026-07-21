# Uploaded Files Datasets

Read this reference only when the user wants to bring supplied data into a project as a new Uploaded Files dataset.

## When To Use Direct Upload

Direct upload is the exception to the Cobuild route. Use it only to create a new Uploaded Files dataset from user-supplied local data or tabular rows.

Do not use it to replace an existing dataset unless the user explicitly requests replacement. Do not use it as a general substitute for creating managed or external datasets.

## Connection Selection

Uploaded Files datasets require a file-compatible connection. Discover the exact connection name through `./dataiku-skills/connections/SKILL.md` before creating the dataset unless the user has already provided a valid connection.

Use the surrounding flow's storage context when it is clear. Otherwise, ask the user to select from compatible discovered connections.

## Transport-Specific Creation

- In `stdio` transport, use `create_upload_dataset` with a local file path visible to the MCP server process.
- In `streamable-http` transport, use `create_upload_dataset_from_rows` with ordered columns and positional tabular rows.
- The row-upload path is for tabular data only; it does not upload arbitrary binary files.

Keep `overwrite=false` unless the user explicitly authorizes replacement.

## Validation After Upload

After creation, inspect the new dataset with `get_dataset_info` and `get_dataset_profile`.

Autodetection can leave numeric, date, boolean, or categorical values as strings. If storage types need correction, inspect samples and profiles first, then route the supported schema change through Cobuild. Do not infer a storage type solely from a column name.
