# Reference: Tool Index

> Generated from the live FastMCP registry by `scripts/generate_tool_index.py`. Do not edit by hand — change the tool docstring and regenerate: `uv run python scripts/generate_tool_index.py`.

Every tool the headless supervisor exposes (57 under the default **stdio** transport), grouped by domain, each with the first sentence of its docstring. Skim this when the capability you need isn't obvious from a playbook; then get exact parameters, defaults, and enums from the tool schema — never from this list.

Under the `streamable-http` transport the surface differs: the registry swaps `create_upload_dataset` for `create_upload_dataset_from_rows` and drops the instance-switching tools (`switch_instance`, `list_instances`). This file reflects the stdio surface.

## Projects

- `count_projects` — Count projects on the Dataiku instance without listing project metadata.
- `create_project` — Create a new project on the Dataiku instance.
- `get_project_metadata` — Get project metadata: label, descriptions, tags, and checklists.
- `get_project_overview` — Call this first when orienting on a project — one call replaces the list_* fan-out.
- `get_project_variables` — Get the project's standard variables, with credential-like values redacted.
- `list_projects` — List the projects on the Dataiku instance.

## Datasets

- `create_upload_dataset` — Create an UploadedFiles dataset from a local file.
- `get_dataset_info` — Get the dataset's type, connection, and column schema.
- `get_dataset_metrics` — Get the last computed metric values for a dataset.
- `get_dataset_profile` — Profile per-column nulls, value frequencies, and numeric stats.
- `get_dataset_sample` — Sample rows from a dataset to inspect raw value formats.
- `list_datasets` — List the datasets in the project with their types and connections.

## Recipes

- `get_recipe_settings` — Get a recipe's settings (type, inputs/outputs by role, params, payload, code).
- `list_recipes` — List the recipes in the project with their types, inputs, and outputs.

## Flow

- `get_flow_graph` — Get the whole flow in one call: nodes, edges, and an ASCII build tree.
- `get_flow_object_metadata` — Get metadata for a flow object.
- `list_flow_zones` — List the flow zones in the project with their items.

## Connections

- `get_connection_info` — Get information about a DSS connection.
- `list_connections` — List the DSS connections available on the instance, each with its type.
- `test_connection` — Test if a DSS connection is available.

## Scenarios

- `get_scenario_run_history` — Get the last runs of a scenario.
- `get_scenario_settings` — Summarize a scenario's settings: run-as, triggers, steps, and reporters.
- `list_scenarios` — List the scenarios in the project with their active and running status.
- `run_scenario` — Request a manual run of an existing scenario.

## Jobs

- `build_datasets` — Build one or more existing datasets as a single DSS job.
- `get_future_status` — Get the status of a DSSFuture returned by a long-running DSS operation.
- `get_job_log` — Get DSS job logs.
- `get_job_status` — Get the current status of a DSS job.
- `list_jobs` — List recent DSS jobs in the project.
- `run_recipe` — Run an existing recipe by building its first output as the trigger target.
- `wait_for_job` — Wait for a DSS job to finish, with a timeout.

## Managed folders

- `get_managed_folder_contents` — List files inside a managed folder.
- `get_managed_folder_info` — Get a managed folder's id, name, type, connection, and path.
- `list_managed_folders` — List the managed folders in the project.
- `upload_file_to_managed_folder` — Upload a local file to a path inside a managed folder.

## Code environments

- `list_code_envs` — List all code environments available on the DSS instance, each with its name and language.

## Data collections

- `list_data_collection_objects` — List the objects in a Data Collection.
- `list_data_collections` — List the Data Collections accessible on the instance.

## Cross-project sharing

- `list_shared_objects` — List the objects this project shares with other projects.

## Project libraries

- `list_project_library` — List project library contents, optionally filtering to internal or external items.
- `read_project_library_file` — Read a text file from the project library, bounded to ``max_bytes``.
- `write_project_library_file` — Create or update a project library file from a local file upload.

## Data quality

- `get_data_quality_status` — Get dataset-level Data Quality status, optionally with partition statuses.
- `list_data_quality_rules` — List Data Quality rules configured on a dataset with compact summaries.

## Agents

- `list_agents` — List the agents in the project.

## LLMs and knowledge banks

- `list_llms` — List DSS-managed LLMs available in the project.

## Machine learning

- `list_ml_analyses` — List the ML analyses in the project with their single-task summaries.
- `list_saved_models` — List the saved models in the project.

## Instances

- `get_current_instance` — Get the active Dataiku instance URL and configured defaults.
- `list_instances` — List the configured Dataiku instances (name, URL, description, active flag).
- `switch_instance` — Switch the active Dataiku instance.

## Cobuild

- `answer_cobuild_confirmation` — Answer a pending Cobuild delete-confirmation with APPROVE or CANCEL.
- `get_cobuild_turn_status` — Poll a Cobuild turn that returned ``status: timeout``.
- `list_cobuild_conversations` — List Cobuild conversations for the current instance + project.
- `send_cobuild_message` — Send one message to a Cobuild conversation and return its settled result.
- `start_cobuild_conversation` — Open a new Cobuild conversation for a project and register it durably.

## Project audit

- `audit_project` — Run after a Cobuild delegation to independently verify the work with a flow-level audit (datasets, recipes, zones, wiki): structure, documentation, evidence (real rows), maintainability.
