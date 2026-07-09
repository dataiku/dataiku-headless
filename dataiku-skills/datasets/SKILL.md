---
name: datasets
description: Inspect and maintain Dataiku datasets through MCP tools. Use when an agent must create or upload datasets, list datasets, inspect samples/info/metrics, propagate schema, or delete datasets with explicit user intent.
---

# Dataset Operations

Use Dataiku MCP tools for dataset inspection and controlled maintenance in a project.

## Follow This Execution Pattern

1. Use `get_flow_items_in_traversal_order` to understand flow order and downstream impact before dataset changes.
2. Use `get_dataset_info` to get schema and storage details for any dataset before inspecting or mutating it.
3. Use `list_datasets` for project-level dataset discovery, exact dataset names, and storage connections.
4. When exploring a dataset's content, default to `get_dataset_profile` — it returns null rates, value frequencies, and distributions and is the right tool for most dataset analysis. Follow with `get_dataset_sample` only when you additionally need raw value formats (date patterns, text structure, delimiters) that the profile doesn't capture. Use `get_dataset_metrics` to retrieve Dataiku-computed metrics attached to the dataset object.
5. For delete, require explicit user confirmation before calling `delete_dataset`.
6. Use `propagate_schema` when downstream flow needs schema refresh after changes.

## Creating New Managed Datasets

Use this section when the user explicitly wants a new managed dataset, or when another workflow needs a missing dataset created first.

- Use an explicitly requested connection when the user provides one.
- Otherwise prefer the same connection as adjacent managed datasets when `list_datasets` or `get_dataset_info` shows a clear match.
- Use the configured default connection only when there is no stronger context signal.
- Use the `connections` skill only as supporting context for discovery or inspection when you need to validate candidate connection names or capabilities.
- Use `create_managed_dataset` to create the new managed dataset.

### Creating New Uploaded Files Datasets
- In `stdio` transport, use `create_upload_dataset` to seed a project from a local file path visible to the MCP server process. The required `connection` must be a filesystem-type connection (Filesystem, EC2, GCS, Azure, HDFS, FTP, or SSH).
- In `streamable-http` transport, use `create_upload_dataset_from_rows` for tabular uploads. Provide ordered `columns` plus positional `rows`; upload all rows in one call. This tool is for tabular data, not arbitrary binary file transport.
- Immediately after, call `get_dataset_profile` to check auto-detected column types and values.
- Autodetection may leave columns as strings; fix with `set_dataset_column_storage_types`. Pass a JSON object mapping column names to type strings, e.g. `{"amount": "double", "date": "dateonly"}`. Valid types: 'tinyint', 'smallint', 'int', 'bigint', 'float', 'double', 'boolean', 'string', 'date', 'dateonly', 'datetimenotz', 'geopoint', 'geometry', 'array', 'map', 'object'. Values that don't conform to the new storage type become null.

## Column Descriptions

Column descriptions live in the dataset schema as each column's `comment` field.

- `set_dataset_column_descriptions` accepts `descriptions_by_column` as a JSON object mapping column names to description strings, for example `{"customer_id": "Unique customer identifier", "customer_name": ""}`.
- Omitted columns are preserved unchanged.
- Unknown column names fail the request before any schema write.
- Use an empty string to clear a column description.

## Column Storage Types

- Use `set_dataset_column_storage_types` only on Uploaded Files input datasets or outputs of `shaker` (prepare) recipes.
- Pass a JSON object mapping column names to type strings, e.g. `{"amount": "double", "date": "dateonly"}`. Valid types: 'tinyint', 'smallint', 'int', 'bigint', 'float', 'double', 'boolean', 'string', 'date', 'dateonly', 'datetimenotz', 'geopoint', 'geometry', 'array', 'map', 'object'. Values that don't conform to the new storage type become null.

## AI Metadata Generation

Use `generate_dataset_metadata` with `save_description=false` to generate AI-powered dataset and column-description suggestions for review. Show the suggestions to the user and ask whether to keep them. If approved, apply dataset-level fields with `set_flow_object_metadata` and column descriptions with `set_dataset_column_descriptions`; if not approved, make no changes.

## Analytical Lens

When inspecting a dataset, go beyond confirming it exists. Surface what matters.

**Schema signals:**
- Column types that look wrong — strings that should be numeric, timestamps stored as text, booleans encoded as integers.
- Column names that suggest identifiers, surrogate keys, or row numbers — these are rarely useful as model features and often cause leakage.
- Cryptic or encoded column names worth clarifying with the user before downstream work.

**Distribution signals** (from `get_dataset_profile`):
- High null rates on important-looking columns — ask whether nulls are structural (always missing by design) or accidental (data quality issue).
- Unexpected value ranges or obvious outliers — flag them and ask whether they're real or errors.
- Low-cardinality columns that seem suspiciously correlated with the target (potential leakage).
- High-cardinality columns that will be hard to use without preprocessing — free-text, raw URLs, unhashed IDs.
- Skewed categorical distributions — a column that's 95% one value rarely adds signal as-is.
- Rows that look like duplicates or near-duplicates.

**Size signals:**
- Very small datasets (under ~1,000 rows) — flag this if ML is the goal; small data severely limits what models can learn and how much the results can be trusted.
- Very wide datasets (many columns relative to rows) — mention the risk of overfitting if ML follows.

**Communicate findings as insights, not lists.**
Don't just enumerate observations — interpret them. "This column has 40% nulls, which needs a decision before modeling" is more useful than "nulls: 40%". Connect what you see to what it means for the user's likely next step.

## Preferred Tools

- Discover: `get_flow_items_in_traversal_order`, `list_datasets`
- Create: `create_managed_dataset`, `create_upload_dataset`, `create_upload_dataset_from_rows`
- Inspect: `get_dataset_info`, `get_dataset_profile`, `get_dataset_sample`, `get_dataset_metrics`, `get_dataset_column_descriptions`
- Storage types: `set_dataset_column_storage_types` (Uploaded Files inputs and `shaker` outputs only)
- AI descriptions: `generate_dataset_metadata`
- Column descriptions: `get_dataset_column_descriptions`, `set_dataset_column_descriptions`
- Metadata: `get_flow_object_metadata`, `set_flow_object_metadata` (use `object_type="dataset"`)
- Maintain: `propagate_schema`
- Delete: `delete_dataset`

## Safety Rules

- Keep `num_rows` small when sampling unless the user asks for more.
- Never set `overwrite=true` without explicit user intent.
- Never delete dataset data (`drop_data=true`) without explicit user intent.
