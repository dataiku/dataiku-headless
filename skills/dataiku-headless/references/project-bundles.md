---
name: project-bundles
description: Inspect, create, and publish project bundles on a Design node before deployment to an Automation node.
---

# Project Bundles

Bundle listing, creation and publication require `design`.

Use this guide to inspect, create and publish project bundles for deployment to
an Automation node via a Project Deployer.

## Project Bundle Concepts

A bundle snapshots project configuration and selected data/artifacts for running
the project on an Automation node. Unlike a full project export for another Design
node, it carries what the production workflow needs. The same bundle can be
promoted through test and production Automation nodes.

Creation captures the bundle on the Design node. Publication makes it available on the
configured Project Deployer. Activation applies its configuration and included content
to the project on the Automation node.

## Bundle Contents

### Metadata

Bundles include project settings and object definitions, including datasets,
recipes, saved models, managed folders, ML analyses, dashboards and scenarios,
plus project shared code. Notebook definitions and outputs follow the notebook
export options below.

These definitions do not include dataset rows, folder files, trained model versions,
or Knowledge Bank data. Global shared code must be provided separately.

### Additional Content

Select the data and artifacts needed on the Automation node. Some examples:

- Dataset rows: source or reference data that the Automation node cannot otherwise
  access. Follow the [data availability and storage isolation policy](#data-availability-and-storage-isolation-policy).
- Saved-model versions: models trained on the Design node and needed for scoring.
- Managed-folder files: runtime reference files, documents or serialized artifacts.

### Additional Content Selection

Pass changed keys in `create_project_bundle(export_options=...)`. Omitted keys
preserve saved options; supplied lists replace selections (`[]` clears). Changes
remain saved for future bundles, including when export fails. Do not copy the
whole options object back: it can contain general project-export switches that
this tool does not support, such as `exportAllDatasets`.

| Content | Option | Entry shape |
| --- | --- | --- |
| Non-partitioned dataset data | `includedDatasetsData` | `{"name": "<dataset name>"}` |
| Saved models for scoring | `includedSavedModels` | `{"id": "<saved-model ID>"}` |
| Runtime folder files | `includedManagedFolders` | `{"id": "<folder ID>"}` |
| Evaluation-store data | `includedModelEvaluationStores` | `{"id": "<store ID>"}` |
| Knowledge Bank data | `includedKnowledgeBanks` | `{"id": "<bank ID>"}` |
| Labeling-task data | `includedLabelingTasks` | `{"id": "<task ID>"}` |
| Code Studios | `includedCodeStudios` | `{"id": "<studio ID>"}` |
| Prompt Studio history | `includedPromptStudiosHistories` | `{"promptStudioId": "<studio ID>", "promptId": "<prompt ID>"}` |

### Other Additional Content Options

| UI choice | `export_options` setting |
| --- | --- |
| Export project / dataset resources | `exportProjectResources` / `exportDatasetResources` |
| Export static insights data | `exportInsightsData` |
| Include only required saved-model versions | `exportSavedModelsRequiredVersions=true`: active version, plus the retrain version used by a partitioned model's training recipe when different. `false` includes all versions of selected models. |
| Notebook export | With outputs: `exportNotebooks=true`, `exportNotebooksWithOutputs=true`. Without outputs: `true`, `false`. Omit notebooks: `false`, `false`. |
| Export all Agent Review tests | `exportAgentReviews` |

## Data Availability and Storage Isolation Policy

Before creating a production bundle, establish that **every required input will be available
on the Automation node and every write target is isolated from the Design node's data.**

### Input Source Data

| Source | Required action |
| --- | --- |
| Uploaded files, files local to the Design node or other inaccessible input | Include the required data in the bundle. If that source cannot be bundled, arrange an accessible copy. |
| External storage | Verify that the Automation node's connection can read the same source or a validated copy with compatible schemas and the required records/snapshot. |

The same filesystem path on two hosts does not establish shared data. Treat any
input that recipes, scenarios or project code modify as a write target.

### Intermediate Data and Outputs

Default to recomputing intermediates and outputs on the Automation node. Isolate all writes,
including managed-folder writes, scenario side effects and imports of bundled data.

Shared storage is fine when writes affect disjoint data: for example, separate
prefixes in one object-store bucket or separate tables in one database/schema.
Check the scope of overwrite and delete operations as well as the named objects.
Different connection names or credentials alone do not establish isolation.

Compare connection destinations, dataset settings and variable overrides on both
nodes. Remapping may leave hardcoded paths unchanged; `${projectKey}` alone does
not separate nodes using the same project key and storage root. Use distinct roots,
namespaces or environment variables. See
[Relocatable managed datasets](https://doc.dataiku.com/dss/latest/connecting/relocation.html).

## Workflow

1. Use `get_current_instance` to verify the Design node profile and `list_projects`
   to discover the project key. Use `list_project_bundles` to inspect existing
   bundle IDs and current `export_options`. These are saved defaults, not the
   content inventory of an existing bundle.
2. Discover project objects with `list_datasets`, `list_saved_models`,
   `list_managed_folders`, `list_evaluation_stores` and `list_knowledge_banks`.
   Select datasets by name and other objects by ID. For `includedSavedModels`,
   use the saved-model object's `id` from `list_saved_models`.
   `list_saved_model_versions` lists individual trained versions within that
   model; their IDs do not belong in `includedSavedModels`. The
   `exportSavedModelsRequiredVersions` option controls which versions are included.
   Use saved selections or the UI for objects without a discovery tool. Follow the
   [ML](./machine-learning.md), [folder](./managed_folders.md) and
   [Knowledge Bank](./llms-and-knowledge-banks.md) guides for further inspection.
3. Inspect dependencies and storage on the Design node. Use `get_flow_graph`,
   `get_dataset_info(include_location=true)`, `get_managed_folder_info`,
   `get_connection_info` with `contextual_project_key`, and `get_project_variables`.
   Identify required inputs and all write targets, following the
   [dataset](./datasets.md) and [connection](./connections.md) guides.
4. On the `deployer` profile, use `deployer.get_infrastructure` with
   `deployer_type="project"` to inspect infrastructure defaults in `settings`.
   For an existing deployment, also use `deployer.get_deployment` to inspect its
   saved configuration. For a new deployment, start from
   infrastructure defaults and identify the overrides needed. Follow the
   [Project Deployer guide](./project-deployer.md); changing these settings still
   requires the UI.
   Switch to the Automation node profile and use `list_connections` and
   `get_connection_info` to inspect the intended target connections. If the target
   project exists, pass its `contextual_project_key` and inspect
   `get_project_variables`; otherwise compare connection defaults with planned
   target variable values. Verify input availability and write isolation, and check
   target plugins, code environments, global shared code, scenario triggers and
   existing objects that activation could overwrite.
5. Assess production readiness from the discovered objects and target settings.
   Resolve missing inputs, uncertain or overlapping write targets, and unmet
   dependencies before creating the bundle. Decide which additional content to
   include using [Bundle Contents](#bundle-contents) and the
   [data policy](#data-availability-and-storage-isolation-policy), and verify that
   the selected data and trained model versions are available.
6. Switch back to the Design node profile. Call `create_project_bundle` with the
   project key, a new bundle ID, changed `export_options` and optional
   `release_notes`. Omit `export_options` to reuse
   saved selections. Creation requests project standards checks; existing IDs,
   including failed exports, cannot be overwritten.
7. Re-read `list_project_bundles` and verify that the new bundle is BUILT before
   publishing.
8. Use `publish_project_bundle` after verifying the **Design node's configured
   Project Deployer**. Optional `published_project_key` defaults to the source
   project key; existing published bundle IDs cannot be replaced. Verify the
   publication receipt, then switch to the intended `deployer` profile and follow
   the [Project Deployer guide](./project-deployer.md) to deploy and verify it.

## Preferred Tools

- `list_project_bundles`
- `create_project_bundle`
- `publish_project_bundle`

## Safety Rules

- Bundle tools package existing assets. Route flow and analytic changes through
  `./cobuild.md`.
- Publish and activate upstream bundles before downstream bundles that use their
  shared objects.
- After a creation timeout, cancellation or connection failure, inspect the listing
  on the same Design node before retrying. BUILDING is pending; FAILED and ABORTED
  cannot be published. If the entry is missing, check the UI before resubmitting
  or choosing another ID.
- For uncertain publication, inspect the local receipt and the configured Project Deployer's
  published versions before retrying; publication may have succeeded without a receipt.
