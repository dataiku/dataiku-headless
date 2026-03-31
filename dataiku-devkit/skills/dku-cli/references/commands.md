# dku-cli Command Reference

Full reference for all `dku` commands. Read this when you need exact flags, argument names, or behavior details for a specific command group.

Global options available on the root CLI:

```bash
dku [--url URL] [--api-key KEY] [--profile NAME] [--quiet] [--errors text|json] COMMAND ...
```

## Table of Contents

- [auth](#auth) — login, logout, status, list, switch
- [config](#config) — set, get, list, path, variables, set-variables
- [project](#project) — list, get, export, create, delete, duplicate, set-metadata, variables, set-variables, permissions, set-permissions, tags
- [dataset](#dataset) — list, schema, head, build, create, upload, delete, clear, get-definition, set-definition, set-schema
- [dq](#dq) — list, create, compute, status, results, delete, project-status
- [recipe](#recipe) — list, get, run, create, delete, set-code, get-code, set-definition, add-input, add-output, check-schema, apply-schema, create-join, create-geojoin, create-fuzzy-join, create-group, create-stack, create-distinct, create-sort, create-filter, create-window, create-split, create-topn, create-pivot, create-sampling, create-embed, create-embed-docs, create-extract, create-llm-eval, create-agent-eval, add-formula, add-rename, add-filter-rows, add-fill-empty, add-delete-columns, add-find-replace, add-fold, add-geopoint, add-geodistance, list-steps, get-step, remove-step, enable-step, disable-step
- [scenario](#scenario) — list, run, abort, status, create, delete, get-definition, set-definition
- [job](#job) — list, run, status, log, abort, wait
- [plugin](#plugin) — list, push, settings, recipes
- [code-env](#code-env) — list, get, create, delete, update
- [connection](#connection) — list, create, test
- [model](#model) — list, get, versions
- [folder](#folder) — list, create, ls, upload, download
- [llm](#llm) — list, completion, embeddings
- [webapp](#webapp) — list, start, stop, status, get-definition, set-definition
- [dashboard](#dashboard) — list, get, create, delete, get-definition, set-definition
- [insight](#insight) — list, get, create, delete, get-definition, set-definition
- [macro](#macro) — list, run
- [user](#user) — list, create
- [flow](#flow) — graph, zones, create-zone, propagate, check, sources, successors
- [library](#library) — list, read, write, delete, mkdir
- [agent](#agent) — list, create, get, delete, wake-up, shutdown, status, add-tool, set-llm
- [agent-tool](#agent-tool) — list, get, run, delete
- [knowledge](#knowledge) — list, create, get, build, search, delete
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

## dataset

All commands require project (`-P KEY` / `DKU_PROJECT` / config default).

```bash
dku dataset list [-P PROJECT] [-o FORMAT]
dku dataset schema DATASET_NAME [-P PROJECT] [-o FORMAT]
dku dataset head DATASET_NAME [-P PROJECT] [-n ROWS] [-o FORMAT]
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
- `head` defaults to 10 rows, override with `-n`
- `build --wait` blocks until job completes
- `build --type RECURSIVE_BUILD --auto-update-schema` builds upstream deps with automatic schema propagation
- `create --type UploadedFiles` for CSV upload targets
- `create` defaults to `--type Filesystem` with `-c filesystem_managed` if neither is specified
- `create --if-not-exists` skips creation silently when the dataset already exists (idempotent)
- `create --definition` supports create-time fields such as `type`, `params`, `formatType`, and `formatParams`
- `create --type UploadedFiles --connection NAME` for cloud DSS instances that require explicit upload connection

## dq

Data quality rules on DSS datasets. Requires DSS 14.5+.

```bash
dku dq list DATASET [-P PROJECT] [-o FORMAT]
dku dq create DATASET [--type TYPE] [--column COL] [--min N] [--max N] [--name NAME] [-P PROJECT]
dku dq create DATASET --config JSON [-P PROJECT]
dku dq compute DATASET [-P PROJECT] [--wait|--no-wait] [--partition PART] [--rule-id ID]
dku dq status DATASET [-P PROJECT] [-o FORMAT]
dku dq results DATASET [-P PROJECT] [--partition PART] [-o FORMAT]
dku dq delete DATASET --rule-id ID [--yes] [-P PROJECT]
dku dq project-status [-P PROJECT] [--all] [-o FORMAT]
```

- `create --type`: `record-count`, `not-empty`, `value-in-range`, `column-min`, `column-max`, `column-avg`, `column-sum`
- `value-in-range` creates TWO rules (ColumnMinInRangeRule + ColumnMaxInRangeRule)
- Column rules require `--column`. Range rules use `--min` and/or `--max` (warning-level thresholds)
- `create --config` for raw JSON (any of 13+ DSS rule types including median, stddev, schema, file-size)
- `compute --wait` (default) blocks until computation finishes
- `compute --rule-id` computes a single rule only
- `project-status` shows monitored datasets only by default; `--all` includes non-monitored
- `not-empty` (ColumnNotEmptyRule) has a known DSS 14.5 beta bug — use `column-min --min 1` as workaround

## recipe

### Visual recipe commands (PREFER these over Python)

```bash
dku recipe create-join NAME -i DS1 -i DS2 --output-ds OUT [-P PROJECT]     # Join (auto-detects keys)
dku recipe create-geojoin NAME -i DS1 -i DS2 --output-ds OUT [--operator OP] [--distance N] [-P PROJECT]  # Geo join
dku recipe create-fuzzy-join NAME -i DS1 -i DS2 --output-ds OUT [--fuzzy-key COL] [-P PROJECT]  # Fuzzy/approx join
dku recipe create-group NAME -i DS --output-ds OUT [-k GROUP_COL] [--agg COL:FUNCS] [-P PROJECT]  # Group/aggregate
dku recipe create-stack NAME -i DS1 -i DS2 --output-ds OUT [-P PROJECT]    # Stack/union
dku recipe create-distinct NAME -i DS --output-ds OUT [-P PROJECT]         # Deduplicate
dku recipe create-sort NAME -i DS --output-ds OUT [--sort-col COL:desc] [-P PROJECT]  # Sort
dku recipe create-filter NAME -i DS --output-ds OUT [--filter-formula GREL] [-P PROJECT]  # Filter
dku recipe create-window NAME -i DS --output-ds OUT [--partition-col COL] [--order-col COL:desc] [-P PROJECT]  # Window functions
dku recipe create-split NAME -i DS --output-ds OUT [-P PROJECT]            # Split by condition
dku recipe create-topn NAME -i DS --output-ds OUT [-P PROJECT]             # Top/bottom N rows
dku recipe create-pivot NAME -i DS --output-ds OUT [-P PROJECT]            # Pivot/crosstab
dku recipe create-sampling NAME -i DS --output-ds OUT [-P PROJECT]         # Sample rows
```

- `create-join` requires 2+ inputs. Use `--join-key col` or `--join-key left=right` to set join conditions (repeatable for composite keys). Auto-detects from matching column names if `--join-key` omitted
- `create-geojoin` requires exactly 2 inputs. `--operator`: WITHIN_DISTANCE (default), CONTAINS, INTERSECTS, etc. `--distance` in meters (for WITHIN_DISTANCE). `--geo-column col1,col2` to specify geo columns
- `create-fuzzy-join` requires exactly 2 inputs. `--fuzzy-key col` for the column to match on. `--method`: NORMALIZED_LEVENSHTEIN (default), BEIDER_MORSE, DOUBLE_METAPHONE, SOUNDEX
- `create-group -k col` sets first group key. Use `--agg col:sum,avg,count` to configure aggregation functions (repeatable). Without `--agg`, defaults to COUNT per group
- `create-sort --sort-col col:desc` for descending, `--sort-col col` for ascending (repeatable)
- `create-filter --filter-formula GREL` sets the filter expression (e.g. `"price > 100"`)
- `create-window --partition-col col` sets partitioning, `--order-col col:desc` sets ordering (both repeatable)
- Visual recipes auto-apply schema updates after creation. For manual control: `apply-schema RECIPE -P PROJ`
- Configure additional visual recipe details (join type, sort order, filter conditions) in the DSS UI or via `set-definition`

### Prepare recipe step commands

```bash
dku recipe add-formula RECIPE --column COL --expr GREL [-P PROJECT]              # Computed column
dku recipe add-rename RECIPE --from OLD --to NEW [-P PROJECT]                     # Rename column
dku recipe add-rename RECIPE --mappings '{"old1":"new1","old2":"new2"}' [-P PROJECT]  # Bulk rename
dku recipe add-filter-rows RECIPE --formula GREL --action KEEP_ROW|REMOVE_ROW [-P PROJECT]  # Filter by formula
dku recipe add-filter-rows RECIPE --column COL --values "a,b" --action KEEP_ROW [-P PROJECT]  # Filter by value
dku recipe add-fill-empty RECIPE --column COL --value VAL [-P PROJECT]            # Fill nulls
dku recipe add-delete-columns RECIPE --columns "col1,col2" [-P PROJECT]           # Drop columns
dku recipe add-find-replace RECIPE --column COL --find X --replace Y [--matching SUBSTRING] [-P PROJECT]  # Find/replace
dku recipe add-fold RECIPE --columns "a,b,c" --key-column K --value-column V [-P PROJECT]  # Unpivot (wide→long)
dku recipe add-geopoint RECIPE --lat-column LAT --lon-column LON [-c OUTPUT_COL] [-P PROJECT]  # Create geopoint
dku recipe add-geodistance RECIPE --from-column A --to-column B [-c OUTPUT_COL] [-P PROJECT]  # Geo distance
dku recipe list-steps RECIPE [-P PROJECT] [-o FORMAT]     # List all steps
dku recipe get-step RECIPE INDEX [-P PROJECT] [-o FORMAT]  # Get step by index
dku recipe remove-step RECIPE INDEX [INDEX ...] [-P PROJECT]  # Remove step(s)
dku recipe enable-step RECIPE INDEX [INDEX ...] [-P PROJECT]  # Enable step(s)
dku recipe disable-step RECIPE INDEX [INDEX ...] [-P PROJECT]  # Disable step(s)
```

- All step commands require the recipe to be of type `prepare` (or `shaker`)
- `add-formula --expr` accepts GREL expressions. `--column` is the output column name
- `add-filter-rows --action`: KEEP_ROW, REMOVE_ROW, CLEAR_CELL, FLAG
- `add-find-replace --matching`: FULL_STRING (default), SUBSTRING, PATTERN (regex)
- `add-fold --pattern REGEX` can be used instead of `--columns` to match column names by regex
- Step indices are 0-based

### Code and management commands

```bash
dku recipe list [-P PROJECT] [-o FORMAT]
dku recipe get RECIPE_NAME [-P PROJECT] [-o FORMAT]
dku recipe run RECIPE_NAME [-P PROJECT] [--wait] [--type BUILD_TYPE] [--auto-update-schema]
dku recipe create RECIPE_NAME --type TYPE --input DS --output-ds DS [-P PROJECT]
dku recipe delete RECIPE_NAME [-P PROJECT]
dku recipe set-code RECIPE_NAME --code CODE|-|@file.py [-P PROJECT]
dku recipe get-code RECIPE_NAME [-P PROJECT] [-o text|json]
dku recipe set-definition RECIPE_NAME --definition JSON [-P PROJECT]
dku recipe add-input RECIPE_NAME DS [--role main] [-P PROJECT]
dku recipe add-output RECIPE_NAME DS [--role main] [-P PROJECT]
dku recipe check-schema RECIPE_NAME [-P PROJECT] [-o FORMAT]
dku recipe apply-schema RECIPE_NAME [-P PROJECT] [-o FORMAT]
```

- `create --input`/`--input-ds`/`-i` all work. `--type`/`-t` for type, `--output-ds` for output
- `create` requires `--input` to exist. For code recipes (python, sql), `--output-ds` is auto-created. For visual recipes, both must pre-exist
- `set-code` accepts `--code @file.py` to read from file, or `--code -` to read from stdin
- **Only use `create -t python` when no visual recipe fits the task**

### GenAI recipe commands

```bash
dku recipe create-embed RECIPE_NAME --input DS --output-kb KB_ID --embedding-llm LLM_ID [-P PROJECT]
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
dku plugin recipes PLUGIN_ID [-o FORMAT]
```

- `push` reads plugin ID from `plugin.json` inside ZIP, auto-detects update vs install. **Warns about recipe type registration** — DSS may need restart for new recipe types
- `get` shows plugin details including version, code env, and dev status
- `create-code-env` creates and waits for the managed code env (use after first install)
- `set-code-env` assigns a code env to the plugin (use after create-code-env)
- `update-code-env` rebuilds the code env after dependency changes
- `usages` shows where plugin components are used; filter by project with `-P`
- `recipes` reads custom recipe types from dev plugin files; shows `CustomCode_{id}_{recipe}` format type IDs
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
dku model set-active-version MODEL_ID VERSION_ID [-P PROJECT]
dku model metrics MODEL_ID [-P PROJECT] [-o FORMAT]
dku model delete-version MODEL_ID VERSION_ID [-P PROJECT]
```

## ml

AutoML task management — create, train, evaluate, and deploy ML models.

```bash
dku ml create-prediction DATASET TARGET [--prediction-type REGRESSION|TWO_CLASS|MULTICLASS] [--guess-policy DEFAULT] [--backend PY_MEMORY] [-P PROJECT] [-o FORMAT]
dku ml create-clustering DATASET [--guess-policy DEFAULT] [--backend PY_MEMORY] [-P PROJECT] [-o FORMAT]
dku ml create-timeseries DATASET TARGET TIME_COL [--identifiers COL ...] [--guess-policy DEFAULT] [-P PROJECT] [-o FORMAT]
dku ml create-causal DATASET OUTCOME TREATMENT [--prediction-type REGRESSION|TWO_CLASS] [-P PROJECT] [-o FORMAT]
dku ml list [-P PROJECT] [-o FORMAT]
dku ml status ANALYSIS_ID MLTASK_ID [-P PROJECT] [-o FORMAT]
dku ml train ANALYSIS_ID MLTASK_ID [--session-name NAME] [--wait/--no-wait] [-P PROJECT] [-o FORMAT]
dku ml models ANALYSIS_ID MLTASK_ID [--session SESSION] [--algorithm ALG] [-P PROJECT] [-o FORMAT]
dku ml details ANALYSIS_ID MLTASK_ID MODEL_ID [-P PROJECT] [-o FORMAT]
dku ml deploy ANALYSIS_ID MLTASK_ID MODEL_ID [--name NAME] [--train-dataset DS] [--test-dataset DS] [--redo-optimization] [-P PROJECT] [-o FORMAT]
dku ml redeploy ANALYSIS_ID MLTASK_ID MODEL_ID [--saved-model-id ID] [--recipe-name NAME] [--activate] [--redo-optimization] [-P PROJECT] [-o FORMAT]
dku ml settings ANALYSIS_ID MLTASK_ID [-P PROJECT] [-o FORMAT]
dku ml algorithms ANALYSIS_ID MLTASK_ID [-P PROJECT] [-o FORMAT]
dku ml set-algorithm ANALYSIS_ID MLTASK_ID [--enable ALG ...] [--disable ALG ...] [--disable-all] [-P PROJECT]
dku ml delete ANALYSIS_ID MLTASK_ID [-P PROJECT]
```

- `create-prediction` blocks during guess phase (5-30s). Returns `{analysisId, mltaskId}` needed for subsequent commands
- `train --wait` (default) blocks until training completes; `--no-wait` starts async
- `deploy` creates a saved model + train recipe in the flow. Returns `{savedModelId, trainRecipeName}`
- `redeploy` updates an existing deployed model with a new trained version

## analysis

Visual analyses — containers for ML tasks.

```bash
dku analysis list [-P PROJECT] [-o FORMAT]
dku analysis create DATASET [-P PROJECT] [-o FORMAT]
dku analysis get ANALYSIS_ID [-P PROJECT] [-o FORMAT]
dku analysis delete ANALYSIS_ID [-P PROJECT]
dku analysis tasks ANALYSIS_ID [-P PROJECT] [-o FORMAT]
```

## evaluation-store

Model evaluation stores — track model performance over time.

```bash
dku evaluation-store list [-P PROJECT] [-o FORMAT]
dku evaluation-store create NAME [--if-not-exists] [-P PROJECT] [-o FORMAT]
dku evaluation-store get STORE_ID [-P PROJECT] [-o FORMAT]
dku evaluation-store evaluations STORE_ID [-P PROJECT] [-o FORMAT]
dku evaluation-store latest STORE_ID [-P PROJECT] [-o FORMAT]
dku evaluation-store build STORE_ID [--wait/--no-wait] [-P PROJECT]
dku evaluation-store delete STORE_ID [-P PROJECT]
```

- `create --if-not-exists` returns existing store if name matches (idempotent)
- `build --wait` (default) blocks until evaluation completes

## folder

Managed folders.

```bash
dku folder list [-P PROJECT] [-o FORMAT]
dku folder create NAME [-P PROJECT] [-c CONNECTION] [-t TYPE] [--if-not-exists] [-o FORMAT]
dku folder ls FOLDER_ID [-P PROJECT] [-o FORMAT]
dku folder upload FOLDER_ID FILE_PATH [-P PROJECT] [--remote-path PATH]
dku folder download FOLDER_ID REMOTE_PATH [-P PROJECT] [--dest DIR]
```

- `create` defaults to `filesystem_folders` connection; use `--connection` for S3, GCS, etc. Returns the folder ID needed for subsequent commands.

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
- `embeddings` outputs raw JSON to stdout — no `-o` flag; pipe to `jq` as needed

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
dku flow sources [-P PROJECT] [-o FORMAT]
dku flow successors NODE [-P PROJECT] [-o FORMAT]
```

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
dku agent set-prompt AGENT_ID --prompt "TEXT" [-P PROJECT]
dku agent set-llm AGENT_ID --llm-id LLM_ID [-P PROJECT]
```

- `set-prompt` writes to the active version system prompt. Accepts literal text, `@file.txt`, or `-` for stdin
- STRUCTURED_AGENT uses `systemPromptAppend` field; TOOLS_USING_AGENT uses `systemPrompt`

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
- **All `agent-block` subcommands require the agent ID, not the name.** Use `dku agent list -P PROJ -o json | jq '.[].id'` to get IDs. Other `dku agent` commands accept names, but `agent-block` does not.
- `add --set-start` sets the new block as starting block (auto-set for first block)
- `connect` sets `nextBlock` on the source block (for ROUTING clauses use `get-graph`/`set-graph`)
- `remove` warns about dangling references from other blocks
- `--version` defaults to active version
- **DSS 14.5+ block names:** `GENERATE_OUTPUT` (not `EMIT_OUTPUT`), `CORE_LOOP` (not `STANDARD_REACT`). DSS 13.x names are accepted but silently renamed. Use 14.5+ names to avoid confusion.
- **DSS 14.5+ settings path:** blocks are stored in `structuredAgentSettings` (not `toolsUsingAgentSettings`). `get-graph` returns `structuredAgentSettings` directly.
- Block types (DSS 14.5+): SET_STATE_ENTRIES, LLM_REQUEST, ROUTING, GENERATE_OUTPUT, CORE_LOOP, MANUAL_TOOL_CALL, MANDATORY_TOOL_CALL, PARALLEL, FOR_EACH, PYTHON_CODE, REFLECTION, DELEGATE_TO_OTHER_AGENT, GENERATE_ARTIFACT, CONTEXT_COMPRESSION, SET_SCRATCHPAD_ENTRIES, EDIT_LAST_USER_MESSAGE
- See `references/structured-agents.md` for full schema of each block type

**Example: Build an SVA from scratch (DSS 14.5+):**
```bash
AGENT_ID=$(dku agent create "My SVA" -P PROJ -o json | jq -r '.id')
dku agent-block add "$AGENT_ID" --set-start -b '{"type":"SET_STATE_ENTRIES","id":"init","entriesToSet":[{"secret":false,"key":"status","value":"ready"}],"nextBlock":"classify"}' -P PROJ
dku agent-block add "$AGENT_ID" -b '{"type":"LLM_REQUEST","id":"classify","llmId":"openai:conn:gpt-4.1-mini","passConversationHistory":true,"systemPromptAfterHistory":"Classify intent","completionSettings":{"stopSequences":[],"outputTrajectory":true},"streamOutput":false,"outputMode":"SAVE_TO_STATE","outputStateKey":"intent","nextBlock":"respond"}' -P PROJ
dku agent-block add "$AGENT_ID" -b '{"type":"GENERATE_OUTPUT","id":"respond","templateType":"CEL_EXPANSION","template":"Intent: {{state.intent}}","addToMessages":true}' -P PROJ
dku agent-block list "$AGENT_ID" -P PROJ
```

## agent-tool

```bash
dku agent-tool list [-P PROJECT] [-o FORMAT]
dku agent-tool get TOOL_ID [-P PROJECT] [-o FORMAT]
dku agent-tool run TOOL_ID [--input JSON] [-P PROJECT] [-o FORMAT]
dku agent-tool delete TOOL_ID [-P PROJECT]
dku agent-tool set-definition TOOL_ID -d JSON [-P PROJECT]
dku agent-tool types [-o FORMAT]
```

- **Plugin-based tool type naming:** `Custom_agent_tool_<plugin-id>_<tool-folder-name>`. Run `dku agent-tool types` to see built-in types plus the naming template for plugin tools.
- `set-definition` saves params to DSS but the running tool instance uses a cached copy — params don't take effect until the plugin server reloads (re-push the plugin or restart DSS).
- `run` on a VectorStoreSearch tool will fail with a prescriptive error if the knowledge bank has not been built yet.

## knowledge

Knowledge banks.

```bash
dku knowledge list [-P PROJECT] [-o FORMAT]
dku knowledge create NAME --embedding-llm LLM_ID [--vector-store-type FAISS|CHROMA|PINECONE|...] [--if-not-exists] [-P PROJECT]
dku knowledge get KB_ID [-P PROJECT] [-o FORMAT]
dku knowledge build KB_ID [-P PROJECT] [--wait]
dku knowledge search KB_ID --query TEXT [--max N] [-P PROJECT] [-o FORMAT]
dku knowledge delete KB_ID [-P PROJECT]
```

- `create` requires `--embedding-llm` (use `dku llm list --purpose TEXT_EMBEDDING_EXTRACTION` to find one)
- `create --vector-store-type` defaults to **CHROMA**. Options: CHROMA, FAISS, PINECONE, ELASTICSEARCH, AZURE_AI_SEARCH, VERTEX_AI_GCS_BASED, QDRANT_LOCAL, MILVUS_LOCAL, MILVUS_REMOTE
- `build` requires the KB to have a document source first — add one via `dku recipe create-embed`. Running `build` on a KB with no source fails with a prescriptive error.
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
