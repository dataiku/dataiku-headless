---
name: datasets
description: Understand and inspect Dataiku datasets, including their storage, schema, metadata, and quality signals. Use when an agent must inspect existing datasets, prepare a grounded Cobuild request, write a local CSV export in stdio, or create a new Uploaded Files dataset from user-supplied data.
---

# Datasets

Dataset inspection, export, and builds are available on `design` and `automation`. New dataset creation, including direct uploads and Cobuild, requires `design`.

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
2. Use `get_dataset_info` to inspect a selected dataset's type, managed flag, connection, schema, meanings, and descriptions. Set `include_location=true` when inspecting storage location or preparing deployment; read the location response as described below.
3. Use `get_dataset_profile` to inspect null rates, value frequencies, distributions, and numeric ranges.
4. Use `get_dataset_sample` when raw values or formatting details matter, such as date formats, delimiters, text structure, or unexpected encodings.
5. Use `get_dataset_metrics` and `get_dataset_column_descriptions` when attached metrics or descriptions matter. `get_dataset_metrics` recomputes the requested metrics on the current data before it reads them, which needs project write access and scans the data for record counts. See [Metric Freshness](#metric-freshness).
6. Interpret findings in context. Flag type mismatches, high null rates, outliers, duplicates, skewed values, identifier-like columns, and potential leakage or small-sample risks when they affect the user's next step. State sampling and coverage limits; a sample does not establish whole-dataset results.

## Analysis Beyond Inspection

Keep dataset analysis in Dataiku. When inspection tools cannot answer the question, use `./cobuild.md` on Design for analysis in the project. Keep `allow_edit_project=false` for inspection or explanation; enable edits only for user-requested asset creation or modification. On Automation, inspect or execute existing assets and return to Design when new analysis assets are needed.

Do not export rows simply because local Python is convenient or because `get_dataset_sample` reaches its row cap. If the available tools and Cobuild cannot perform the analysis, report the coverage gap rather than silently moving the work to a local CSV.

## Local CSV Exports

Use `export_dataset` when the user requests a local file or the applicable workflow explicitly requires offline validation, such as the Excel migration parity workflow. Routine exploration and verification should use the inspection tools above or analysis in Dataiku.

Export is available only in stdio; Streamable HTTP cannot write a host-local CSV. Select only the required `columns` and bound `limit` to the requested scope. Each call is capped at 1,000,000 rows, so an export does not establish full coverage when the dataset exceeds that cap. Follow the applicable validation workflow when exhaustive comparison is required.

## Metric Freshness

Stored metric values are not live. Dataiku's built-in `records:COUNT_RECORDS` metric does not recompute on build by default, so its stored value can describe data from before the latest build. External datasets can also change without any Dataiku build.

- Keep the default `refresh=true` when a number feeds a decision, a parity check, or a user answer.
- Check `refreshed` in the response. When it is `false`, report the value as possibly stale, quote `refresh_error`, and name every id in `stale_metric_ids`. Those values were computed before the last build started.
- A successful computation can leave stored values untouched, for example when their probes are disabled. `refreshed` is true only when the computation report includes every requested metric (or every returned metric when no ids are specified). `unrefreshed_metric_ids` identifies metrics absent from that report; treat them as possibly stale even if no build has occurred.
- `refresh=false` reads stored values only. Use it for metric history or when recomputing is too expensive, and say the values may be stale.
- An empty `stale_metric_ids` after `refresh=false` does not prove freshness. External data can change without a build.

## Configured storage locations

Set `include_location=true` on `get_dataset_info` when checking data availability
or storage isolation. Inspect `location.parameters` for storage settings and
`location.partitioning` for partition rules.

- `${...}` variables remain unexpanded. `projectKey` is the project key. Use `get_project_variables` to discover other variables.
- Blank or absent fields may inherit connection defaults; they do not
  establish that no storage dependency exists. Discover default connection settings with `get_connection_info(contextual_project_key=...)`.
- Review included queries and custom SQL/code for additional data dependencies
  and write targets. Inspect referenced datasets and managed folders separately.
- These settings do not establish the complete resolved destination. Obtain
  missing evidence from the above tools and the Dataiku UI as necessary.

## Modification Routing

Route all dataset modifications through `./cobuild.md`, including schema changes, column descriptions, semantic meanings, AI metadata application, managed/external dataset changes, and deletion.

Inspect `./connections.md` before a Cobuild request when the required connection is not explicit or cannot be inferred safely from the surrounding flow.

## Preferred Tools

- `list_datasets`
- `get_dataset_info`
- `get_dataset_profile`
- `get_dataset_sample`
- `get_dataset_metrics`
- `get_dataset_column_descriptions`
- `create_upload_dataset`

For requested local files or explicit offline validation workflows: `export_dataset`.

## Safety Rules

- Inspect an existing dataset before asking Cobuild to build from or modify it.
- Use direct creation only for a new Uploaded Files dataset from user-supplied data.
- In Streamable HTTP, supply direct-upload data as `columns` and at most 10,000
  `rows`; host-local file paths are stdio only.
- Direct upload never replaces an existing dataset. Use a new name or route
  changes through Cobuild.
- `export_dataset` preserves raw CSV values by default. Set
  `spreadsheet_safe=true` when the export may contain untrusted values and will
  be opened in spreadsheet software.
- Keep samples small unless the user requests a larger inspection.
