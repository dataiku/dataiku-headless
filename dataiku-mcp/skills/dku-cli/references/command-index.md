# Reference: Command Index

> Generated from `dku`'s command tree by `scripts/generate_command_index.py`. Do not edit by hand — change help text in the CLI source and regenerate.

Every group and command with its one-line description — read this once per session when the capability table in `SKILL.md` doesn't have a row, or the task spans domains you haven't touched yet. Grep it locally instead of drilling `--help` into each group. Once you have the exact command, jump straight to `dku <group> <command> --help` for flags.

## Root Commands

### `root` — Root-level commands.

- `commands` — List every group/command with a one-line description, in one read.
- `whoami` — Show current authenticated user.

## Tabular Flow & Data

### `dataset` — Manage DSS datasets.

- `ai-describe` — Generate AI-powered descriptions for a dataset and its columns.
- `analyze-column` — Analyze a column: distribution, null rate, top-K values, and basic stats.
- `build` — Trigger dataset build.
- `checks` — Inspect and compute data-quality rules. Modern API (DSSDataQualityRuleSet) — `compute_rules`, `list_rules`, `get_status`, `get_last_rules_results`. The legacy `runChecks` endpoint exposed pre-DSS-12 is intentionally NOT wired up here.
- `checks list` — List data-quality rules with their last results.
- `checks run` — Compute every enabled data-quality rule on the dataset.
- `checks status` — Show the overall data-quality status of the dataset.
- `clear` — Clear all data from a dataset.
- `copy` — Copy dataset DATA into an existing dataset in another project.
- `count` — Count rows in a dataset by its logical name.
- `create` — Create a new dataset.
- `create-from-file` — Create an UploadedFiles dataset from a LOCAL file and auto-detect its schema.
- `delete` — Delete a dataset.
- `detect` — Detect format and schema for a dataset.
- `download` — Stream a dataset's rows to a local CSV (or stdout).
- `exists` — Check whether a dataset exists (exit code 0 = yes, 1 = no).
- `get-definition` — Get the full definition of a dataset as JSON.
- `head` — Preview first rows of a dataset (or all rows with --all).
- `infer-types` — Re-infer storage types for string columns from actual data and optionally apply.
- `info` — Show dataset metadata: size, row count, type, connection, last build.
- `lineage` — Trace a column's provenance across the flow graph.
- `list` — List datasets in a project.
- `metrics` — Inspect and compute dataset metrics (row count, size, custom SQL probes). DSS does NOT auto-recompute metrics on build. Run `dku dataset metrics run` after a recipe rebuild, otherwise downstream checks see stale numbers.
- `metrics get` — Get the cached value of a single metric.
- `metrics history` — Show the time-series history of a metric value.
- `metrics list` — List configured probes and their last computed values.
- `metrics run` — Recompute metrics on the dataset.
- `partitions` — List partitions of a dataset.
- `query` — Run SQL against a dataset's backing table by logical name.
- `rename` — Rename a dataset.
- `schema` — Show dataset schema.
- `set-column-description` — Set descriptions on dataset columns.
- `set-definition` — Set the full definition of a dataset from JSON.
- `set-meaning` — Set the semantic meaning of one or more columns (storage type unchanged).
- `set-metadata` — Update dataset description, short description, and/or tags.
- `set-schema` — Set the schema of a dataset from JSON or shorthand.
- `share` — Share a dataset to another flow zone.
- `unshare` — Unshare a dataset from a flow zone.
- `upload` — Upload a file to an UploadedFiles dataset and auto-detect format/schema.
- `usages` — Show what recipes, analyses, or models use this dataset.
- `zone` — Show which flow zone a dataset belongs to.

### `recipe` — Manage DSS recipes.

- `add-delete-columns` — Add a step to delete (drop) columns from the dataset.
- `add-fill-empty` — Add a step that fills empty/null values in one or more columns with a fixed value.
- `add-filter-rows` — Add a filter step to remove or keep rows matching conditions.
- `add-find-replace` — Add a find-and-replace step on a column.
- `add-fold` — Fold (unpivot) multiple columns into key-value rows (wide→long).
- `add-formula` — Add a formula step (GREL expression) to create or transform a column.
- `add-geodistance` — Compute distance between two geopoint/geometry columns.
- `add-geopoint` — Create a geopoint column from latitude/longitude columns.
- `add-input` — Add an input to a recipe.
- `add-output` — Add an output dataset to a recipe.
- `add-rename` — Add a column rename step. Use --from/--to for single, --mappings for bulk.
- `add-reorder` — Add a ColumnReorder step (auto-fills `appliesTo`).
- `add-step` — Add a processor step to a prepare recipe (generic — any of ~95 processor types).
- `apply-schema` — Compute and apply required schema updates to recipe outputs.
- `apply-spec` — Build a full multi-step prepare recipe from one declarative spec.
- `check-schema` — Check if recipe outputs need schema updates.
- `create` — Create a new recipe.
- `create-agent-eval` — Create an Agent Evaluation recipe (evaluates agent tool-calling accuracy).
- `create-clustering-scoring` — Create a Clustering Scoring recipe (classic ML — assigns cluster labels).
- `create-distinct` — Create a Distinct recipe. Deduplicates rows.
- `create-download` — Create a Download recipe (built-in DSS recipe).
- `create-eda-univariate` — Create an EDA Univariate recipe.
- `create-embed` — Create an Embed Dataset recipe (embeds text columns into a Knowledge Bank).
- `create-embed-docs` — Create an Embed Documents recipe (extracts + chunks + embeds documents into a KB).
- `create-evaluation` — Create an Evaluation recipe (classic ML).
- `create-export` — Create an Export recipe (built-in DSS recipe).
- `create-extract` — Create an Extract Content recipe (extracts structured content from documents using a VLM).
- `create-extract-failed-rows` — Create an Extract-Failed-Rows recipe (built-in DSS recipe type).
- `create-filter` — Create a filter recipe (rows matching the formula).
- `create-fuzzy-join` — Create a Fuzzy Join recipe for approximate string matching. NEVER use Python for fuzzy matching — use this instead.
- `create-generate-features` — Create a Generate Features recipe (auto feature engineering).
- `create-geojoin` — Create a Geo Join recipe. NEVER use Python haversine — use this instead.
- `create-group` — Create a Group (aggregate) recipe. NEVER use Python for aggregations — use this instead.
- `create-join` — Create a Join recipe. NEVER use Python for joins — use this instead.
- `create-list-folder-contents` — Create a List-Folder-Contents recipe (built-in DSS recipe type).
- `create-llm-classify` — Create an LLM Classify recipe (zero/few-shot text classification via NLI).
- `create-llm-eval` — Create an LLM Evaluation recipe (evaluates LLM outputs with metrics like relevancy, faithfulness).
- `create-merge-folder` — Create a Merge-Folder recipe (built-in DSS folder→folder recipe).
- `create-pivot` — Create a Pivot recipe (long→wide). NEVER use df.pivot_table() in Python.
- `create-prediction-scoring` — Create a Prediction Scoring recipe (classic ML).
- `create-prepare` — Create an empty Prepare recipe (auto-creates output dataset).
- `create-prompt` — Create a Prompt recipe (LLM batch generation, one row per input).
- `create-python` — Alias for `recipe create NAME -t python`.
- `create-r` — Create an R code recipe.
- `create-sampling` — Create a Sampling recipe. Takes a random, stratified, or head sample.
- `create-sort` — Create a Sort recipe.
- `create-split` — Create a Split recipe. Routes input rows to N output datasets.
- `create-sql` — Create a sql_query recipe.
- `create-sql-script` — Create a sql_script recipe (multi-statement SQL — DDL / stored-proc-like flows).
- `create-stack` — Create a Stack recipe. Vertically concatenates datasets (UNION).
- `create-sync` — Create a sync recipe with optional schema/engine tuning.
- `create-topn` — Create a Top N recipe. Returns the top/bottom N rows per group.
- `create-update` — Create an Update (UPSERT) recipe.
- `create-window` — Create a Window recipe. Computes window/analytic functions (rank, lag, cumsum).
- `delete` — Delete a recipe.
- `disable-step` — Disable steps in a prepare recipe (skipped during execution).
- `enable-step` — Enable previously disabled steps in a prepare recipe.
- `get` — Show recipe identity and I/O (name, type, inputs, outputs) — NO payload.
- `get-code` — Get the code payload of a code recipe.
- `get-definition` — Get the full recipe definition (raw definition + payload).
- `get-settings` — Get full recipe settings as JSON (includes visual recipe payload).
- `get-step` — Get full details of a single prepare recipe step.
- `lint-formula` — Lint a prepare recipe — validate formula/GREL expressions and step config.
- `lint-python` — Lint a Python recipe — validate code env and engine configuration.
- `lint-sql` — Lint an SQL recipe — validate syntax and engine configuration.
- `list` — List recipes in a project.
- `list-steps` — List steps in a prepare recipe.
- `remove-step` — Remove one or more steps from a prepare recipe by index.
- `rename` — Rename a recipe.
- `replace-input` — Swap an input dataset reference on a recipe.
- `replace-step` — Replace one prepare-recipe step at the given index in a single operation.
- `run` — Run a recipe.
- `set-code` — Set the code payload of a code recipe.
- `set-definition` — Set the definition or payload of a recipe from JSON.
- `set-description` — Set the recipe description (shortcut for set-definition --definition '{"description":"..."}').
- `set-engine` — Change a visual recipe's execution engine after creation.
- `set-env` — Set the code env and/or container of an existing code recipe.
- `set-metadata` — Update recipe short description, description, and/or tags.
- `set-settings` — Set full recipe settings from JSON (supports visual recipe payload).
- `set-sql` — Update the SQL body of a sql_query recipe.
- `status` — Show recipe status: engine, severity, and check messages.

### `flow` — Inspect and manage DSS project flow.

- `ai-describe-zone` — Generate an AI-powered description for a flow zone.
- `check` — Run flow consistency check (schema + data consistency).
- `create-zone` — Create a new flow zone.
- `delete-zone` — Delete a flow zone.
- `graph` — Show flow graph summary.
- `move` — Move items to a flow zone. Use instead of manually organizing in the DSS UI.
- `propagate` — Run schema propagation from a dataset through downstream recipes.
- `set-zone` — Update a flow zone's name, color, and/or descriptions.
- `sources` — Find source datasets (nodes with no upstream dependencies).
- `successors` — Show downstream successors of a flow node.
- `visualize` — Render flow DAG as an ASCII tree.
- `zones` — List flow zones with their items (objectType + objectId per member).

### `dq` — Manage data quality rules on DSS datasets (requires DSS 14.5+).

- `compute` — Compute data quality rules on a dataset.
- `create` — Create a data quality rule on a dataset.
- `delete` — Delete a data quality rule from a dataset.
- `list` — List data quality rules defined on a dataset.
- `project-status` — Show data quality status across all datasets in a project.
- `results` — Show latest data quality rule results for a dataset.
- `rule-schema` — Emit a config template JSON for a data quality rule type.
- `rule-types` — List native DSS data quality rule type ids with scope and description.
- `status` — Show data quality status for a dataset.

### `sql` — Run SQL queries on DSS connections.

- `query` — Execute a SQL query on a DSS connection.

### `connection` — Manage DSS connections.

- `create` — Create a new connection.
- `delete` — Delete a connection (admin only). Tier-3 cascade — orphans all datasets using it.
- `get` — Get connection details as JSON (admin only).
- `list` — List connections. Use --type to filter by connection type.
- `schemas` — List schemas/namespaces available in a SQL or Iceberg connection.
- `set-definition` — Replace a connection's full definition (credential rotation, param changes).
- `sync-acls` — Sync HDFS ACLs for a connection (User Isolation with DSS-managed ACLs).
- `tables` — List tables available for import in a SQL or Iceberg connection.
- `test` — Test a connection.
- `update` — Patch selected fields on an existing connection. Safer than set-definition.

### `folder` — Manage DSS managed folders.

- `copy` — Copy contents of one managed folder to another.
- `create` — Create a new managed folder.
- `create-dataset` — Create a FilesInFolder dataset from a managed folder.
- `decompress` — Extract a zip archive inside a managed folder.
- `delete` — Delete a managed folder from the flow.
- `delete-file` — Delete a file from a managed folder.
- `delete-files` — Delete multiple files from a managed folder.
- `download` — Download a file from a managed folder.
- `get` — Get managed folder settings (name, type, connection, path).
- `get-definition` — Get the full managed-folder definition as JSON.
- `list` — List managed folders in a project.
- `ls` — List contents of a managed folder.
- `rename` — Rename a managed folder.
- `set-definition` — Replace the managed-folder definition from JSON.
- `set-metadata` — Update managed folder description and/or tags.
- `upload` — Upload a file to a managed folder.
- `upload-dir` — Upload an entire local directory to a managed folder.

### `streaming` — Manage DSS streaming endpoints.

- `create` — Create a streaming endpoint.
- `delete` — Delete a streaming endpoint.
- `get` — Get streaming endpoint settings.
- `list` — List streaming endpoints in a project.
- `schema` — Show streaming endpoint schema.
- `set-schema` — Set the schema of a streaming endpoint.

### `meaning` — Manage DSS data dictionary meanings.

- `create` — Create a new meaning (admin only).
- `get` — Get a meaning's definition.
- `list` — List all user-defined meanings.
- `update` — Update a meaning's definition (admin only).

### `library` — Manage DSS project library files.

- `delete` — Delete a file (or, with --recursive, a folder tree) from the library.
- `delete-folder` — Recursively delete a folder and all its contents from the project library.
- `list` — List files in the project library.
- `mkdir` — Create a directory in the project library.
- `read` — Read a file from the project library (prints to stdout).
- `sync` — Sync a local directory to the project library.
- `write` — Write a file to the project library.

### `job` — Manage DSS jobs.

- `abort` — Abort a running job.
- `last` — Show the most recent job id (shortcut for 'dku job list | .').
- `list` — List recent jobs.
- `log` — Show job log output.
- `run` — Run a build job with full control over build type and schema updates.
- `status` — Show job status details.
- `wait` — Wait for a job to reach a terminal state.

### `continuous` — Manage continuous recipe activities.

- `list` — List continuous activities in a project.
- `start` — Start a continuous activity.
- `status` — Get the status of a continuous activity.
- `stop` — Stop a continuous activity.

### `analysis` — Manage DSS visual analyses (lab).

- `create` — Create a new visual analysis for a dataset.
- `delete` — Delete a visual analysis.
- `get` — Show visual analysis definition.
- `list` — List visual analyses in a project.
- `tasks` — List ML tasks in a visual analysis.

### `macro` — Manage DSS macros.

- `list` — List available macros in a project.
- `result` — Print the rendered result of a finished macro run.
- `run` — Run a macro.

### `bundle` — Manage DSS project bundles.

- `activate` — Activate (preload and apply) a bundle on a project.
- `download` — Download an exported bundle archive to a local file.
- `export` — Export (create) a bundle snapshot.
- `import` — Import a bundle archive into a project.
- `list` — List exported bundles for a project.

## GenAI & Agents

### `agent` — Manage DSS agents.

- `add-tool` — Add a tool to an agent's active version. Accepts agent ID or name.
- `create` — Create a new agent. Prints the created agent as data (capture the id).
- `create-react` — Create a tool-calling (ReAct) agent in one call.
- `create-version` — Create a new agent version by deep-copying an existing one.
- `delete` — Delete an agent. Accepts agent ID or name.
- `get` — Show agent settings. Accepts agent ID or name.
- `list` — List agents in a project.
- `list-versions` — List versions of an agent. Active version is marked.
- `rename` — Rename an agent. Accepts agent ID or name.
- `set-active-version` — Make a specific agent version active.
- `set-code` — Set the Python code for a Code Agent (PYTHON_AGENT). Accepts agent ID or name.
- `set-llm` — Set the LLM for an agent's active version. Accepts agent ID or name.
- `set-metadata` — Update agent description, short description, and/or tags.
- `set-prompt` — Set the system prompt for an agent's active version. Accepts agent ID or name.
- `shutdown` — Shutdown an agent. Accepts agent ID or name.
- `status` — Show agent status. Accepts agent ID or name.
- `test` — Send a test query to an agent and display the response.
- `wake-up` — Wake up an agent. Accepts agent ID or name.

### `agent-block` — Manage visual agent block graphs.

- `add` — Add a block to the agent's block graph.
- `connect` — Connect two blocks (set nextBlock on source).
- `disconnect` — Disconnect a block (remove nextBlock, making it terminal).
- `get` — Show a single block definition.
- `get-graph` — Dump the full block graph definition (auto-detects settings key).
- `list` — List blocks in an agent's block graph.
- `remove` — Remove a block from the agent's block graph.
- `set-graph` — Replace the full block graph definition (auto-detects settings key).
- `set-mode` — Switch agent mode between SIMPLE and BLOCKS_GRAPH.
- `set-start` — Set the starting block of the agent's block graph.

### `agent-hub` — Manage DSS Agent Hub instances (limited surface — see notes). Agent enrollment (add/remove) lives in the plugin's private store and is UI-only.

- `config` — Show the Agent Hub webapp's plugin-runtime config.
- `list` — List Agent Hub instances in a project.
- `set-config` — Update the Agent Hub webapp's plugin-runtime config (shallow merge).
- `start` — Start or restart the Agent Hub backend and verify it actually boots.
- `stop` — Stop the Agent Hub backend.

### `agent-review` — Manage agent reviews — evaluate agent quality with traits, tests, and runs.

- `add-trait` — Add an evaluation trait to a review.
- `compare` — Compare trait pass/fail across multiple runs of the same review.
- `create` — Create a new agent review.
- `create-test` — Create a single test case for an agent review.
- `delete` — Delete an agent review. Accepts review ID or name.
- `delete-test` — Delete a single test from an agent review.
- `export-tests` — Export tests from an agent review to a dataset.
- `get` — Show agent review settings. Accepts review ID or name.
- `get-result` — Show one result's detail with its human-verification state.
- `import-tests` — Import tests from a dataset into an agent review.
- `list` — List agent reviews in a project.
- `list-runs` — List runs of an agent review.
- `list-tests` — List tests in an agent review.
- `override-trait` — Override one trait's AI verdict on a result with a human PASS/FAIL.
- `remove-trait` — Remove a trait from a review. Other traits are preserved.
- `results` — Show results of a review run — per-test trait evaluations.
- `run` — Execute a review run — evaluates the agent against all tests.
- `set-agent` — Link an agent review to an agent.
- `set-llm` — Set the helper LLM used for trait evaluation.
- `update-test` — Edit a test's query, reference answer, or expectations.
- `update-trait` — Edit an existing trait on a review. Only the flags you pass change.
- `verify` — Record a human (SME) review on a result — DSS 14.6 human verification.

### `agent-tool` — Manage DSS agent tools.

- `create` — Create a new agent tool.
- `delete` — Delete an agent tool.
- `describe` — Describe an agent tool type: its known param keys and usage.
- `get` — Show agent tool settings.
- `list` — List agent tools in a project.
- `run` — Run an agent tool.
- `set-definition` — Update agent tool settings (params, config, etc.).
- `types` — List known built-in agent tool types.

### `llm` — Interact with DSS LLM endpoints.

- `completion` — Send a completion request to an LLM.
- `embeddings` — Generate embeddings for a text string.
- `endpoint` — Print the project-scoped OpenAI-compatible LLM Mesh endpoint and auth form.
- `generate-image` — Generate an image using an image generation LLM.
- `list` — List available LLMs.
- `rerank` — Rerank documents by relevance to a query.

### `rag` — Manage Retrieval Augmented LLMs (RAG).

- `create` — Create a RAG LLM that combines a knowledge bank with an LLM.
- `delete` — Delete a RAG LLM.
- `get` — Show RAG LLM details.
- `get-definition` — Get the full definition of a RAG LLM as JSON.
- `list` — List RAG LLMs in a project.
- `set-definition` — Set the full definition of a RAG LLM from JSON.

### `knowledge` — Manage DSS knowledge banks.

- `build` — Build a knowledge bank.
- `create` — Create a new knowledge bank.
- `delete` — Delete a knowledge bank.
- `get` — Show knowledge bank settings.
- `list` — List knowledge banks in a project.
- `search` — Search a knowledge bank.
- `set-definition` — Update a knowledge bank's definition from JSON.

### `eal` — Enterprise Asset Library — governed, reusable prompts.

- `create-prompt` — Create a governed prompt in a collection (needs contributor rights).
- `delete-prompt` — Delete a governed prompt from a collection.
- `get-prompt` — Show a governed prompt, including its full content.
- `list-collections` — List Enterprise Asset Library collections you can read.
- `list-prompts` — List governed prompts across readable collections.

## Project Ops

### `project` — Manage DSS projects.

- `ai-describe` — Generate AI-powered description for a project.
- `audit` — Audit whether an SME could open this project cold, follow the flow, and trust it.
- `create` — Create a new project.
- `delete` — Delete a project. Tier-3 guard: requires --yes and --confirm-name matching the project key.
- `duplicate` — Duplicate a project.
- `export` — Export project as ZIP.
- `find-column-refs` — Find every reference to a column name across the project.
- `get` — Get project details.
- `get-settings` — Get project settings (code envs, flow build, exposed objects, ...).
- `get-variables` — Show project variables (pairs with set-variables).
- `import` — Import a project from a ZIP archive (design node only).
- `inspect` — One-shot project summary: datasets, recipes, flow, scenarios, jobs, wiki, variables.
- `list` — List all projects.
- `permissions` — Show project permissions.
- `set-metadata` — Update project name, description, and/or tags.
- `set-permissions` — Set project permissions from JSON definition (wholesale replace).
- `set-variables` — Set project variables. Use --set for individual standard vars or --definition to replace all.
- `tags` — Show project tags.
- `timeline` — Show project timeline: creation, contributors, recent modifications.

### `project-standards` — Manage Project Standards checks, scopes, and compliance runs (DSS 14.1+).

- `create-checks` — Import checks from plugin specs into the instance library (admin).
- `create-scope` — Create a project-, folder-, or tag-selected scope (admin).
- `delete-check` — Delete a check without leaving dangling scope references (admin).
- `delete-scope` — Delete a custom scope (admin).
- `get-check` — Get one check's full definition.
- `get-default-scope` — Get the fallback scope used when no custom scope matches.
- `get-scope` — Get one scope's full definition.
- `last-report` — Show the latest saved scoped report for a project.
- `list-check-specs` — List available check specs and their parameter schemas.
- `list-checks` — List configured checks, parameters, and tags.
- `list-scopes` — List scopes in evaluation priority order.
- `project-scope` — Show which scope currently applies to a project.
- `reorder-scope` — Move a custom scope in priority order; Default remains last (admin).
- `run` — Run checks; optionally turn findings into a CI exit code.
- `update-check` — Update a check's name, description, params, or tags (admin).
- `update-scope` — Replace a scope's checks, description, or selector (admin).

### `project-folder` — Manage DSS project folders.

- `create` — Create a project subfolder.
- `list` — List all project folders (recursive tree from root).
- `move-project` — Move a project to a different folder.

### `project-deployer` — Manage Project Deployer infras, projects, and deployments.

- `create-deployment` — Create a new Project Deployer deployment.
- `delete-deployment` — Delete a Project Deployer deployment.
- `deployment-status` — Show Project Deployer deployment health and messages.
- `get-deployment` — Show Project Deployer deployment settings.
- `list-deployments` — List Project Deployer deployments.
- `list-infras` — List Project Deployer infrastructures.
- `list-projects` — List Project Deployer published projects.
- `update-deployment` — Update (push) a Project Deployer deployment.

### `scenario` — Manage DSS scenarios.

- `abort` — Abort a running scenario.
- `add-reporter` — Add an email reporter to a scenario.
- `add-step` — Add a step to a step-based scenario (generic; supports any step type).
- `add-step-build` — Add a build_flowitem step (the most common scenario step).
- `add-step-check-dataset` — Add a check_dataset step (run dataset checks defined on the dataset).
- `add-step-clear-items` — Add a clear_items step. Wipes data on datasets, managed folders, and/or
- `add-step-compute-metrics` — Add a compute_metrics step. Refreshes metrics on datasets, managed
- `add-step-export-dashboard` — Add a create_dashboard_export step (PDF/PNG snapshot of a dashboard).
- `add-step-prepare-lambda-package` — Add a prepare_lambda_package step (build an API-deployer package from this project's API service).
- `add-step-propagate-schema` — Add a schema_propagation step.
- `add-step-python` — Add a custom_python step (inline Python script in a step-based scenario).
- `add-step-refresh-chart-cache` — Add a refresh_chart_cache step (precompute dashboard tile data).
- `add-step-reload-schema` — Add a reload_schema step (refresh source schemas before downstream builds).
- `add-step-restart-webapp` — Add a restart_webapp step (used to refresh dashboard-attached webapps).
- `add-step-run-scenario` — Add a run_scenario step (chain another scenario).
- `add-step-sql` — Add an exec_sql step (run a SQL query against a connection).
- `add-step-update-deployment` — Add an update_apideployer_deployment step.
- `add-trigger` — Add a trigger to a scenario from JSON.
- `add-trigger-dataset` — Add a dataset change trigger (fires when dataset data is modified).
- `add-trigger-python` — Add a custom_python trigger (fire-on-state-condition).
- `add-trigger-time` — Add a time-based (temporal) trigger to a scenario.
- `avg-duration` — Show average duration of recent successful scenario runs.
- `create` — Create a new scenario.
- `delete` — Delete a scenario.
- `get-code` — Get the script/code of a scenario.
- `get-definition` — Get the raw definition of a scenario as JSON.
- `last-run` — Show the last finished run of a scenario.
- `list` — List scenarios in a project.
- `list-reporters` — List reporters on a scenario.
- `list-steps` — List steps in a step-based scenario.
- `list-triggers` — List triggers on a scenario.
- `remove-step` — Remove a step from a step-based scenario by index.
- `remove-trigger` — Remove a trigger from a scenario by index.
- `run` — Run a scenario.
- `run-log` — Get logs from a specific scenario run.
- `runs` — List recent runs of a scenario.
- `set-active` — Enable or disable a scenario AND every trigger in one call.
- `set-code` — Set the script/code of a scenario, or of one custom_python step.
- `set-definition` — Update a scenario's definition from JSON.
- `set-metadata` — Update scenario description, short description, and/or tags.
- `status` — Show last run status of a scenario.

### `git` — Manage a DSS project's git repository.

- `branches` — List branches in the project's git repository.
- `commit` — Commit pending changes in the project's git repository.
- `create-branch` — Create a new local branch and switch to it.
- `create-tag` — Create a tag on the project's git repository.
- `delete-branch` — Delete a local or remote branch.
- `diff` — Show changes between commits or working copy and last commit.
- `fetch` — Fetch refs from the remote repository.
- `log` — List commits in the project's git repository.
- `pull` — Pull changes from the remote repository (rebase).
- `push` — Push local commits to the remote repository.
- `remote` — Get or set the remote URL for the project's git repository.
- `reset-to-head` — Drop uncommitted changes, hard-resetting the working copy to HEAD.
- `reset-to-upstream` — Hard-reset the current branch to its upstream (remote) state.
- `status` — Show the current state of the project's git repository.
- `switch` — Switch to a different branch.
- `tags` — List tags in the project's git repository.

### `code-env` — Manage DSS code environments.

- `create` — Create a new code environment.
- `delete` — Delete a code environment.
- `get` — Show code environment details.
- `jupyter` — Toggle Jupyter support for a code environment.
- `list` — List all code environments.
- `logs` — List or read code environment build logs.
- `set-packages` — Set the package list for a code environment.
- `update` — Update packages in a code environment (re-resolve versions, optional rebuild).
- `update-images` — Rebuild the Docker image for a code env (container-exec).
- `usages` — Show what uses a code environment.

### `code-studio` — Manage DSS Code Studios.

- `change-owner` — Change the owner of a Code Studio.
- `create` — Create a new Code Studio.
- `delete` — Delete a Code Studio.
- `get` — Show Code Studio settings.
- `list` — List Code Studios in a project.
- `start` — Start (or restart) a Code Studio.
- `status` — Show Code Studio status (STOPPED, STARTING, RUNNING, STOPPING).
- `stop` — Stop a Code Studio.
- `templates` — List available Code Studio templates (instance-level, no project required).

### `cluster` — Manage DSS clusters (admin only).

- `create` — Create a new cluster.
- `delete` — Delete a cluster (does not stop it first).
- `get` — Get cluster settings.
- `list` — List all clusters.
- `start` — Start or attach a managed cluster.
- `status` — Get cluster status and usage.
- `stop` — Stop or detach a managed cluster.

### `notebook` — Manage DSS notebooks (Jupyter and SQL).

- `clear-outputs` — Clear all outputs from a Jupyter notebook.
- `create` — Create a new Jupyter notebook.
- `delete` — Delete a Jupyter notebook.
- `get` — Get a Jupyter notebook's content.
- `history` — Show execution history of a SQL notebook.
- `list` — List notebooks in a project. Combines Jupyter and SQL notebooks.
- `sessions` — List running notebook sessions.
- `stop` — Stop a running notebook session.

### `api-deployer` — Manage API Deployer infras, services, and deployments.

- `create-deployment` — Create a new API Deployer deployment.
- `delete-deployment` — Delete an API Deployer deployment.
- `deployment-status` — Show API Deployer deployment health and live service URLs.
- `get-deployment` — Show API Deployer deployment settings.
- `get-service` — Show API Deployer service settings.
- `list-deployments` — List API Deployer deployments.
- `list-infras` — List API Deployer infrastructures.
- `list-services` — List API Deployer services.
- `update-deployment` — Update (push) an API Deployer deployment.

### `api-service` — Manage DSS API services.

- `add-endpoint` — Add a typed endpoint to an API service.
- `create` — Create a new API service.
- `create-package` — Create a new package (version) for an API service.
- `delete-package` — Delete a package from an API service.
- `get` — Get API service settings.
- `list` — List API services in a project.
- `list-endpoints` — List endpoints of an API service.
- `list-packages` — List packages for an API service.
- `publish-package` — Publish a package to the API Deployer.

### `wiki` — Manage DSS wiki articles.

- `create` — Create a wiki article.
- `delete` — Delete a wiki article.
- `get` — Get a wiki article's content.
- `list` — List wiki articles in a project.
- `update` — Update a wiki article's body and/or title.

### `discussion` — Manage discussions on DSS objects.

- `create` — Create a new discussion on a DSS object.
- `get` — Get a specific discussion with its replies.
- `list` — List discussions on a DSS object.
- `reply` — Reply to a discussion.

## Analytics & Apps

### `dashboard` — Manage DSS dashboards.

- `add-tile` — Add an insight tile to a dashboard page.
- `create` — Create a new dashboard.
- `delete` — Delete a dashboard.
- `get` — Get dashboard details.
- `get-definition` — Get the raw definition of a dashboard as JSON.
- `list` — List dashboards in a project.
- `list-tiles` — List tiles across all pages of a dashboard.
- `remove-tile` — Remove all tiles referencing an insight from a dashboard.
- `set-definition` — Update a dashboard's definition from JSON.
- `set-metadata` — Update dashboard description, short description, and/or tags.
- `validate` — Pre-flight a dashboard layout before a human loads it.

### `insight` — Manage DSS insights (charts, reports, metrics views).

- `add-dimension` — Add a dimension column to a chart insight.
- `add-measure` — Add a measure column to a chart insight.
- `clear-columns` — Clear all dimension and measure column bindings from a chart insight.
- `create` — Create a new insight.
- `delete` — Delete an insight.
- `get` — Get insight details.
- `get-definition` — Get the raw definition of an insight as JSON.
- `head` — Preview rows from the dataset bound to an insight.
- `list` — List insights in a project.
- `set-chart-type` — Set the chart type of a chart insight.
- `set-colors` — Set a chart's colors: a single color, a named palette, or per-category map.
- `set-definition` — Update an insight's definition from JSON.
- `set-metadata` — Update insight description, short description, and/or tags.
- `validate` — Pre-flight a chart insight before a human loads it.

### `app` — List DSS applications and instantiate them. For authoring (enable app mode, homepage sections, tiles, manifest) use dku app-designer.

- `create-instance` — Create a new instance of an application.
- `get` — Get app manifest/details.
- `list` — List all applications (app templates).
- `list-instances` — List instances of an application.

### `app-designer` — Manage App Designer manifest and tiles.

- `add-tile` — Add a tile to the app homepage.
- `disable` — Disable the app homepage (set useAppHomepage=false).
- `enable` — Enable the app homepage on a project (APP_TEMPLATE mode).
- `get` — Get the full app manifest.
- `list-tiles` — List all tiles across all sections.
- `remove-tile` — Remove a tile by section and tile index.
- `set-definition` — Set/replace the full app manifest from JSON.
- `set-section` — Set section title and/or description text.

### `ml` — Create, train, and deploy ML models (prediction, clustering, timeseries, causal).

- `algorithms` — List available algorithms and which are enabled.
- `create-causal` — Create a causal prediction ML task from a dataset.
- `create-clustering` — Create a clustering ML task from a dataset.
- `create-prediction` — Create a prediction ML task from a dataset.
- `create-timeseries` — Create a time series forecasting ML task from a dataset.
- `delete` — Delete an ML task.
- `deploy` — Deploy a trained model from the lab to the flow.
- `details` — Show performance metrics for a trained model.
- `ensemble` — Create and train an ensemble from already-trained models.
- `list` — List all ML tasks in a project.
- `models` — List trained models in an ML task with their headline metric.
- `redeploy` — Redeploy a trained model to an existing saved model in the flow.
- `set-algorithm` — Enable or disable algorithms for an ML task.
- `set-feature` — Change the role, rescaling, and/or missing-value handling of a feature.
- `set-features` — Set multiple feature roles in ONE transactional write.
- `set-params` — Set algorithm hyperparameters for an ML task.
- `set-split` — Set the train/test split policy of a prediction ML task.
- `settings` — Show ML task settings (algorithms, features, validation).
- `status` — Show status of an ML task (guessing, training, model count).
- `train` — Train models for an ML task.

### `model` — Manage DSS saved models.

- `create-external` — Create a saved model for external remote endpoints (SageMaker, Databricks, etc).
- `create-mlflow` — Create a saved model for storing MLflow pyfunc models.
- `delete` — Delete a saved model.
- `delete-version` — Delete one or more versions from a saved model.
- `diagnostics` — List, enable, or disable model-level diagnostics.
- `get` — Show saved model details.
- `get-definition` — Get the full saved-model settings as JSON.
- `import-mlflow` — Import a MLflow model version from a local path.
- `list` — List saved models in a project.
- `metrics` — Show performance metrics for a model version.
- `set-active-version` — Set the active version of a saved model.
- `set-definition` — Replace the saved-model settings from JSON.
- `set-flow-options` — Patch a saved model's flow options (virtualizable, rebuild behavior, ...).
- `set-metadata` — Update saved model description, short description, and/or tags.
- `set-publish-policy` — Set the publish policy on a saved model.
- `set-threshold` — Set the classification threshold of a binary saved model version.
- `usages` — Show where a saved model is used (recipes, endpoints, etc.).
- `versions` — List versions of a saved model.

### `model-comparison` — Manage DSS model comparisons.

- `add-model` — Add a model to a comparison.
- `create` — Create a new model comparison.
- `delete` — Delete a model comparison.
- `get` — Get model comparison settings.
- `list` — List model comparisons in a project.
- `remove-model` — Remove a model from a comparison.

### `evaluation-store` — Manage DSS evaluation stores (TABULAR, LLM, AGENT).

- `build` — Build a model evaluation store.
- `create` — Create a new evaluation store (TABULAR, LLM, or AGENT).
- `delete` — Delete a model evaluation store.
- `evaluations` — List evaluations in a model evaluation store.
- `get` — Show evaluation store settings.
- `latest` — Show the latest evaluation in a store.
- `list` — List evaluation stores in a project.

## Semantic Layer

### `semantic-model` — Manage DSS semantic models.

- `add-entity` — Add an entity to a semantic model version.
- `add-filter` — Add a named pseudo-SQL filter (WHERE-clause fragment) to an entity.
- `add-glossary-term` — Add a glossary term (auto-generates UUID).
- `add-golden-query` — Add a golden query (NL question → target SQL) as a few-shot example.
- `add-metric` — Add a named aggregate metric (pseudoSQL) to an entity.
- `add-relationship` — Add a relationship between two entities.
- `create` — Create a new semantic model.
- `create-version` — Create a new version of a semantic model.
- `delete` — Delete a semantic model.
- `distinct-values` — Show indexed distinct values for a semantic model version.
- `get` — Show semantic model definition.
- `get-version` — Show version settings (entities, relationships, glossary, etc.).
- `list` — List semantic models in a project.
- `list-entities` — List entities in a semantic model version (name, dataset, attribute count, PK).
- `list-filters` — List filters defined on an entity.
- `list-glossary` — List glossary terms in a semantic model version.
- `list-golden-queries` — List golden queries on a semantic model version.
- `list-metrics` — List metrics defined on an entity.
- `list-relationships` — List relationships in a semantic model version.
- `remove-entity` — Remove an entity from a semantic model version.
- `remove-filter` — Remove a filter from an entity by name.
- `remove-glossary-term` — Remove a glossary term by its label.
- `remove-golden-query` — Remove a golden query by name.
- `remove-metric` — Remove a metric from an entity by name.
- `remove-relationship` — Remove a relationship between two entities (matches either order).
- `set-active-version` — Set the active version of a semantic model.
- `set-manual-values` — Set or clear curated distinct values on an attribute.
- `set-version` — Update a version's settings from JSON.
- `sync-descriptions` — Backfill entity and attribute descriptions from backing dataset schemas.
- `update-index` — Trigger distinct values indexing for a semantic model version.
- `versions` — List versions of a semantic model.

## Extensions & Admin

### `plugin` — Manage DSS plugins.

- `components` — List a plugin's usable components (recipes, agent-tools, datasets,
- `create-code-env` — Create the managed code environment for a plugin.
- `delete` — Delete a plugin.
- `download` — Download a plugin as a ZIP archive.
- `get` — Show plugin details including version, code env, and dev status.
- `get-file` — Get the contents of a file in a dev plugin.
- `install-from-git` — Install a plugin from a Git repository.
- `install-from-store` — Install a plugin from the Dataiku plugin store.
- `list` — List installed plugins.
- `list-files` — List files in a dev plugin (hierarchical tree).
- `move-file` — Move a file or folder within a dev plugin.
- `push` — Push a plugin to DSS from a directory or ZIP archive.
- `put-file` — Write content to a file in a dev plugin.
- `recipes` — List plugin recipe types available for use with 'dku recipe create'.
- `rename-file` — Rename a file or folder in a dev plugin.
- `set-code-env` — Assign a code environment to a plugin.
- `settings` — View or update plugin settings.
- `update-code-env` — Rebuild a plugin's code environment after dependency changes.
- `update-from-git` — Update an installed plugin from a Git repository.
- `update-from-store` — Update an installed plugin from the Dataiku plugin store.
- `usages` — Show where a plugin's components are used across projects.

### `webapp` — Manage DSS web applications (list, start/stop, read/edit code).

- `create` — Create a new web application.
- `get-definition` — Get the raw definition of a web app as JSON (includes source code in params).
- `list` — List web applications in a project.
- `logs` — Read recent backend logs for a web app.
- `restart` — Restart a running web app backend.
- `set-definition` — Update a web app's definition from JSON (use get-definition to read current state first).
- `start` — Start or restart a web app backend.
- `status` — Show web app backend status.
- `stop` — Stop a web app backend.

### `admin` — DSS instance administration (admin only).

- `assets` — Enterprise Asset Library (read-only).
- `assets list-collections` — List enterprise asset collections.
- `assets list-prompts` — List enterprise prompts (optionally filtered by collection).
- `audit-log` — Write a custom entry to the DSS audit log.
- `azure-ad` — Azure AD / Microsoft Entra ID settings.
- `azure-ad get` — Dump current Azure AD settings as JSON.
- `azure-ad set` — Replace Azure AD settings.
- `catalog-index` — Trigger data catalog indexing for one or more connections.
- `code-env` — `code-env` is a TOP-LEVEL group — use `dku code-env ...`.
- `code-studio-template` — Code studio templates (admin visibility + lifecycle).
- `code-studio-template add-block` — Append (or insert) a block into a template's ``params.blocks[]``.
- `code-studio-template build` — Trigger an image build for a template.
- `code-studio-template get` — Get full template settings as JSON.
- `code-studio-template inspect-build` — Show last-build metadata: container configs, last-built timestamp,
- `code-studio-template list` — List registered code studio templates.
- `code-studio-template list-blocks` — List blocks (index, type, label) in a template.
- `code-studio-template remove-block` — Remove a block from a template by index.
- `code-studio-template set-block-params` — Set params on an existing block in ``params.blocks[]``.
- `code-studio-template set-dockerfile-append` — Replace the ``append_dockerfile`` block's content on a template.
- `connection` — `connection` is a TOP-LEVEL group — use `dku connection ...`.
- `disk-footprint` — Data directories footprint (read-only disk usage).
- `disk-footprint all` — Size of ALL DSS data directories (global + all projects). Can be slow.
- `disk-footprint global` — Size of instance-wide directories (code envs, plugins, libs).
- `disk-footprint project` — Size of a single project's owned directories.
- `disk-footprint unknown` — Directories in the data root that don't belong to DSS (leaked data).
- `get-log` — Get contents of a specific log file.
- `infra` — Infrastructure: base images, K8s policies.
- `infra apply-k8s-policies` — Apply Kubernetes namespace policies from general settings to the cluster.
- `infra push-base-images` — Push container-exec base images to the configured registry.
- `instance-info` — Show DSS instance information (node ID, type, version, etc).
- `ldap` — LDAP settings.
- `ldap get` — Dump current LDAP settings as JSON.
- `ldap set` — Replace LDAP settings.
- `license` — License status and upload.
- `license status` — Show licensing status (edition, expiry, user caps).
- `license upload` — Install a new DSS license. Overwrites active license — NO ROLLBACK.
- `llm-cost` — LLM Mesh cost-limiting counters (read-only).
- `llm-cost counters` — List all LLM cost-limiting counters and their current state.
- `llm-cost get` — Get a specific LLM cost counter by ID.
- `logs` — List available log files.
- `messaging` — Messaging channels (SMTP, Slack, Teams, etc).
- `messaging create` — Create a messaging channel.
- `messaging delete` — Delete a messaging channel.
- `messaging list` — List configured messaging channels.
- `messaging send-test` — Send a test message via a mail channel. Verifies creds.
- `sanity-check` — Run an instance sanity check.
- `settings` — DSS general settings (impersonation, container-exec).
- `settings get` — Dump general settings as JSON. Use as the starting point for 'set'.
- `settings set` — Replace DSS general settings. Always GET → edit → SET.
- `sso` — SSO (OpenID / SAML) settings.
- `sso get` — Dump current SSO settings as JSON.
- `sso set` — Replace SSO settings.
- `usage` — Show global usage summary (projects, datasets, users, etc).
- `users-sync` — External user/group sync from LDAP/Azure AD/custom.
- `users-sync fetch-external-groups` — List groups visible in the external directory.
- `users-sync fetch-external-users` — Search the external directory WITHOUT provisioning any DSS accounts.
- `users-sync resync-all` — Resync ALL existing users from their external supplier.

### `api-key` — Manage DSS global API keys (admin only).

- `create` — Create a new global API key.
- `delete` — Delete a global API key.
- `get` — Get an API key's definition.
- `list` — List all global API keys.
- `list-personal` — List personal API keys visible to the caller (admin sees all).

### `auth` — Manage DSS authentication profiles.

- `export-env` — Emit shell `export` lines for DKU_URL / DKU_API_KEY.
- `list` — List all configured profiles.
- `login` — Authenticate with a DSS instance.
- `logout` — Remove stored credentials.
- `status` — Show current authentication status.
- `switch` — Switch active profile.

### `user` — Manage DSS users.

- `activity` — Show user activity (last login, last session, etc).
- `add-secret` — Add or replace a user secret.
- `bulk-create` — Bulk-create users from JSON or CSV. Returns per-user status list.
- `bulk-edit` — Bulk-edit existing users. Each change dict MUST include 'login'.
- `create` — Create a DSS user.
- `delete` — Delete a DSS user.
- `get` — Get user details.
- `list` — List DSS users.

### `group` — Manage DSS groups.

- `create` — Create a DSS group.
- `delete` — Delete a DSS group.
- `get` — Show group details.
- `list` — List DSS groups.

### `config` — Manage CLI configuration.

- `get` — Get a configuration value.
- `get-safety` — Show the active safety mode and why it is active.
- `list` — Show all configuration.
- `list-profiles` — List configured auth profiles (alias for `dku auth list`).
- `path` — Print config file path.
- `set` — Set a configuration value.
- `set-safety` — Persist the safety mode to config.toml.
- `set-variables` — Set instance-level standard variables.
- `variables` — Show instance-level variables.

### `workspace` — Manage DSS workspaces.

- `create` — Create a new workspace.
- `delete` — Delete a workspace (requires admin rights).
- `get` — Get workspace settings.
- `list` — List all workspaces.
- `list-objects` — List objects in a workspace (datasets, dashboards, articles, etc).

## Govern

### `govern` — Govern commands: artifact, blueprint, signoff, role, custom-page, user, group, time-series, file.

- `artifact` — Manage Govern artifacts. Use 'govern blueprint fields' to discover field schemas.
- `artifact create` — Create a new Govern artifact.
- `artifact delete` — Delete a Govern artifact. Requires --confirm / --yes flag.
- `artifact get` — Get an artifact definition.
- `artifact list` — Search and list Govern artifacts.
- `artifact set-definition` — Update an artifact definition from JSON. Use set-field for single field updates.
- `artifact set-field` — Set a single field on an artifact without replacing the full definition.
- `artifact set-fields` — Set multiple fields on an artifact in a single round-trip.
- `blueprint` — Manage Govern blueprints. Use 'fields' subcommand to discover field schemas for artifact creation.
- `blueprint create` — Create a new blueprint (admin/architect). Provide definition as JSON.
- `blueprint create-signoff-config` — Create a signoff configuration on a workflow step.
- `blueprint create-version` — Create a new blueprint version (DRAFT by default).
- `blueprint delete` — Delete a blueprint (admin/architect). All versions and artifacts must be deleted first.
- `blueprint delete-signoff-config` — Delete the signoff configuration on a workflow step.
- `blueprint delete-version` — Delete a blueprint version. All artifacts using this version must be deleted first.
- `blueprint describe-version` — Pretty-print a blueprint version: fields, workflow, signoffs, views, hooks, and structural warnings.
- `blueprint export-version` — Export a blueprint version as a BlueprintVersionExport envelope.
- `blueprint fields` — List fields for a blueprint with type, list/scalar, required, and valid categories.
- `blueprint get` — Get a blueprint definition.
- `blueprint get-signoff-config` — Get the signoff configuration for a specific workflow step.
- `blueprint get-version` — Get a blueprint version definition.
- `blueprint get-version-definition` — Get a blueprint version definition.
- `blueprint import-version` — Import a blueprint version from an exported envelope.
- `blueprint list` — List all Govern blueprints.
- `blueprint list-hooks` — List logical hooks on a blueprint version.
- `blueprint list-signoff-configs` — List signoff configurations wired to a blueprint version's workflow steps.
- `blueprint list-versions` — List all versions of a blueprint, including DRAFT and ARCHIVED.
- `blueprint set-definition` — Update a blueprint definition (admin/architect).
- `blueprint set-signoff-config` — Update an existing signoff configuration on a workflow step.
- `blueprint set-version-definition` — Save a full BlueprintVersion definition (fields, workflow, hooks, views, actions).
- `blueprint set-version-status` — Update blueprint version status. Typical flow: DRAFT → ACTIVE (publish) → ARCHIVED (retire).
- `blueprint version-status` — Show the current status of a blueprint version (DRAFT/ACTIVE/ARCHIVED) and its trace.
- `custom-page` — Manage Govern custom pages.
- `custom-page create` — Create a new custom page (admin/architect). Provide definition as JSON.
- `custom-page delete` — Delete a custom page (admin/architect). Requires --confirm flag.
- `custom-page get` — Get a custom page definition.
- `custom-page list` — List all Govern custom pages.
- `custom-page set-definition` — Update a custom page definition (admin/architect).
- `file` — Manage Govern uploaded files.
- `file download` — Download an uploaded file from Govern.
- `file get` — Get metadata for an uploaded file.
- `file upload` — Upload a file to Govern.
- `group` — Manage Govern groups (admin).
- `group create` — Create a Govern group. Requires admin API key.
- `group delete` — Delete a Govern group. Requires --confirm flag and admin API key.
- `group get` — Get a group's definition. Requires admin API key.
- `group list` — List all Govern groups. Requires admin API key.
- `info` — Show Govern instance information.
- `role` — Manage Govern roles.
- `role create` — Create a new role (admin/architect). Provide definition as JSON.
- `role delete` — Delete a Govern role. Requires --confirm flag and admin/architect rights.
- `role get` — Get a role definition.
- `role list` — List all Govern roles.
- `role set-definition` — Update a role definition (admin/architect).
- `role-assignment` — Bind Govern roles to groups/users (per blueprint).
- `role-assignment delete` — Delete ALL role assignments for a blueprint. Requires --yes.
- `role-assignment get` — Show the full role-assignment rules for one blueprint.
- `role-assignment list` — List blueprint role assignments across all blueprints.
- `role-assignment set` — Bind a role to one or more groups/users for a blueprint.
- `signoff` — Manage Govern artifact sign-offs.
- `signoff add-approval` — Add approval to a sign-off.
- `signoff add-feedback` — Add feedback to a sign-off.
- `signoff create` — Create a sign-off for a workflow step. Required before updating status.
- `signoff delegate-approval` — Delegate approval to specific users for a sign-off.
- `signoff delegate-feedback` — Delegate feedback to specific users for a sign-off group.
- `signoff get` — Get sign-off details for an artifact workflow step.
- `signoff get-approval` — Get the current approval for a sign-off step.
- `signoff get-feedback` — Get a specific feedback review from a sign-off.
- `signoff list` — List sign-offs for an artifact.
- `signoff list-feedbacks` — List all feedbacks for a sign-off step.
- `signoff update-status` — Update the status of a sign-off.
- `time-series` — Manage Govern time series.
- `time-series create` — Create a new time series, optionally with initial datapoints.
- `time-series delete` — Delete time series values. Without --min/--max, deletes all values.
- `time-series get` — Get values from a time series.
- `time-series push-values` — Push datapoints into an existing time series.
- `user` — Manage Govern users (admin).
- `user create` — Create a Govern user. Requires admin API key.
- `user create-bulk` — Bulk create multiple users from JSON. Requires admin API key.
- `user delete-bulk` — Bulk delete multiple users. Requires admin API key and cascade confirmation.
- `user edit-bulk` — Bulk edit multiple users from JSON. Requires admin API key.
- `user get` — Get a user's settings. Requires admin API key.
- `user get-own` — Get your own user settings.
- `user list` — List all Govern users. Requires admin API key.
- `user list-activity` — List user activity (last login, etc.). Requires admin API key.
- `whoami` — Show current authenticated Govern user.
