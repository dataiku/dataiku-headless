# dku-cli Command Reference

Full reference for all `dku` commands. Read this when you need exact flags, argument names, or behavior details for a specific command group.

Global options available on the root CLI:

```bash
dku [--url URL] [--api-key KEY] [--profile NAME] [--quiet] [--errors text|json] COMMAND ...
```

## Table of Contents

- [auth](#auth) — login, logout, status, list, switch
- [config](#config) — set, get, list, path, variables, set-variables
- [project](#project) — list, get, inspect, export, create, delete, duplicate, set-metadata, variables, set-variables, permissions, set-permissions, tags
- [dataset](#dataset) — list, schema, head, build, create, upload, delete, clear, get-definition, set-definition, set-schema
- [recipe](#recipe) — list, get, get-definition, get-settings, set-settings, run, create, delete, set-code, get-code, set-definition, add-input, add-output, check-schema, apply-schema, create-embed, create-embed-docs, create-extract, create-llm-eval, create-agent-eval
- [scenario](#scenario) — list, run, abort, status, create, delete, get-definition, set-definition
- [job](#job) — list, run, status, log, abort, wait
- [plugin](#plugin) — list, push, settings
- [code-env](#code-env) — list, get, create, delete, update
- [connection](#connection) — list, create, test
- [model](#model) — list, get, versions
- [folder](#folder) — list, ls, upload, download
- [llm](#llm) — list, completion, embeddings
- [webapp](#webapp) — list, start, stop, status, get-definition, set-definition
- [dashboard](#dashboard) — list, get, create, delete, get-definition, set-definition
- [insight](#insight) — list, get, create, delete, get-definition, set-definition
- [macro](#macro) — list, run
- [user](#user) — list, create
- [flow](#flow) — graph, zones, create-zone, propagate, check, sources, successors
- [library](#library) — list, read, write, delete, mkdir
- [agent](#agent) — list, create, get, delete, wake-up, shutdown, status, add-tool, set-llm
- [agent-review](#agent-review) — list, create, get, delete, set-agent, set-llm, add-trait, list-tests, create-test, import-tests, export-tests, run, list-runs, results
- [agent-tool](#agent-tool) — list, get, create, set-definition, run, types, delete
- [code-studio](#code-studio) — list, create, get, delete, status, start, stop, change-owner, templates
- [git](#git) — status, log, diff, commit, pull, push, fetch, branches, create-branch, delete-branch, switch, tags, create-tag, remote
- [api-deployer](#api-deployer) — list-infras, list-services, get-service, list-deployments, create-deployment, get-deployment, update-deployment, delete-deployment, deployment-status
- [project-deployer](#project-deployer) — list-infras, list-projects, list-deployments, create-deployment, get-deployment, update-deployment, delete-deployment, deployment-status
- [notebook](#notebook) — list, get, create, delete, sessions, stop, clear-outputs, history
- [discussion](#discussion) — list, get, create, reply
- [knowledge](#knowledge) — list, create, get, set-definition, build, search, delete
- [bundle](#bundle) — list, export, download, import, activate
- [api-service](#api-service) — list, create, get, create-package, list-packages
- [wiki](#wiki) — list, create, get, update, delete
- [sql](#sql) — query
- [whoami](#whoami)

---

## auth

Manage DSS authentication profiles. No project needed.

```bash
dku auth login [--profile NAME] [--url URL] [--api-key KEY]
dku auth logout [--profile NAME] [--all]
dku auth status
dku auth list
dku auth switch PROFILE
```

- `login` without `--api-key` prompts interactively (also prompts for default project)
- `login` with all flags is non-interactive (CI/CD)
- `logout --all` removes all profiles
- Credentials stored in keyring (macOS Keychain, etc.) with file fallback

## config

Local CLI configuration. Stored in `~/.config/dku/config.toml` (platform-dependent via platformdirs).

```bash
dku config set KEY VALUE        # e.g., dku config set default_project MY_PROJ
dku config get KEY
dku config list
dku config path                 # Show config file location
dku config variables            # Show instance-level variables
dku config set-variables --set key=value  # Set instance-level variables
```

## project

```bash
dku project list [-o FORMAT]
dku project get PROJECT_KEY [-o FORMAT]
dku project inspect [PROJECT_KEY] [-P PROJECT] [-o FORMAT]
dku project export PROJECT_KEY [--dest DIR]
dku project create PROJECT_KEY --name NAME [--description DESC] [--if-not-exists] [-o FORMAT]
dku project delete PROJECT_KEY --yes
dku project duplicate PROJECT_KEY --target-key KEY --target-name NAME [-o FORMAT]
dku project set-metadata PROJECT_KEY [--name NAME] [--description DESC]
dku project variables [-P PROJECT] [-o FORMAT]
dku project set-variables [-P PROJECT] --set key=value [--set key2=value2]
dku project set-variables [-P PROJECT] --definition JSON
dku project permissions [-P PROJECT] [-o FORMAT]
dku project set-permissions [-P PROJECT] --definition JSON
dku project tags [-P PROJECT] [-o FORMAT]
```

- `delete` requires `--confirm`, `--yes`, or `-y` flag (safety guard)
- `create --if-not-exists` skips creation silently when the project already exists (idempotent)
- `set-metadata` updates project display name and/or description after creation
- `set-variables --set` modifies individual standard vars; `--definition` replaces all
- `inspect` gives a one-shot project summary: datasets, recipes, scenarios, flow sources, jobs, wiki, variables. Use `-o json` for machine-readable nested output

## dataset

All commands require project (`-P KEY` / `DKU_PROJECT` / config default).

```bash
dku dataset list [-P PROJECT] [-o FORMAT]
dku dataset schema DATASET_NAME [-P PROJECT] [-o FORMAT]
dku dataset head DATASET_NAME [-P PROJECT] [-n ROWS] [-C COLUMNS] [-o FORMAT]
dku dataset build DATASET_NAME [-P PROJECT] [--wait] [--type BUILD_TYPE] [--auto-update-schema]
dku dataset create DATASET_NAME [--type Filesystem] [-c CONNECTION] [-P PROJECT] [--if-not-exists] [--definition JSON]
dku dataset upload DATASET_NAME FILE [-P PROJECT] [--no-autodetect]
dku dataset delete DATASET_NAME [-P PROJECT] [--yes]
dku dataset clear DATASET_NAME [-P PROJECT]
dku dataset get-definition DATASET_NAME [-P PROJECT] [-o json]
dku dataset set-definition DATASET_NAME [-P PROJECT] --definition JSON
dku dataset set-schema DATASET_NAME [-P PROJECT] --definition JSON
```

- `upload` auto-detects format + schema after upload (calls `autodetect_settings`)
- `upload --no-autodetect` skips detection (if you'll set format manually)
- `head` defaults to 10 rows, override with `-n`. Use `--columns "col1,col2"` / `-C` to inspect specific columns before transforming
- `build --wait` blocks until job completes
- `build --type RECURSIVE_BUILD --auto-update-schema` builds upstream deps with automatic schema propagation
- `create --type UploadedFiles` for CSV upload targets
- `create` defaults to `--type Filesystem` with `-c filesystem_managed` if neither is specified
- `create --if-not-exists` skips creation silently when the dataset already exists (idempotent)
- `create --definition` supports create-time fields such as `type`, `params`, `formatType`, and `formatParams`

## recipe

### Visual recipe commands (PREFER these over Python)

```bash
dku recipe create-join NAME -i DS1 -i DS2 --output-ds OUT [--join-type LEFT] [-P PROJECT]  # Join
dku recipe create-group NAME -i DS --output-ds OUT [-k GROUP_COL] [-P PROJECT]  # Group/aggregate
dku recipe create-stack NAME -i DS1 -i DS2 --output-ds OUT [-P PROJECT]    # Stack/union
dku recipe create-distinct NAME -i DS --output-ds OUT [-P PROJECT]         # Deduplicate
dku recipe create-sort NAME -i DS --output-ds OUT [--sort-col COL] [-P PROJECT]  # Sort
dku recipe create-filter NAME -i DS --output-ds OUT [--filter-formula EXPR] [-P PROJECT]  # Filter/sample
dku recipe create-window NAME -i DS --output-ds OUT [--partition-col COL] [--order-col COL] [-P PROJECT]  # Window functions
dku recipe create-split NAME -i DS --output-ds OUT [-P PROJECT]            # Split by condition
dku recipe create-topn NAME -i DS --output-ds OUT [--sort-col COL] [--n N] [-P PROJECT]  # Top/bottom N rows
dku recipe create-pivot NAME -i DS --output-ds OUT [--row-key COL] [--column-key COL] [-P PROJECT]  # Pivot (long→wide)
dku recipe create-sampling NAME -i DS --output-ds OUT [--method METHOD] [--size N] [-P PROJECT]     # Random sample
dku recipe add-fold RECIPE --columns "c1,c2" --key-column KEY --value-column VAL [-P PROJECT]       # Fold (wide→long)
```

- `create-join` requires 2+ inputs. `--join-type LEFT|INNER|RIGHT|CROSS` (default LEFT). `--join-key col` or `--join-key left=right` (repeatable). For multi-input joins, prefix with index: `--join-key 1:col`
- `create-group -k col` sets first group key. Use `--agg col:sum,avg,count` to configure aggregation functions (repeatable). Without `--agg`, defaults to COUNT per group
- `create-pivot` transposes rows into columns. `--row-key` (repeatable), `--column-key`, `--value-column` optional
- `create-sampling` takes a sample. `--method`: RANDOM_FIXED_NB (default), RANDOM_FIXED_RATIO, HEAD_SEQUENTIAL, STRATIFIED. `--size N` or `--ratio 0.1`
- `add-fold` unpivots columns into rows (wide→long). Use `--columns` for explicit list or `--pattern` for regex match
- `create-sort --sort-col COL` sets sort columns at creation (repeatable). Use `COL` for ascending or `COL:desc` for descending
- `create-topn --sort-col COL` and `--n N` set the sort column(s) and row limit at creation
- `create-filter --filter-formula EXPR` (aliases: `--filter EXPR`, `-f EXPR`) sets the filter expression at creation using Dataiku formula syntax
- `create-window --partition-col COL` and `--order-col COL` set the window partition and ordering columns at creation
- `create-embed --embed-column COL` specifies the column to embed (alias for `--text-column`)
- Visual recipes auto-apply schema updates after creation. For manual control: `apply-schema RECIPE -P PROJ`

### Prepare recipe step commands

Manage processor steps in prepare recipes. Create a prepare recipe first with `dku recipe create NAME --type prepare -i INPUT --output-ds OUTPUT -c CONNECTION -P PROJECT`.

**ALWAYS prefer purpose-built processors over `CreateColumnWithGREL`.** See `skills/dataiku/references/prepare-processors.md` for the full processor catalog with param schemas.

#### Step management

```bash
dku recipe list-steps RECIPE [-P PROJECT] [-o FORMAT]                                    # List all steps
dku recipe add-step RECIPE --type TYPE --params JSON [--at INDEX] [--name NAME] [-P PROJECT]  # Add any processor
dku recipe get-step RECIPE --index INDEX [-P PROJECT] [-o FORMAT]                        # Get step details
dku recipe remove-step RECIPE --index INDEX [--index INDEX2] [-P PROJECT]                # Remove step(s)
dku recipe disable-step RECIPE --index INDEX [--index INDEX2] [-P PROJECT]               # Skip step
dku recipe enable-step RECIPE --index INDEX [--index INDEX2] [-P PROJECT]                # Re-enable step
```

- `list-steps` shows index, type, name, disabled status, target column. `-o json` for full params
- `add-step --type` accepts any of ~95 processor type IDs. `--params` accepts JSON string, `@file.json`, or `-` for stdin
- `add-step --at N` inserts at position N (0-based). Default: append to end
- `remove-step --index` is repeatable. Indices removed in descending order (no shifting issues)

#### Named shortcuts (prefer over add-step for these operations)

```bash
dku recipe add-formula RECIPE --expr EXPRESSION --column OUTPUT_COL [-P PROJECT]
dku recipe add-rename RECIPE {--from COL --to COL | --mappings JSON} [-P PROJECT]
dku recipe add-filter-rows RECIPE {--column COL --values CSV | --formula EXPR} [--action ACTION] [-P PROJECT]
dku recipe add-fill-empty RECIPE --column COL --value VALUE [-P PROJECT]
dku recipe add-delete-columns RECIPE --columns "COL1,COL2" [-P PROJECT]
dku recipe add-find-replace RECIPE --column COL --find VALUE --replace VALUE [--matching MODE] [-P PROJECT]
dku recipe add-fold RECIPE {--columns CSV | --pattern REGEX} --key-column KEY --value-column VAL [-P PROJECT]
dku recipe add-geopoint RECIPE --lat-column COL --lon-column COL [--output-column COL] [-P PROJECT]
dku recipe add-geodistance RECIPE --from-column COL --to-column COL [--output-column COL] [-P PROJECT]
```

- `add-formula` wraps `CreateColumnWithGREL`. **Use as LAST RESORT** — prefer purpose-built processors
- `add-rename --mappings` accepts JSON: `'{"old1":"new1","old2":"new2"}'` or `@file.json`
- `add-filter-rows --action`: `KEEP_ROW` (default), `REMOVE_ROW`, `CLEAR_CELL`, `FLAG`
- `add-filter-rows --formula` uses `FilterOnFormula`; `--column/--values` uses `FlagOnValue`
- `add-find-replace --matching`: `FULL_STRING` (default), `SUBSTRING`, `PATTERN` (regex)
- `add-fold --columns` uses `FoldColumnsByName`; `--pattern` uses `FoldColumnsByPattern`

#### Common add-step processors (no shortcut available)

| Task | Type | Example `--params` |
|------|------|-------------------|
| Uppercase/lowercase | `StringTransformer` | `'{"mode":"UPPERCASE","appliesTo":"SINGLE_COLUMN","columns":["city"]}'` |
| Parse dates | `DateParser` | `'{"appliesTo":"SINGLE_COLUMN","columns":["date"],"formats":["yyyy-MM-dd"],"lang":"auto","timezone_id":"UTC","outType":{"name":"out","type":"date"}}'` |
| Extract year/month | `DateComponentsExtractor` | `'{"column":"date","timezone_id":"UTC","outYearColumn":"year","outMonthColumn":"month"}'` |
| Date difference | `DateDifference` | `'{"input1":"start","compareTo":"NOW","output":"days_ago","outputUnit":"DAYS","timezone_id":"UTC"}'` |
| Concat columns | `ColumnsConcat` | `'{"columns":["first","last"],"join":" ","outputColumn":"full_name"}'` |
| Split column | `ColumnSplitter` | `'{"inCol":"name","separator":" ","outColPrefix":"name_","target":"COLUMNS","keepEmptyChunks":false,"limitOutput":false,"limit":0}'` |
| Copy column | `ColumnCopier` | `'{"inputColumn":"status","outputColumn":"status_bak"}'` |
| Remove empty rows | `RemoveRowsOnEmpty` | `'{"appliesTo":"ALL","columns":[],"keep":false}'` |
| Remove bad-type rows | `FilterOnBadType` | `'{"appliesTo":"SINGLE_COLUMN","columns":["price"],"type":"DoubleMeaning","action":"REMOVE_ROW","considerEmptyAsInvalid":false,"booleanMode":"AND"}'` |
| Flatten JSON | `JSONFlattener` | `'{"inCol":"metadata","flattenArrays":false,"maxDepth":10,"nullAsEmpty":true,"prefixOutputs":true,"separator":"_"}'` |
| If/then/else | `VisualIfRule` | See `prepare-processors.md` for full JSON structure |
| Bin numbers | `BinnerProcessor` | `'{"input":"age","output":"age_group","mode":"WIDTH","width":10.0,"bins":[]}'` |

### Code and management commands

```bash
dku recipe list [-P PROJECT] [-o FORMAT]
dku recipe get RECIPE_NAME [-P PROJECT] [-o FORMAT]
dku recipe get-definition RECIPE_NAME [-P PROJECT] [-o FORMAT]
dku recipe get-settings RECIPE_NAME [-P PROJECT] [-o json]
dku recipe set-settings RECIPE_NAME --settings JSON [-P PROJECT]
dku recipe run RECIPE_NAME [-P PROJECT] [--wait] [--type BUILD_TYPE] [--auto-update-schema]
dku recipe create RECIPE_NAME --type TYPE --input DS --output-ds DS [-P PROJECT]
dku recipe delete RECIPE_NAME [-P PROJECT]
dku recipe set-code RECIPE_NAME --code CODE|-|@file.py [-P PROJECT]
dku recipe get-code RECIPE_NAME [-P PROJECT] [-o text|json]
dku recipe set-definition RECIPE_NAME {--definition JSON | --payload JSON} [--deep-merge] [-P PROJECT]
dku recipe add-input RECIPE_NAME DS [--role main] [-P PROJECT]
dku recipe add-output RECIPE_NAME DS [--role main] [-P PROJECT]
dku recipe check-schema RECIPE_NAME [-P PROJECT] [-o FORMAT]
dku recipe apply-schema RECIPE_NAME [-P PROJECT] [-o FORMAT]
```

- `create --input`/`--input-ds`/`-i` all work. `--type`/`-t` for type, `--output-ds` for output
- `create` requires `--input` to exist. For code recipes (python, sql), `--output-ds` is auto-created. For visual recipes, both must pre-exist
- `set-code` accepts `--code @file.py` to read from file, or `--code -` to read from stdin
- `get-settings` returns full recipe settings as JSON including the visual recipe payload (sort orders, join keys, filter conditions, etc.). Unlike `get`, this includes the payload
- `set-settings` sets full recipe settings from JSON. Root-level keys update the definition; the `payload` key updates the visual recipe config (shallow merge). Use `get-settings` first to read, modify, then `set-settings` to update
- `set-definition --payload` updates visual recipe config (aggregations, join keys, filter conditions). `--definition` updates raw recipe definition (I/O, connection). Mutually exclusive
- `set-definition --deep-merge` (with `--payload`) recursively merges nested objects — patch one field without losing siblings. Default is shallow merge (top-level keys replaced). See `skills/dataiku/references/visual-recipe-payloads.md` for payload schemas
- **Only use `create -t python` when no visual recipe fits the task**

### GenAI recipe commands

```bash
dku recipe create-embed RECIPE_NAME --input DS --output-kb KB_ID --embedding-llm LLM_ID [--text-column COL] [--embed-column COL] [-P PROJECT]
dku recipe create-embed-docs RECIPE_NAME --input DS --output-kb KB_ID --embedding-llm LLM_ID [--vlm LLM_ID] [-P PROJECT]
dku recipe create-extract RECIPE_NAME --input DS --output-ds DS --vlm LLM_ID [-P PROJECT]
dku recipe create-llm-eval RECIPE_NAME --input DS --eval-store STORE_ID [--output-ds DS] [--output-metrics DS] [--task-type TYPE] [--metrics CSV] [--completion-llm LLM_ID] [--embedding-llm LLM_ID] [-P PROJECT]
dku recipe create-agent-eval RECIPE_NAME --input DS --eval-store STORE_ID [--output-ds DS] [--output-metrics DS] [--input-format TYPE] [--metrics CSV] [--completion-llm LLM_ID] [--embedding-llm LLM_ID] [-P PROJECT]
```

- `create-llm-eval` and `create-agent-eval` require any dataset passed via `--output-ds` or `--output-metrics` to already exist

## scenario

```bash
dku scenario list [-P PROJECT] [-o FORMAT]
dku scenario run SCENARIO_ID [-P PROJECT] [--wait]
dku scenario abort SCENARIO_ID [-P PROJECT]
dku scenario status SCENARIO_ID [-P PROJECT] [-o FORMAT]
dku scenario create NAME [--type step_based] [-P PROJECT] [--definition JSON] [--if-not-exists]
dku scenario delete SCENARIO_ID [-P PROJECT]
dku scenario get-definition SCENARIO_ID [-P PROJECT] [-o json]
dku scenario set-definition SCENARIO_ID --definition JSON [-P PROJECT]
```

## job

```bash
dku job list [-P PROJECT] [-o FORMAT]
dku job run --target NAME [--target NAME2] [-P PROJECT] [--type BUILD_TYPE] [--auto-update-schema] [--wait] [--timeout SECS] [--refresh-metastore]
dku job status JOB_ID [-P PROJECT] [-o FORMAT]
dku job log JOB_ID [-P PROJECT]
dku job abort JOB_ID [-P PROJECT]
dku job wait JOB_ID [-P PROJECT] [--timeout SECONDS]
```

- `run --target` is repeatable for building multiple outputs in one job
- `run --type` defaults to `NON_RECURSIVE_FORCED_BUILD`; use `RECURSIVE_BUILD` to build upstream deps
- `run --auto-update-schema` auto-updates output schemas before each recipe run — eliminates manual schema propagation
- `run --wait` blocks until completion; combine with `--timeout` for bounded waits

## plugin

Instance-level (no project needed).

```bash
dku plugin list [-o FORMAT]
dku plugin get PLUGIN_ID [-o FORMAT]
dku plugin push ZIP_PATH [--update/--install]
dku plugin delete PLUGIN_ID [--confirm/--yes/-y] [--force]
dku plugin settings PLUGIN_ID [-o FORMAT] [--set key=value ...]
dku plugin create-code-env PLUGIN_ID [--wait/--no-wait] [-o FORMAT]
dku plugin set-code-env PLUGIN_ID ENV_NAME
dku plugin update-code-env PLUGIN_ID [--wait/--no-wait]
dku plugin usages PLUGIN_ID [-P PROJECT] [-o FORMAT]
```

- `push` reads plugin ID from `plugin.json` inside ZIP, auto-detects update vs install
- `get` shows plugin details including version, code env, and dev status
- `create-code-env` creates and waits for the managed code env (use after first install)
- `set-code-env` assigns a code env to the plugin (use after create-code-env)
- `update-code-env` rebuilds the code env after dependency changes
- `usages` shows where plugin components are used; filter by project with `-P`
- First install flow: `push --install && create-code-env PLUGIN && set-code-env PLUGIN ENV`

## code-env

```bash
dku code-env list [-o FORMAT]
dku code-env get ENV_NAME [--lang PYTHON] [-o FORMAT]
dku code-env create ENV_NAME [--lang PYTHON] [--python-version VER]
dku code-env delete ENV_NAME [--lang PYTHON]
dku code-env update ENV_NAME [--lang PYTHON]
```

## connection

Admin-only. 403 if non-admin.

```bash
dku connection list [-o FORMAT]
dku connection create NAME --type TYPE [--definition JSON]
dku connection test CONNECTION_NAME
```

## model

```bash
dku model list [-P PROJECT] [-o FORMAT]
dku model get MODEL_ID [-P PROJECT] [-o FORMAT]
dku model versions MODEL_ID [-P PROJECT] [-o FORMAT]
```

## folder

Managed folders.

```bash
dku folder list [-P PROJECT] [-o FORMAT]
dku folder ls FOLDER_ID [-P PROJECT] [-o FORMAT]
dku folder upload FOLDER_ID FILE_PATH [-P PROJECT] [--remote-path PATH]
dku folder download FOLDER_ID REMOTE_PATH [-P PROJECT] [--dest DIR]
```

## llm

```bash
dku llm list [-P PROJECT] [--purpose PURPOSE] [-o FORMAT]
dku llm completion LLM_ID MESSAGE [-P PROJECT] [--system MSG] [--json-output] [-o text|json]
dku llm embeddings LLM_ID --text TEXT [-P PROJECT]
```

- LLM IDs follow `provider:connection:model` pattern (e.g., `openai:MyConnection:gpt-4o-mini`)
- `completion -o json` returns text + usage stats
- **Finding embedding models:** `dku llm list` defaults to `--purpose GENERIC_COMPLETION` which only shows chat/completion models. To find embedding models, you MUST use:
  ```bash
  dku llm list --purpose TEXT_EMBEDDING_EXTRACTION -P PROJECT
  ```
  Valid `--purpose` values: `GENERIC_COMPLETION`, `TEXT_EMBEDDING_EXTRACTION`, `IMAGE_EMBEDDING_EXTRACTION`, `RERANKING`, `IMAGE_GENERATION`
- `embeddings` rejects LLM IDs that are not available for `TEXT_EMBEDDING_EXTRACTION` in the target project

## webapp

No create via API (DSS UI only). But you can read/edit existing webapp code via get-definition/set-definition.

```bash
dku webapp list [-P PROJECT] [-o FORMAT]
dku webapp start WEBAPP_ID [-P PROJECT]
dku webapp stop WEBAPP_ID [-P PROJECT]
dku webapp status WEBAPP_ID [-P PROJECT]
dku webapp get-definition WEBAPP_ID [-P PROJECT] [-o json]
dku webapp set-definition WEBAPP_ID --definition JSON [-P PROJECT]
```

- `get-definition` returns full webapp settings including source code in `params` (html, css, js, python)
- `set-definition` accepts JSON string, `@file.json`, or `-` for stdin
- To edit webapp code: `get-definition` → modify `params` → `set-definition`

## dashboard

```bash
dku dashboard list [-P PROJECT] [-o FORMAT]
dku dashboard get DASHBOARD_ID [-P PROJECT] [-o FORMAT]
dku dashboard create NAME [-P PROJECT] [--definition JSON] [--if-not-exists]
dku dashboard delete DASHBOARD_ID [-P PROJECT]
dku dashboard get-definition DASHBOARD_ID [-P PROJECT] [-o json]
dku dashboard set-definition DASHBOARD_ID --definition JSON [-P PROJECT]
```

- No create via API for individual tiles/charts — manage via the raw JSON definition
- `get-definition` returns full dashboard JSON including `pages` array with embedded tiles
- Tiles live at `pages[i].grid.tiles` (NOT `pages[i].tiles`). Uses 36-column grid: `box: {top, left, width, height}`
- `set-definition` accepts JSON string, `@file.json`, or `-` for stdin
- See `skills/dataiku/references/dashboard-charts.md` for full chart JSON anatomy

## insight

```bash
dku insight list [-P PROJECT] [-o FORMAT]
dku insight get INSIGHT_ID [-P PROJECT] [-o FORMAT]
dku insight create NAME [--type TYPE] [--dataset DS] [-P PROJECT] [--definition JSON] [--if-not-exists]
dku insight delete INSIGHT_ID [-P PROJECT]
dku insight get-definition INSIGHT_ID [-P PROJECT] [-o json]
dku insight set-definition INSIGHT_ID --definition JSON [-P PROJECT]
dku insight validate INSIGHT_ID [-P PROJECT]
```

- `create` defaults to `--type dataset_table`. Common types: `chart`, `dataset_table`, `report`, `scenario_last_runs`, `metrics`, `eda`, `jupyter`
- `--dataset` / `--ds` binds the insight to a dataset (sets `params.datasetSmartName`). Required for chart/dataset_table types
- `--definition` overrides/extends creation info (merged with `--type` and name)
- `validate` checks chart column references against the dataset schema (client-side). Reports mismatches with fuzzy suggestions

## macro

```bash
dku macro list [-P PROJECT] [-o FORMAT]
dku macro run MACRO_ID [-P PROJECT]
```

## user

```bash
dku user list [-o FORMAT]
dku user create LOGIN --password PASS [--display-name NAME] [--email EMAIL] [--groups G1,G2]
```

## flow

```bash
dku flow graph [-P PROJECT] [-o FORMAT]
dku flow visualize [-P PROJECT]
dku flow zones [-P PROJECT] [-o FORMAT]
dku flow create-zone NAME [-P PROJECT]
dku flow propagate DATASET [-P PROJECT] [--stop-at RECIPE ...] [--mark-ok RECIPE ...] [--no-auto-rebuild] [-o FORMAT]
dku flow check [-P PROJECT] [-o FORMAT]
dku flow sources [DATASET] [-P PROJECT] [-o FORMAT]
dku flow successors NODE [-P PROJECT] [-o FORMAT]
```

- `sources` without arguments lists all flow source datasets. With a `DATASET` argument, lists upstream sources for that specific dataset
- `propagate` requires a dataset name as starting point for schema propagation
- `propagate --stop-at` stops propagation at the given recipe (repeatable)
- `propagate --mark-ok` marks a recipe as always OK during propagation (repeatable)
- `propagate --no-auto-rebuild` disables automatic rebuilds during propagation
- `check` runs schema + data consistency checks on the entire flow

## library

Project library files.

```bash
dku library list [-P PROJECT] [--path PATH] [-o FORMAT]
dku library read PATH [-P PROJECT]
dku library write PATH [-P PROJECT] --content CONTENT
dku library delete PATH [-P PROJECT]
dku library mkdir PATH [-P PROJECT]
```

- `write --content @file.py` reads from local file

## agent

```bash
dku agent list [-P PROJECT] [-o FORMAT]
dku agent create NAME [--type TOOLS_USING_AGENT] [-P PROJECT]
dku agent get AGENT_ID [-P PROJECT] [-o FORMAT]
dku agent delete AGENT_ID [-P PROJECT]
dku agent wake-up AGENT_ID [-P PROJECT]
dku agent shutdown AGENT_ID [-P PROJECT]
dku agent status AGENT_ID [-P PROJECT] [-o FORMAT]
dku agent add-tool AGENT_ID --tool TOOL_ID [-P PROJECT]
dku agent set-llm AGENT_ID --llm-id LLM_ID [-P PROJECT]
```

- `create --type` defaults to TOOLS_USING_AGENT. Options: TOOLS_USING_AGENT, PYTHON_AGENT, PLUGIN_AGENT, STRUCTURED_AGENT
- `set-llm` and `add-tool` operate on the active version

## agent-block

Manage visual agent block graphs (structured visual agents). Blocks live inside `TOOLS_USING_AGENT` with `mode: "BLOCKS_GRAPH"`.

```bash
dku agent-block list AGENT_ID [-P PROJECT] [--version VER] [-o FORMAT]
dku agent-block get AGENT_ID BLOCK_ID [-P PROJECT] [--version VER] [-o FORMAT]
dku agent-block add AGENT_ID --block/-b JSON [--set-start] [-P PROJECT] [--version VER]
dku agent-block remove AGENT_ID BLOCK_ID [-P PROJECT] [--version VER]
dku agent-block connect AGENT_ID --from BLOCK_A --to BLOCK_B [-P PROJECT] [--version VER]
dku agent-block disconnect AGENT_ID BLOCK_ID [-P PROJECT] [--version VER]
dku agent-block set-start AGENT_ID BLOCK_ID [-P PROJECT] [--version VER]
dku agent-block set-mode AGENT_ID SIMPLE|BLOCKS_GRAPH [-P PROJECT] [--version VER]
dku agent-block get-graph AGENT_ID [-P PROJECT] [--version VER] [-o json]
dku agent-block set-graph AGENT_ID --definition/-d JSON [-P PROJECT] [--version VER]
```

- `--block` and `--definition` accept inline JSON, `@file.json`, or `-` for stdin
- `add` auto-switches agent to `BLOCKS_GRAPH` mode if currently `SIMPLE`
- `add --set-start` sets the new block as starting block (auto-set for first block)
- `connect` sets `nextBlock` on the source block (for ROUTING clauses use `get-graph`/`set-graph`)
- `remove` warns about dangling references from other blocks
- `--version` defaults to active version
- 13 block types: SET_STATE_ENTRIES, LLM_REQUEST, ROUTING, EMIT_OUTPUT, STANDARD_REACT, MANUAL_TOOL_CALL, MANDATORY_TOOL_CALL, PARALLEL, FOR_EACH, PYTHON_CODE, REFLECTION, DELEGATE_TO_OTHER_AGENT, GENERATE_ARTIFACT
- See `docs/block-graph-api.md` for full schema of each block type

**Example: Build an SVA from scratch:**
```bash
dku agent create "My SVA" -P PROJ
dku agent-block add My_SVA --set-start -b '{"type":"SET_STATE_ENTRIES","id":"init","entriesToSet":[{"secret":false,"key":"status","value":"ready"}],"nextBlock":"classify"}' -P PROJ
dku agent-block add My_SVA -b '{"type":"LLM_REQUEST","id":"classify","llmId":"openai:conn:gpt-4.1-mini","passConversationHistory":true,"systemPromptAfterHistory":"Classify intent","completionSettings":{"stopSequences":[],"outputTrajectory":true},"streamOutput":false,"outputMode":"SAVE_TO_STATE","outputStateKey":"intent","nextBlock":"respond"}' -P PROJ
dku agent-block add My_SVA -b '{"type":"EMIT_OUTPUT","id":"respond","templateType":"CEL_EXPANSION","template":"Intent: {{state.intent}}","addToMessages":true}' -P PROJ
dku agent-block list My_SVA -P PROJ
```

## agent-review

Manage agent reviews — evaluate agent quality with LLM-as-judge traits, test cases, and evaluation runs.

```bash
dku agent-review list [-P PROJECT] [-o FORMAT]
dku agent-review create NAME [-P PROJECT]
dku agent-review get REVIEW_ID [-P PROJECT] [-o FORMAT]
dku agent-review delete REVIEW_ID [-P PROJECT]
dku agent-review set-agent REVIEW_ID --agent AGENT_ID [-P PROJECT]
dku agent-review set-llm REVIEW_ID --llm LLM_ID [-P PROJECT]
dku agent-review add-trait REVIEW_ID --name NAME [--description DESC] [--criteria CRITERIA] [--llm LLM_ID] [-P PROJECT]
dku agent-review list-tests REVIEW_ID [-P PROJECT] [-o FORMAT]
dku agent-review create-test REVIEW_ID --query QUERY [--reference ANSWER] [--expectations EXPECT] [-P PROJECT]
dku agent-review import-tests REVIEW_ID --dataset DS --query-column COL [--reference-column COL] [--expectations-column COL] [--top-n N] [-P PROJECT]
dku agent-review export-tests REVIEW_ID --dataset DS [--create-new] [--connection CONN] [-P PROJECT]
dku agent-review run REVIEW_ID [--wait/--no-wait] [--name NAME] [-P PROJECT]
dku agent-review list-runs REVIEW_ID [-P PROJECT] [-o FORMAT]
dku agent-review results REVIEW_ID --run RUN_ID [-P PROJECT] [-o FORMAT]
```

- `REVIEW_ID` accepts review ID or name (resolved automatically)
- `add-trait`: `--criteria` is the evaluation prompt for the LLM judge (e.g. "Does the answer directly address the user's question?")
- `import-tests`: bulk-creates test cases from dataset rows; each row becomes one test
- `run`: executes all tests, sending each query to the agent and scoring responses against configured traits
- `results`: shows per-test evaluation results including trait pass/fail status

---

## agent-tool

Manage agent tools (create, configure, run, inspect).

```bash
dku agent-tool list [-P PROJECT] [-o FORMAT]
dku agent-tool get TOOL_ID [-P PROJECT] [-o FORMAT]
dku agent-tool create NAME --type TYPE [--knowledge-bank KB_ID] [--dataset DS] [--llm LLM_ID] [-P PROJECT]
dku agent-tool set-definition TOOL_ID --definition JSON [-P PROJECT]
dku agent-tool run TOOL_ID [--input JSON] [-P PROJECT] [-o FORMAT]
dku agent-tool types [-o FORMAT]
dku agent-tool delete TOOL_ID [-P PROJECT]
```

- `create --type` accepts built-in types (`DatasetRowLookup`, `VectorStoreSearch`, `LLMMeshLLMQuery`) or plugin types (`Custom_agent_tool_<plugin>_<tool>`). Run `dku agent-tool types` to list built-in types.
- `create --knowledge-bank` / `--kb` required for `VectorStoreSearch`.
- `create --dataset` / `--ds` sets `datasetSmartName` for `DatasetRowLookup`.
- `create --llm` sets `llmId` for `LLMMeshLLMQuery`.
- `set-definition` accepts JSON as literal string, `@file.json`, or `-` for stdin. Merges into existing settings (shallow — replaces top-level keys).
- `types` does NOT accept `-P` (project-independent).
- For custom Python tools, build a plugin with `python-agent-tools/` and deploy via `dku plugin push`.

## code-studio

Manage Code Studio instances — interactive development environments in DSS.

```bash
dku code-studio list [-P PROJECT] [-o FORMAT]
dku code-studio create NAME --template TEMPLATE_ID [-P PROJECT]
dku code-studio get CS_ID [-P PROJECT] [-o FORMAT]
dku code-studio delete CS_ID [-P PROJECT]
dku code-studio status CS_ID [-P PROJECT] [-o FORMAT]
dku code-studio start CS_ID [--wait/--no-wait] [-P PROJECT]
dku code-studio stop CS_ID [--wait/--no-wait] [-P PROJECT]
dku code-studio change-owner CS_ID --owner NEW_OWNER [-P PROJECT]
dku code-studio templates [-o FORMAT]
```

- `templates` is a client-level command (no `--project` needed) — lists available templates
- `start`/`stop` return DSSFuture; `--wait` (default) blocks until state change completes
- States: STOPPED, STARTING, RUNNING, STOPPING
- Use `dku code-studio templates` to find the `TEMPLATE_ID` for `create`

---

## api-deployer

Deploy API services to API Nodes. No `--project` needed — operates at instance level.

```bash
dku api-deployer list-infras [-o FORMAT]
dku api-deployer list-services [-o FORMAT]
dku api-deployer get-service SERVICE_ID [-o FORMAT]
dku api-deployer list-deployments [-o FORMAT]
dku api-deployer create-deployment --id ID --service SERVICE_ID --infra INFRA_ID --version VERSION
dku api-deployer get-deployment DEPLOYMENT_ID [-o FORMAT]
dku api-deployer update-deployment DEPLOYMENT_ID [--wait/--no-wait]
dku api-deployer delete-deployment DEPLOYMENT_ID
dku api-deployer deployment-status DEPLOYMENT_ID [-o FORMAT]
```

---

## project-deployer

Deploy project bundles to Automation Nodes. No `--project` needed — operates at instance level.

```bash
dku project-deployer list-infras [-o FORMAT]
dku project-deployer list-projects [-o FORMAT]
dku project-deployer list-deployments [-o FORMAT]
dku project-deployer create-deployment --id ID --project-key KEY --infra INFRA_ID --bundle BUNDLE_ID
dku project-deployer get-deployment DEPLOYMENT_ID [-o FORMAT]
dku project-deployer update-deployment DEPLOYMENT_ID [--wait/--no-wait]
dku project-deployer delete-deployment DEPLOYMENT_ID
dku project-deployer deployment-status DEPLOYMENT_ID [-o FORMAT]
```

---

## git

Manage DSS project version control (branches, commits, tags, push/pull).

```bash
dku git status [-P PROJECT] [-o FORMAT]
dku git log [--count N] [-P PROJECT] [-o FORMAT]
dku git diff [--from COMMIT] [--to COMMIT] [-P PROJECT] [-o FORMAT]
dku git commit -m MESSAGE [-P PROJECT]
dku git pull [--branch NAME] [-P PROJECT] [-o FORMAT]
dku git push [--branch NAME] [-P PROJECT] [-o FORMAT]
dku git fetch [-P PROJECT] [-o FORMAT]
dku git branches [--remote] [-P PROJECT] [-o FORMAT]
dku git create-branch NAME [--from COMMIT] [-P PROJECT]
dku git delete-branch NAME [--force] [--remote] [-P PROJECT]
dku git switch BRANCH [-P PROJECT] [-o FORMAT]
dku git tags [-P PROJECT] [-o FORMAT]
dku git create-tag NAME [--ref REF] [-m MESSAGE] [-P PROJECT]
dku git remote [--set URL] [--name NAME] [-P PROJECT] [-o FORMAT]
```

- `commit`: DSS auto-adds untracked files before committing
- `remote`: reads remote URL by default; use `--set URL` to update
- `branches --remote`: lists remote tracking branches
- All commands require `--project` since git is per-project in DSS

---

## notebook

Manage Jupyter and SQL notebooks.

```bash
dku notebook list [--type jupyter|sql] [-P PROJECT] [-o FORMAT]
dku notebook get NAME [-P PROJECT] [-o FORMAT]
dku notebook create NAME [-P PROJECT]
dku notebook delete NAME [-P PROJECT]
dku notebook sessions [-P PROJECT] [-o FORMAT]
dku notebook stop NAME [--session SESSION_ID] [-P PROJECT]
dku notebook clear-outputs NAME [-P PROJECT]
dku notebook history NAME [-P PROJECT] [-o FORMAT]
```

- `list` combines Jupyter + SQL notebooks; use `--type` to filter
- `history` is for SQL notebooks only
- `sessions` lists all running notebook kernels in the project
- `stop` kills a notebook's kernel; `--session` targets a specific session

---

## discussion

Manage discussions/comments on any DSS object.

```bash
dku discussion list --type TYPE --name NAME [-P PROJECT] [-o FORMAT]
dku discussion get DISCUSSION_ID --type TYPE --name NAME [-P PROJECT] [-o FORMAT]
dku discussion create --type TYPE --name NAME --topic TOPIC --message MSG [-P PROJECT]
dku discussion reply DISCUSSION_ID --type TYPE --name NAME --message MSG [-P PROJECT]
```

- `--type`: dataset, recipe, scenario, model, dashboard, insight
- `--name`: the object's name/ID to attach the discussion to
- Works on any DSS object that supports `get_object_discussions()`

---

## knowledge

Knowledge banks.

```bash
dku knowledge list [-P PROJECT] [-o FORMAT]
dku knowledge create NAME --embedding-llm LLM_ID [--vector-store-type CHROMA|FAISS|PINECONE|...] [--if-not-exists] [-P PROJECT]
dku knowledge get KB_REF [-P PROJECT] [-o FORMAT]
dku knowledge set-definition KB_REF --definition JSON|@file.json|- [-P PROJECT]
dku knowledge build KB_REF [-P PROJECT] [--wait]
dku knowledge search KB_REF --query TEXT [--max N] [-P PROJECT] [-o FORMAT]
dku knowledge delete KB_REF [-P PROJECT]
```

- All commands (except `list`, `create`) accept knowledge bank ID **or name** — name is resolved via list fallback
- `create` requires `--embedding-llm` (use `dku llm list --purpose TEXT_EMBEDDING_EXTRACTION` to find one)
- `create --vector-store-type` defaults to CHROMA. Options: CHROMA, FAISS, PINECONE, ELASTICSEARCH, AZURE_AI_SEARCH, VERTEX_AI_GCS_BASED, QDRANT_LOCAL, MILVUS_LOCAL, MILVUS_REMOTE
- `set-definition` merges JSON into current settings (shallow merge). Get current: `dku knowledge get KB -o json`
- `get` expects JSON from DSS; on getitstarted instances the sleep/wake page can intercept the request and return HTML instead

## bundle

```bash
dku bundle list [-P PROJECT] [-o FORMAT]
dku bundle export BUNDLE_ID [-P PROJECT]
dku bundle download BUNDLE_ID [-P PROJECT] [--dest DIR]
dku bundle import FILE [-P PROJECT]
dku bundle activate BUNDLE_ID [-P PROJECT]
```

- `activate` calls `preload_bundle` then `activate_bundle`

## api-service

```bash
dku api-service list [-P PROJECT] [-o FORMAT]
dku api-service create SERVICE_ID [-P PROJECT]
dku api-service get SERVICE_ID [-P PROJECT] [-o FORMAT]
dku api-service create-package SERVICE_ID [-P PROJECT]
dku api-service list-packages SERVICE_ID [-P PROJECT] [-o FORMAT]
```

## wiki

```bash
dku wiki list [-P PROJECT] [-o FORMAT]
dku wiki create TITLE [--body TEXT] [-P PROJECT] [--if-not-exists]
dku wiki get ARTICLE_ID [-P PROJECT] [-o FORMAT]
dku wiki update ARTICLE_ID [--body TEXT] [--title TEXT] [-P PROJECT]
dku wiki delete ARTICLE_ID --confirm [-P PROJECT]
```

- `update` changes body and/or title. Body accepts literal, `@file.md`, or `-` for stdin.
- `delete` requires `--confirm` / `--yes` / `-y` flag.

## sql

```bash
dku sql query SQL --connection CONN [-o FORMAT]
```

- `query` accepts SQL string or `@file.sql`

## whoami

```bash
dku whoami
```

Shows: user, DSS URL, DSS version, groups.
