---
name: datasets
description: Understand and inspect Dataiku datasets, including their storage, schema, metadata, and quality signals. Use when an agent must inspect existing datasets, prepare a grounded Cobuild request, write a local CSV export, or create a new Uploaded Files dataset from user-supplied data.
---

# Datasets

Use this guide to understand, inspect, and locally export Dataiku datasets, gather context for Cobuild, and handle the direct Uploaded Files creation exception.

## Dataset Concepts

A dataset is a project-level representation of data. Its type and connection determine where data lives, who manages its lifecycle, and which operations are available.

- **Managed datasets** are created and stored under Dataiku-managed lifecycle in a selected connection.
- **External or unmanaged datasets** point to data that already exists in an external system; the external system remains responsible for the underlying data lifecycle.
- **Uploaded Files datasets** store user-supplied files or tabular rows and provide a direct ingestion path when data must first enter the project.

Datasets are tied to connections. When creating a managed, external, or Uploaded Files dataset, select a connection that supports the intended storage and access pattern. Prefer an explicitly requested connection; otherwise preserve the established connection context of adjacent flow assets when it is clear.

A dataset schema includes column names, storage types, semantic meanings, and descriptions. Column descriptions and meanings document business intent; storage types control how values are interpreted. AI-generated metadata can accelerate documentation, but suggestions must be reviewed before they are applied.

## Using a Dataset from Another Project

Cobuild can share a dataset from another project into the project where its conversation is running. It may also select and share that dataset as part of a broader Flow request. Use [Cross-Project Sharing](./cross-project-sharing.md) for the workflow and verification steps.

## Creation Routes

| Dataset type | Creation path |
| --- | --- |
| Managed dataset | Route creation through `./cobuild.md`. |
| External dataset | Route creation through `./cobuild.md`. |
| Uploaded Files dataset | Create directly from user-supplied data using [Uploaded Files Datasets](./datasets/uploaded-files-datasets.md). |

The direct-upload exception applies only to creating a new Uploaded Files dataset. All later changes to dataset schema, metadata, or lifecycle route through Cobuild.

## Inspection Workflow

1. Use `list_datasets` to discover exact dataset names, types, connections, and shared datasets. Shared datasets are returned in the target project with `shared: true` and a source-project-qualified name.
2. Use `get_dataset_info` to inspect a selected dataset's type, connection, schema, meanings, and descriptions.
3. Use `get_dataset_profile` to inspect null rates, value frequencies, distributions, and numeric ranges.
4. Use `get_dataset_sample` when raw values or formatting details matter, such as date formats, delimiters, text structure, or unexpected encodings.
5. Use `export_dataset` when every row is needed for parity checks, offline inspection, or downstream local tooling. On large datasets this can take a while to run, so prefer the lighter inspection tools unless a full local CSV is truly needed. Use `limit` to bound the export; the tool will not export more than 1,000,000 rows in one call.
6. Use `get_dataset_metrics` and `get_dataset_column_descriptions` when attached metrics or descriptions matter.
7. Interpret findings in context. Flag type mismatches, high null rates, outliers, duplicates, skewed values, identifier-like columns, and potential leakage or small-sample risks when they affect the user's next step.

## Modification Routing

Route all dataset modifications through `./cobuild.md`, including schema changes, column descriptions, semantic meanings, AI metadata application, managed/external dataset changes, and deletion.

Inspect `./connections.md` before a Cobuild request when the required connection is not explicit or cannot be inferred safely from the surrounding flow.

## Preferred Tools

- `list_datasets`
- `get_dataset_info`
- `get_dataset_profile`
- `get_dataset_sample`
- `export_dataset`
- `get_dataset_metrics`
- `get_dataset_column_descriptions`
- `create_upload_dataset`

## Safety Rules

- Inspect an existing dataset before asking Cobuild to build from or modify it.
- Use direct creation only for a new Uploaded Files dataset from user-supplied data.
- Direct upload never replaces an existing dataset. Use a new name or route
  changes through Cobuild.
- `export_dataset` preserves raw CSV values by default. Set
  `spreadsheet_safe=true` when the export may contain untrusted values and will
  be opened in spreadsheet software.
- Keep samples small unless the user requests a larger inspection.
- Treat `export_dataset` as a heavier operation on large datasets, and bound it with `limit` when a complete export is unnecessary.
