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
- [dataset](#dataset) — list, schema, info, head, build, create, upload, delete, clear, get-definition, set-definition, set-schema, set-metadata, set-column-description, ai-describe, rename, copy, partitions, exists, usages, lineage, detect, zone, share, unshare
- [recipe](#recipe) — list, get, get-definition, get-settings, set-settings, run, create, delete, set-code, get-code, set-definition, add-input, add-output, check-schema, apply-schema, create-embed, create-embed-docs, create-extract, create-llm-eval, create-agent-eval
- [scenario](#scenario) — list, run, abort, status, create, delete, get-definition, set-definition, last-run, runs, set-metadata, list-triggers, add-trigger, add-trigger-dataset, remove-trigger
- [job](#job) — list, run, status, log, abort, wait
- [plugin](#plugin) — list, get, push, delete, settings, create-code-env, set-code-env, update-code-env, usages, recipes, list-files, get-file, put-file
- [code-env](#code-env) — list, get, create, delete, update
- [connection](#connection) — list, get, create, delete, test
- [model](#model) — list, get, versions, set-active-version, metrics, delete-version, delete, usages, set-metadata
- [ml](#ml) — create-prediction, create-clustering, create-timeseries, create-causal, list, status, settings, algorithms, set-algorithm, set-feature, train, models, details, deploy, redeploy, delete
- [folder](#folder) — list, ls, upload, download, create, delete, delete-file, get, create-dataset, set-metadata
- [llm](#llm) — list, completion, embeddings
- [webapp](#webapp) — list, start, stop, status, get-definition, set-definition
- [dashboard](#dashboard) — list, get, create, delete, get-definition, set-definition, set-metadata
- [insight](#insight) — list, get, create, delete, get-definition, set-definition, validate, set-metadata
- [macro](#macro) — list, run
- [user](#user) — list, get, create, delete
- [flow](#flow) — graph, visualize, zones, create-zone, set-zone, move, propagate, check, sources, successors
- [library](#library) — list, read, write, delete, mkdir
- [agent](#agent) — list, create, get, delete, wake-up, shutdown, status, add-tool, set-llm, set-prompt, test, set-metadata
- [agent-review](#agent-review) — list, create, get, delete, set-agent, set-llm, add-trait, list-tests, create-test, import-tests, export-tests, run, list-runs, results
- [agent-tool](#agent-tool) — list, get, create, set-definition, run, types, delete
- [code-studio](#code-studio) — list, create, get, delete, status, start, stop, change-owner, templates
- [git](#git) — status, log, diff, commit, pull, push, fetch, branches, create-branch, delete-branch, switch, tags, create-tag, remote
- [api-deployer](#api-deployer) — list-infras, list-services, get-service, list-deployments, create-deployment, get-deployment, update-deployment, delete-deployment, deployment-status
- [project-deployer](#project-deployer) — list-infras, list-projects, list-deployments, create-deployment, get-deployment, update-deployment, delete-deployment, deployment-status
- [notebook](#notebook) — list, get, create, delete, sessions, stop, clear-outputs, history
- [discussion](#discussion) — list, get, create, reply
- [knowledge](#knowledge) — list, create, get, set-definition, build, search, delete
- [semantic-model](#semantic-model) — list, create, get, delete, versions, get-version, create-version, set-version, set-active-version, distinct-values, update-index
- [agent-hub](#agent-hub) — list, config, set-config, list-agents, add-agent, remove-agent, set-agent, set-llm, start, stop
- [app-designer](#app-designer) — get, set-definition, list-tiles, add-tile, remove-tile, set-section, enable, disable
- [app](#app) — list, get, list-instances, create-instance
- [bundle](#bundle) — list, export, download, import, activate
- [api-service](#api-service) — list, create, get, create-package, list-packages
- [wiki](#wiki) — list, create, get, update, delete
- [sql](#sql) — query
- [whoami](#whoami)
- [govern](#govern) — whoami, info; **artifact** list/get/create/delete/set-field/set-definition; **blueprint** list/get/list-versions/get-version (alias: get-version-definition)/describe-version/fields/create/set-definition/delete; **signoff** create/list/get/update-status/add-feedback/add-approval/delegate-feedback/delegate-approval/list-feedbacks/get-feedback/get-approval; **role** list/get/create/set-definition/delete; **custom-page** list/get/create/set-definition/delete; **user** list/get/create/create-bulk/edit-bulk/delete-bulk/get-own/list-activity; **group** list/get/create/delete; **time-series** create/get/push-values/delete; **file** upload/get/download

---

## auth

Manage DSS authentication profiles. No project needed.

```bash
dku auth login [--profile NAME] [--url URL] [--api-key KEY]
dku auth logout [--profile NAME] [--all]
dku auth status [-o text|json]
dku auth list
dku auth switch PROFILE
```

- `login` without `--api-key` prompts interactively (also prompts for default project)
- `login` with all flags is non-interactive (CI/CD)
- `logout --all` removes all profiles
- `status` shows resolved auth sources, DSS version/node type, and default project accessibility
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
dku project delete PROJECT_KEY --yes [--drop-data]
dku project duplicate PROJECT_KEY --target-key KEY --target-name NAME [-o FORMAT]
dku project set-metadata PROJECT_KEY [--name NAME] [--description DESC] [--tags a,b,c]
dku project variables [-P PROJECT] [-o FORMAT]
dku project set-variables [-P PROJECT] --set key=value [--set key2=value2]
dku project set-variables [-P PROJECT] --definition JSON
dku project permissions [-P PROJECT] [-o FORMAT]
dku project set-permissions [-P PROJECT] --definition JSON
dku project tags [-P PROJECT] [-o FORMAT]
dku project ai-describe [-P PROJECT] [--language LANG] [--purpose PURPOSE] [--length LENGTH] [--save] [-o FORMAT]
dku project timeline [-P PROJECT] [--limit N] [-o FORMAT]
```

- `delete` requires `--confirm`, `--yes`, or `-y` flag (safety guard). By default, backing storage of managed datasets (physical SQL tables, managed folder contents) is NOT dropped — they stay orphaned on the target connection. Pass `--drop-data` (alias `--clear-managed`) to also clear them. Without `--drop-data`, the command prints a reminder after deletion.
- `create --if-not-exists` skips creation silently when the project already exists (idempotent)
- `set-metadata` updates project display name and/or description after creation
- `set-variables --set` modifies individual standard vars; `--definition` replaces all
- `inspect` gives a one-shot project summary: datasets, recipes, scenarios, flow sources, jobs, wiki, variables. Use `-o json` for machine-readable nested output
- `ai-describe` generates AI description for the project. `--purpose`: generic (default), technical, business_oriented, executive. `--length`: low, medium, high. `--save` persists to the project
- `timeline` shows project history: creation, contributors, recent modifications. Items have `time`, `user`, `action`, `objectId` fields. Timestamps are millis in JSON, formatted in table output

## dataset

All commands require project (`-P KEY` / `DKU_PROJECT` / config default).

```bash
dku dataset list [-P PROJECT] [-o FORMAT]
dku dataset schema DATASET_NAME [-P PROJECT] [-o FORMAT]
dku dataset info DATASET_NAME [-P PROJECT] [-o FORMAT] [--recompute]  # Row count, size, type, connection, last build
dku dataset head DATASET_NAME [-P PROJECT] [-n ROWS] [-C COLUMNS] [-o FORMAT]
dku dataset build DATASET_NAME [-P PROJECT] [--wait] [--type BUILD_TYPE] [--auto-update-schema]
dku dataset create DATASET_NAME [--type Filesystem] [-c CONNECTION] [-P PROJECT] [--if-not-exists] [--definition JSON]
dku dataset upload DATASET_NAME FILE [-P PROJECT] [--no-autodetect] [--overwrite]
dku dataset delete DATASET_NAME [-P PROJECT] [--yes]
dku dataset clear DATASET_NAME [-P PROJECT]
dku dataset get-definition DATASET_NAME [-P PROJECT] [-o json]
dku dataset set-definition DATASET_NAME [-P PROJECT] --definition JSON
dku dataset set-schema DATASET_NAME [-P PROJECT] --definition JSON
dku dataset set-metadata DATASET_NAME [-P PROJECT] [--description DESC] [--short-desc DESC] [--tags TAGS]
dku dataset set-column-description DATASET_NAME COL1 "DESC1" COL2 "DESC2" [-P PROJECT]
dku dataset ai-describe DATASET_NAME [-P PROJECT] [--language LANG] [--save] [-o FORMAT]
dku dataset rename DATASET_NAME --name NEW_NAME [-P PROJECT]
dku dataset copy DATASET_NAME --to-project PROJECT_KEY [--name NAME] [-P PROJECT]
dku dataset partitions DATASET_NAME [-P PROJECT] [-o FORMAT]
dku dataset detect DATASET_NAME [-P PROJECT] [--save] [--infer-types] [-o FORMAT]  # Auto-detect format + schema
dku dataset zone DATASET_NAME [-P PROJECT] [-o FORMAT]                            # Show flow zone
dku dataset share DATASET_NAME --zone ZONE [-P PROJECT]                           # Share to zone
dku dataset unshare DATASET_NAME --zone ZONE [-P PROJECT]                         # Unshare from zone
dku dataset exists DATASET_NAME [-P PROJECT] [-o FORMAT]           # Exit code 0=exists, 1=not
dku dataset usages DATASET_NAME [-P PROJECT] [-o FORMAT]           # What recipes/analyses use this dataset
dku dataset lineage DATASET_NAME --column COL [-P PROJECT] [--max-datasets N] [-o FORMAT]  # Column provenance
```

- `upload` auto-detects format + schema after upload (calls `autodetect_settings`)
- `upload --overwrite` clears the dataset's existing uploaded files first
- `upload --no-autodetect` skips detection (if you'll set format manually)
- `head` defaults to 10 rows, override with `-n`. Use `--columns "col1,col2"` / `-C` to inspect specific columns before transforming
- `build --wait` blocks until job completes
- `build --type RECURSIVE_BUILD --auto-update-schema` builds upstream deps with automatic schema propagation
- `create --type UploadedFiles` for CSV upload targets
- `create` defaults to `--type Filesystem` with `-c filesystem_managed` if neither is specified
- `create --if-not-exists` skips creation silently when the dataset already exists (idempotent)
- `create --definition` supports create-time fields such as `type`, `params`, `formatType`, and `formatParams`
- `info --recompute` (alias `--fresh`) recomputes the row count, size, and file count metrics before reading them. Use after a recipe run to avoid stale numbers in the cache. Without `--recompute`, `info` on a built dataset with cached metrics prints a hint pointing at the flag (skipped in `-o json` mode)
- `set-schema` accepts both `{"columns": [...]}` (full object) and `[{name, type}, ...]` (plain array — auto-wrapped). Round-trips with `schema -o json`
- `set-metadata` updates description, short description, and/or tags without needing JSON. Provide at least one of `--description`, `--short-desc`, `--tags`
- `set-column-description` takes alternating column-name description pairs (even count required)
- `ai-describe` calls DSS AI Services to generate descriptions for the dataset and its columns. Requires 'Generate Metadata' enabled in DSS admin. `--save` persists descriptions to the dataset; without it, only displays suggestions. `--language`: english (default), french, german, dutch, portuguese, spanish
- `rename` renames the dataset in place
- `copy --to-project` copies a dataset to another project. `--name` overrides the name in the target (default: same name)
- `partitions` lists the partitions of a partitioned dataset
- `detect` runs DSS auto-detection on filesystem/SQL/Elasticsearch datasets. Without `--save`, shows detected format + schema. With `--save`, persists them. Use `--infer-types` to detect numeric/date types instead of all-STRING. Managed SQL datasets already have schemas from the database — autodetect is primarily for filesystem/uploaded datasets
- `zone` shows which flow zone a dataset belongs to. JSON: `{zone_id, zone_name, dataset}`
- `share --zone ZONE` makes a dataset visible in another zone without moving it. Use `dku flow move` to fully relocate
- `unshare --zone ZONE` removes a shared dataset from a zone
- `exists` returns exit code 0 if dataset exists, 1 if not. JSON: `{"exists": bool, "name", "project"}`
- `usages` shows recipes, analyses, and models that reference this dataset
- `lineage --column COL` traces column provenance across datasets (input→output relations). Use `--max-datasets` to limit scope

## recipe

### Visual recipe commands (PREFER these over Python)

```bash
dku recipe create-join NAME -i DS1 -i DS2 --output-ds OUT [--join-type LEFT] [-P PROJECT]  # Join
dku recipe create-group NAME -i DS --output-ds OUT [-k GROUP_COL] [--no-global-count] [-P PROJECT]  # Group/aggregate
dku recipe create-stack NAME -i DS1 -i DS2 --output-ds OUT [-P PROJECT]    # Stack/union
dku recipe create-distinct NAME -i DS --output-ds OUT [-P PROJECT]         # Deduplicate
dku recipe create-sort NAME -i DS --output-ds OUT [--sort-col COL] [-P PROJECT]  # Sort
dku recipe create-filter NAME -i DS --output-ds OUT --filter-formula EXPR [--action KEEP_ROW|REMOVE_ROW] [-P PROJECT]  # Filter rows
dku recipe create-window NAME -i DS --output-ds OUT [--partition-col COL] [--order-col COL] [-P PROJECT]  # Window functions
dku recipe create-split NAME -i DS --output-ds OUT [-P PROJECT]            # Split by condition
dku recipe create-topn NAME -i DS --output-ds OUT [--sort-col COL] [--n N] [-P PROJECT]  # Top/bottom N rows
dku recipe create-pivot NAME -i DS --output-ds OUT [--row-key COL] [--column-key COL] [--value-column COL] [--agg-type SUM|AVG|...] [--value-limit TOP_N|NO_LIMIT|AT_LEAST_N_OCC] [--topn-limit N] [--min-occ-limit N] [-P PROJECT]  # Pivot (long→wide)
dku recipe create-sampling NAME -i DS --output-ds OUT [--method METHOD] [--size N] [-P PROJECT]     # Random sample
dku recipe add-fold RECIPE --columns "c1,c2" --key-column KEY --value-column VAL [-P PROJECT]       # Fold (wide→long)
```

- `create-join` requires 2+ inputs. `--join-type LEFT|INNER|RIGHT|CROSS` (default LEFT). `--join-key col` or `--join-key left=right` (repeatable). For multi-input joins, prefix with index: `--join-key 1:col`, `--join-key 2:col`. With N inputs the CLI creates N-1 join pairs (main ↔ input 1, main ↔ input 2, …)
- `create-group -k col` sets first group key. Use `--agg col:sum,avg,count` to configure aggregation functions (repeatable). Without `--agg`, defaults to COUNT per group. DSS adds a per-group `count` column by default — pass `--no-global-count` to suppress it when you want only the explicit aggregates in the output
- `create-distinct` deduplicates on **all input columns by default** (matching `df.drop_duplicates()` semantics). Use `--on col1 --on col2` to dedup on a subset. Passing no `--on` flag reads the input schema and wires every column as a key
- `create-pivot` transposes rows into columns. `--row-key` (repeatable), `--column-key`, `--value-column` optional. Always emits `payload.pivots[0].valueLimit = "TOP_N"` + `topnLimit = 20` to match the DSS UI — without these, DSS crashes at build time with `Unexpected value limit on modality collection`. Valid `--value-limit` values: `TOP_N` (keep top N by frequency, default), `NO_LIMIT` (keep every distinct column-key value), `AT_LEAST_N_OCC` (keep modalities seen at least `--min-occ-limit N` times). Aggregation is stored as **boolean flags** on each value column (`sum: true`, `avg: true`, ...) — NOT as a `function` string. The CLI writes `{column, type: "double", sum/avg/min/max/count/count_distinct/concat/stddev: bool}` to match the UI. Writing `function: "SUM"` would be silently accepted by the API but produce a recipe that builds with no aggregated columns
- `create-sampling` takes a sample. `--method`: RANDOM_FIXED_NB (default), RANDOM_FIXED_RATIO, HEAD_SEQUENTIAL, STRATIFIED. `--size N` or `--ratio 0.1`
- `add-fold` unpivots columns into rows (wide→long). Use `--columns` for explicit list or `--pattern` for regex match
- `create-sort --sort-col COL` sets sort columns at creation (repeatable). Use `COL` for ascending or `COL:desc` for descending
- `create-topn --sort-col COL` and `--n N` set the sort column(s) and row limit at creation
- `create-filter` builds a **Prepare recipe** with a single `FilterOnCustomFormula` step (not a Sampling recipe — whose filter schema is unstable across DSS versions). `--filter-formula` is required (aliases `--filter`, `-f`). `--action KEEP_ROW` (default) keeps matching rows, `--action REMOVE_ROW` drops them
- `create-window --partition-key COL` and `--order-key COL` set the window partition and ordering columns. The CLI writes both to `windows[0]` with `enablePartitioning=true` / `enableOrdering=true` so aggregations/ranks are computed per-partition (not globally)
- `create-embed --embed-column COL` specifies the column to embed (alias for `--text-column`)
- Visual recipes auto-apply schema updates after creation. For manual control: `apply-schema RECIPE -P PROJ`

### Sync recipe: landing data across connections

`sync` moves data from one dataset to another. Unlike most visual recipes (which require the output to pre-exist), **`-t sync --connection X`** auto-creates the output as a managed dataset on the target connection — no Python passthrough needed. The same pattern works for `-t sql_query --connection X` when you want a custom SELECT landed as a new managed table.

For engine-specific examples, push-down gotchas, and recovery snippets, see `references/sql-engines.md`.

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
| Parse dates | `DateParser` | `'{"appliesTo":"SINGLE_COLUMN","columns":["date"],"formats":["yyyy-MM-dd"],"lang":"auto","timezone_id":"UTC","outCol":"date_parsed","outType":{"name":"out","type":"date"}}'` (MUST have outCol — in-place = nulls) |
| Extract year/month | `DateComponentsExtractor` | `'{"column":"date","timezone_id":"UTC","outYearColumn":"year","outMonthColumn":"month"}'` |
| Date difference | `DateDifference` | `'{"input1":"start","compareTo":"NOW","output":"days_ago","outputUnit":"DAYS","timezone_id":"UTC"}'` |
| Timestamp → date-only | `DateParser` | `'{"appliesTo":"SINGLE_COLUMN","columns":["ts"],"formats":["yyyy-MM-dd HH:mm:ss"],"lang":"auto","timezone_id":"UTC","outCol":"date_only","outType":{"name":"out","type":"dateonly"}}'` |
| Format date (custom pattern) | `DateFormatter` | `'{"inCol":"parsed","outCol":"month_label","format":"MMM yyyy","lang":"en_US","timezone_id":"UTC"}'` — `inCol`/`outCol`, NOT `column`/`outputColumn` |
| Truncate date to unit | `DateTruncate` | `'{"inCol":"parsed","outCol":"month_start","datePart":"MONTH"}'` — `datePart` must be `YEAR`/`MONTH`/`DAY`/`HOUR`/`MINUTE`/`SECOND` (defaults to `YEAR` if omitted) |
| UNIX epoch → date | `UNIXTimestampParser` | `'{"inCol":"event_ts","outCol":"event_date","milliseconds":false}'` — `milliseconds` is BOOLEAN, not `"SECONDS"`/`"MILLISECONDS"` |
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
dku recipe delete RECIPE_NAME [-P PROJECT] [--yes]
dku recipe rename RECIPE_NAME --name NEW_NAME [-P PROJECT]
dku recipe status RECIPE_NAME [-P PROJECT] [-o FORMAT]             # Engine, severity, check messages
dku recipe set-code RECIPE_NAME --code CODE|-|@file.py [-P PROJECT]
dku recipe get-code RECIPE_NAME [-P PROJECT] [-o text|json]
dku recipe set-definition RECIPE_NAME {--definition JSON | --payload JSON} [--deep-merge] [-P PROJECT]
dku recipe add-input RECIPE_NAME REF [--type DATASET|MANAGED_FOLDER|SAVED_MODEL] [--role ROLE] [-P PROJECT]
dku recipe add-output RECIPE_NAME DS [--role main] [-P PROJECT]
dku recipe check-schema RECIPE_NAME [-P PROJECT] [-o FORMAT]
dku recipe apply-schema RECIPE_NAME [-P PROJECT] [-o FORMAT]
```

- `create --input`/`--input-ds`/`-i` all work. `--type`/`-t` for type, `--output-ds` for output
- `create` requires `--input` to exist. For code recipes (python, sql), `--output-ds` is auto-created. For visual recipes, both must pre-exist
- `create -t prediction_scoring` and `create -t clustering_scoring` REQUIRE `--model SAVED_MODEL_ID_OR_NAME`. The model is auto-wired as a `model`-role input after creation. Omitting it errors before the server call
- `add-input REF` — `REF` can be a dataset name, managed folder (name or ID), or saved model (ID or name). When `--type` is omitted, the CLI auto-detects by probing the project and errors on ambiguity. For saved models, `--role` defaults to `model`. Folder names are resolved to IDs before writing the ref (DSS stores folder refs as IDs)
- `delete` prompts for confirmation by default. Use `--yes` / `-y` for non-interactive deletion
- `set-code` accepts `--code @file.py` to read from file, or `--code -` to read from stdin
- `get-code` only works on code recipes (python, sql, r, shell, pyspark, sparkr, cpython). For visual recipes (prepare/shaker, join, group, etc.) use `get-settings` to inspect the recipe definition
- `check-schema` output column is `NEEDS_UPDATE` (yes/no per output). Non-zero exit when any output needs an update — pair with `apply-schema` in scripts
- `run` on failure exits 1 with the failing job ID + `dku job log <ID>` + `dku job status <ID>` hints pre-formatted in the error details
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
dku scenario last-run SCENARIO_ID [--successful] [-P PROJECT] [-o FORMAT]
dku scenario runs SCENARIO_ID [--limit N] [--from DATE] [--to DATE] [-P PROJECT] [-o FORMAT]
dku scenario avg-duration SCENARIO_ID [--limit N] [-P PROJECT] [-o FORMAT]
dku scenario run-log SCENARIO_ID --run RUN_ID [--step STEP_ID] [-P PROJECT]
dku scenario set-metadata SCENARIO_ID [-P PROJECT] [--description DESC] [--short-desc DESC] [--tags TAGS]
dku scenario list-triggers SCENARIO_ID [-P PROJECT] [-o FORMAT]
dku scenario add-trigger SCENARIO_ID --trigger JSON [-P PROJECT]
dku scenario add-trigger-dataset SCENARIO_ID --dataset DS [--delay SECS] [--grace-delay SECS] [-P PROJECT]
dku scenario remove-trigger SCENARIO_ID --index INDEX [-P PROJECT]
```

- `last-run` shows the last finished run of a scenario
- `runs` lists recent runs (default limit: 10). Use `--limit` to change
- `set-metadata` updates description, short description, and/or tags. Provide at least one of `--description`, `--short-desc`, `--tags`
- `list-triggers` shows all triggers configured on a scenario (type, active status, params)
- `add-trigger --trigger` accepts raw trigger JSON (inline, `@file.json`, or `-` for stdin). Must include `type`, `active`, and `params` fields
- `add-trigger-dataset` is a convenience shortcut for dataset-change triggers. `--delay` is the check interval in seconds (default: 120). `--grace-delay` is the stabilization period (default: 0)
- `remove-trigger --index` removes a trigger by its 0-based index (use `list-triggers` to find the index)
- `set-definition` does a FULL settings replace — including `params.steps`, `params.reporters`, and the header fields. Supply a complete scenario definition (the shape returned by `get-definition` or `get_settings().get_raw()`). Partial updates of header-only fields should use `set-metadata` instead.
- **Step types for `params.steps`:** `build_flowitem` (build datasets/folders — takes `params.builds` as a list of `{type: "DATASET"|"MANAGED_FOLDER", itemId, partitionsSpec}` and `params.buildMode`), `custom_python` (inline script — `params.script`), `exec_sql` (SQL — `params.sql`, `params.connection`). See `dataikuapi/dss/scenario.py` for the full step-type catalogue.
- **`get-definition` is header-only:** it does NOT include `params.steps` or `triggers`. For triggers use `list-triggers`; for steps read via the API's `get_settings().get_raw()` path.

## job

```bash
dku job list [-P PROJECT] [-o FORMAT]
dku job last [-P PROJECT] [-o plain|table|json]
dku job run --target NAME [--target NAME2] [-P PROJECT] [--type BUILD_TYPE] [--auto-update-schema] [--wait] [--timeout SECS] [--refresh-metastore]
dku job status JOB_ID [-P PROJECT] [-o FORMAT]
dku job log JOB_ID [-P PROJECT] [--tail N] [--errors-only]
dku job abort JOB_ID [-P PROJECT]
dku job wait JOB_ID [-P PROJECT] [--timeout SECONDS]
```

- `last` prints the most recent job id on stdout — composable in shells: `dku job log $(dku job last -P PROJ) -P PROJ`. Pass `-o json` for the full record (id/state/initiator/start) or `-o table` for a one-row table. Exit 1 with a prescriptive error when there are no jobs
- `run --target` is repeatable for building multiple outputs in one job
- `run --type` defaults to `NON_RECURSIVE_FORCED_BUILD`; use `RECURSIVE_BUILD` to build upstream deps
- `run --auto-update-schema` auto-updates output schemas before each recipe run — eliminates manual schema propagation
- `run --wait` blocks until completion; combine with `--timeout` for bounded waits
- `log --tail N` keeps only the last N lines for shorter inspection
- `log --errors-only` heuristically filters to error-like lines plus nearby context; if nothing matches, it falls back to the full log with a warning

## plugin

Instance-level (no project needed).

```bash
dku plugin list [-o FORMAT]
dku plugin get PLUGIN_ID [-o FORMAT]
dku plugin push ZIP_OR_DIR [--update/--install]
dku plugin delete PLUGIN_ID [--confirm/--yes/-y] [--force]
dku plugin settings PLUGIN_ID [-o FORMAT] [--set key=value ...]
dku plugin create-code-env PLUGIN_ID [--wait/--no-wait] [-o FORMAT]
dku plugin set-code-env PLUGIN_ID ENV_NAME
dku plugin update-code-env PLUGIN_ID [--wait/--no-wait]
dku plugin usages PLUGIN_ID [-P PROJECT] [-o FORMAT]
dku plugin recipes [PLUGIN_ID] [-o FORMAT]
dku plugin list-files PLUGIN_ID [-o FORMAT]
dku plugin get-file PLUGIN_ID --path FILE_PATH
dku plugin put-file PLUGIN_ID --path FILE_PATH --content CONTENT
dku plugin download PLUGIN_ID [--dest PATH]                                    # Download dev plugin as ZIP
dku plugin rename-file PLUGIN_ID --path PATH --name NEW_NAME                   # Rename file/folder (dev only)
dku plugin move-file PLUGIN_ID --path PATH --to NEW_PATH                       # Move file/folder (dev only)
dku plugin install-from-store PLUGIN_ID [--wait/--no-wait]
dku plugin install-from-git REPO_URL [--checkout BRANCH] [--subpath PATH] [--wait/--no-wait]
dku plugin update-from-store PLUGIN_ID [--wait/--no-wait]
dku plugin update-from-git PLUGIN_ID REPO_URL [--checkout BRANCH] [--subpath PATH] [--wait/--no-wait]
```

- `push` reads plugin ID from `plugin.json` inside ZIP, auto-detects update vs install
- `push` accepts a directory (containing `plugin.json`) or a `.zip` archive
- `get` shows plugin details including version, code env, and dev status
- `create-code-env` creates and waits for the managed code env (use after first install)
- `set-code-env` assigns a code env to the plugin (use after create-code-env)
- `update-code-env` rebuilds the code env after dependency changes
- `usages` shows where plugin components are used; filter by project with `-P`
- `download` downloads a dev plugin as a ZIP archive. Only works for dev plugins (not store-installed). Default filename is `<plugin_id>.zip`
- `rename-file` renames a file or folder within a dev plugin. `--path` is the current path, `--name` is just the new filename (not full path)
- `move-file` moves a file or folder to a new location within the plugin. Both `--path` and `--to` are relative to plugin root
- First install flow: `push --install && create-code-env PLUGIN && set-code-env PLUGIN ENV`
- `recipes` lists plugin recipe types available for `dku recipe create --type`. Shows the full type string (e.g., `CustomCode_plugin_recipe`). Omit PLUGIN_ID to list from all plugins
- `list-files` lists files in a dev plugin as a flattened path tree (dev plugins only)
- `get-file --path` prints the contents of a file in a dev plugin
- `put-file --path` writes content to a file in a dev plugin. `--content` accepts literal string, `@file.txt`, or `-` for stdin
- `delete --force` force-deletes even if the plugin is used by recipes, agents, etc. Requires `--confirm`/`--yes`/`-y`

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
dku connection list [--type TYPE] [-o FORMAT]
dku connection get CONNECTION_NAME [-o FORMAT]
dku connection create NAME --type TYPE [--definition JSON]
dku connection delete CONNECTION_NAME [--yes]
dku connection test CONNECTION_NAME
dku connection schemas CONNECTION_NAME [-P PROJECT] [-o FORMAT]    # SQL schemas / Iceberg namespaces
dku connection tables CONNECTION_NAME [-P PROJECT] [--schema SCHEMA] [-o FORMAT]  # Importable tables
dku connection sync-acls CONNECTION_NAME [--root/--datasets] [--wait/--no-wait]
```

- `list --type` filters by connection type (Snowflake, PostgreSQL, EC2, etc.) using fast `list_connections_names` endpoint
- `test` only works on SQL and cloud connections. Filesystem/LLM/local connections exit 2 with `unsupported_operation` — use `dku connection get` to inspect instead
- `schemas` lists SQL schemas or Iceberg namespaces. Requires project context (`-P`)
- `tables` lists tables available for import. Use `--schema` to narrow results. Auto-detects SQL vs Iceberg
- `sync-acls` syncs HDFS ACLs (only useful with User Isolation + DSS-managed HDFS ACL). `--datasets` syncs dataset ACLs instead of root

- `get` shows connection details including type, params, and usability settings
- `delete` removes the connection. `--yes` skips confirmation

## model

```bash
dku model list [-P PROJECT] [-o FORMAT]
dku model get MODEL_ID [-P PROJECT] [-o FORMAT]
dku model versions MODEL_ID [-P PROJECT] [-o FORMAT]
dku model set-active-version MODEL_ID VERSION_ID [-P PROJECT]
dku model metrics MODEL_ID [--version VERSION_ID] [-P PROJECT] [-o FORMAT]
dku model delete-version MODEL_ID --version VERSION_ID [--version VERSION_ID2] [-P PROJECT]
dku model delete MODEL_ID [-P PROJECT]
dku model usages MODEL_ID [-P PROJECT] [-o json]
dku model set-metadata MODEL_ID [-P PROJECT] [--description DESC] [--short-desc DESC] [--tags TAGS]
dku model create-mlflow NAME [-t PREDICTION_TYPE] [-P PROJECT] [-o FORMAT]
dku model import-mlflow MODEL_ID -v VERSION_ID --path PATH [--code-env ENV] [--set-active/--no-set-active] [-P PROJECT]
dku model create-external NAME -t PREDICTION_TYPE --protocol PROTO [--connection CONN] [--region REGION] [--config JSON] [-P PROJECT] [-o FORMAT]
```

- `set-active-version` activates a version; downstream prediction recipes and API endpoints use it
- `metrics` shows performance metrics (AUC, accuracy, RMSE, etc.) for the active version by default. `--version` inspects a specific version
- `delete-version --version` is repeatable to delete multiple versions at once
- `delete` removes the entire saved model
- `usages` shows where the model is used (recipes, endpoints, etc.) as JSON
- `set-metadata` updates description, short description, and/or tags. Provide at least one of `--description`, `--short-desc`, `--tags`
- `create-mlflow` creates a saved model for MLflow pyfunc models. Prediction type optional (BINARY_CLASSIFICATION, MULTICLASS, REGRESSION). Follow with `import-mlflow` to import a version
- `import-mlflow` imports a MLflow model version from a local path. Model must have been created with `create-mlflow`. `--code-env` defaults to active env; set `INHERIT` for project default
- `create-external` creates a saved model for remote endpoints (SageMaker, Databricks, Azure ML, Vertex AI). `--protocol` is required. Use `--config` for full JSON config override

## ml

Train visual-ML models (prediction, clustering, timeseries, causal). Prefer these over Python.

```bash
dku ml create-prediction --input DS --target COL [--name NAME] [-P PROJECT]
dku ml create-clustering --input DS [--name NAME] [-P PROJECT]
dku ml create-timeseries --input DS --target COL --time-col COL [-P PROJECT]
dku ml create-causal --input DS --treatment COL --outcome COL [-P PROJECT]
dku ml list [-P PROJECT] [-o FORMAT]
dku ml status ANALYSIS MLTASK [-P PROJECT]
dku ml settings ANALYSIS MLTASK [-P PROJECT] [-o FORMAT]
dku ml algorithms ANALYSIS MLTASK [-P PROJECT] [-o FORMAT]
dku ml set-algorithm ANALYSIS MLTASK [--enable ALG]... [--disable ALG]... [--disable-all] [-P PROJECT]
dku ml set-feature ANALYSIS MLTASK FEATURE --role INPUT|REJECT|TARGET|WEIGHT [-P PROJECT]
dku ml train ANALYSIS MLTASK [-P PROJECT] [--wait]
dku ml models ANALYSIS MLTASK [-P PROJECT] [-o FORMAT]
dku ml details MODEL_ID [-P PROJECT] [-o FORMAT]
dku ml deploy MODEL_ID --name NAME [-P PROJECT]
dku ml redeploy MODEL_ID --saved-model-id SM_ID [-P PROJECT]
dku ml delete ANALYSIS MLTASK [--yes|-y] [-P PROJECT]
```

- **After `create-prediction`, ALWAYS audit `dku ml settings`** for label-leaking columns. Auto-guess does not detect leakage. Reject leaky columns with `dku ml set-feature ANALYSIS MLTASK COL --role REJECT` before training
- `set-feature --role REJECT` disables a column as input without rebuilding the upstream dataset. Use for label leakage, post-event columns, high-cardinality IDs
- `delete` prompts for confirmation; use `--yes` / `-y` for non-interactive
- To apply a saved clustering/prediction model to a dataset, see `references/recipe-decision.md` → "Scoring a Saved Model"

## folder

Managed folders. Commands accept folder ID (8-char hash) or folder name.

```bash
dku folder list [-P PROJECT] [-o FORMAT]
dku folder create NAME [-c CONNECTION] [--type TYPE] [-P PROJECT] [--if-not-exists] [-o FORMAT]
dku folder delete FOLDER_REF [-P PROJECT] [--yes]
dku folder get FOLDER_REF [-P PROJECT] [-o FORMAT]
dku folder ls FOLDER_REF [--prefix PATH] [-P PROJECT] [-o FORMAT]
dku folder upload FOLDER_REF FILE_PATH [--path REMOTE_PATH] [-P PROJECT]
dku folder download FOLDER_REF REMOTE_PATH [--dest DIR] [-P PROJECT]
dku folder delete-file FOLDER_REF PATH [-P PROJECT]
dku folder create-dataset FOLDER_REF DATASET_NAME [-P PROJECT]
dku folder set-metadata FOLDER_REF [-P PROJECT] [--description DESC] [--tags TAGS]
```

- `create` returns the folder ID (8-char hash) needed by other commands. Default connection: `filesystem_folders`. Use `--connection` for S3/GCS/etc
- `create --if-not-exists` skips creation silently when a folder with that name already exists (idempotent)
- `delete` removes the folder from the flow but does NOT delete file contents from underlying storage. `--yes` skips confirmation
- `get` shows folder settings: name, type, connection, path
- `ls --prefix` filters listed contents by path prefix (default: `/`)
- `delete-file` deletes a file within the folder (idempotent -- no error if file doesn't exist)
- `create-dataset` creates a FilesInFolder dataset from the folder, useful for feeding documents into embed-docs or extract recipes
- `set-metadata` updates folder description and/or tags. Provide at least one of `--description`, `--tags`
- Workflow: `create` -> `upload` -> `create-dataset` -> `recipe create-embed-docs`

## llm

```bash
dku llm list [-P PROJECT] [--purpose PURPOSE] [-o FORMAT]
dku llm completion LLM_ID MESSAGE [-P PROJECT] [--system MSG] [--json-output] [--json-schema JSON] [-o text|json]
dku llm embeddings LLM_ID --text TEXT [-P PROJECT]
dku llm generate-image LLM_ID --prompt TEXT [--negative-prompt TEXT] [--dest FILE] [-P PROJECT]
dku llm rerank LLM_ID --query TEXT --doc TEXT [--doc TEXT ...] [-P PROJECT] [-o FORMAT]
```

- LLM IDs follow `provider:connection:model` pattern (e.g., `openai:MyConnection:gpt-4o-mini`)
- `completion -o json` returns text + usage stats
- **Finding embedding models:** `dku llm list` defaults to `--purpose GENERIC_COMPLETION` which only shows chat/completion models. To find embedding models, you MUST use:
  ```bash
  dku llm list --purpose TEXT_EMBEDDING_EXTRACTION -P PROJECT
  ```
  Valid `--purpose` values: `GENERIC_COMPLETION`, `TEXT_EMBEDDING_EXTRACTION`, `IMAGE_EMBEDDING_EXTRACTION`, `RERANKING`, `IMAGE_GENERATION`
- `completion --json-schema` uses `with_json_output(schema=...)` for structured output. The LLM must support JSON mode with schema
- `embeddings` rejects LLM IDs that are not available for `TEXT_EMBEDDING_EXTRACTION` in the target project
- `generate-image` requires an IMAGE_GENERATION LLM. `--dest` saves to file, otherwise prints base64 preview. Use `--negative-prompt` to exclude elements
- `rerank` requires a RERANKING LLM. Pass multiple `--doc` flags. Results sorted by relevance score descending

### LLM Completion Patterns

**When to use `dku llm completion` vs a Prompt recipe:**

| Use case | Use `dku llm completion` | Use Prompt recipe (DSS UI) |
|----------|-------------------------|---------------------------|
| One-off query during automation | Yes | No |
| Repeatable pipeline step | No | Yes — becomes a flow node |
| Needs dataset input/output | No | Yes |
| Quick test/validation | Yes | No |
| Prompt engineering iteration | No | Yes — has prompt studio |

**Freeform JSON output:**
```bash
# Ask the LLM to respond in JSON (adds prompt instruction)
dku llm completion LLM_ID "List 3 colors" --json-output -P PROJ -o json
```

**Structured output with schema enforcement:**
```bash
# Schema-enforced JSON — the LLM MUST conform to the schema
dku llm completion LLM_ID "Extract the person's name and age" \
  --json-schema '{"type":"object","properties":{"name":{"type":"string"},"age":{"type":"integer"}},"required":["name","age"]}' \
  -P PROJ -o json
```

**With system message for role/context:**
```bash
dku llm completion LLM_ID "Summarize this data" \
  --system "You are a data analyst. Be concise." \
  -P PROJ
```

**Cost-conscious pattern:** Use `-o json` to see token usage:
```bash
dku llm completion LLM_ID "test" -P PROJ -o json | jq '.total_usage'
```

## webapp

No create via API (DSS UI only). But you can read/edit existing webapp code via get-definition/set-definition.

```bash
dku webapp list [-P PROJECT] [-o FORMAT]
dku webapp start WEBAPP_ID [-P PROJECT]
dku webapp restart WEBAPP_ID [-P PROJECT]
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
dku dashboard set-metadata DASHBOARD_ID [-P PROJECT] [--description DESC] [--short-desc DESC] [--tags TAGS]
```

- `set-metadata` updates description, short description, and/or tags. Provide at least one of `--description`, `--short-desc`, `--tags`
- No create via API for individual tiles/charts — manage via the raw JSON definition
- `get-definition` returns full dashboard JSON including `pages` array with embedded tiles
- Tiles live at `pages[i].grid.tiles` (NOT `pages[i].tiles`). Uses 36-column grid: `box: {top, left, width, height}`
- **URL anatomy:** `/dashboards/<dashboardId>_<slug>/view/<pageId>` maps to `dashboard.id` and `pages[].id`. Paste the URL path to locate a specific page in `get-definition` output
- **Filter-page dataset binding** can live at `pages[i].filtersParams.datasetSmartName`, not only inside filter insight definitions. Check both paths when tracing which dataset a filter targets
- **Always verify after `set-definition`** — DSS normalizes the payload on save. `TEXT` tile `tileParams.htmlContent` can be silently dropped. Follow every `set-definition` with a `get-definition` re-read and `diff` to confirm what actually persisted
- `set-definition` accepts JSON string, `@file.json`, or `-` for stdin
- See `skills/dataiku/references/dashboard-charts.md` for full chart JSON anatomy

## evaluation-store

```bash
dku evaluation-store list [-P PROJECT] [-o FORMAT] [--flavor FLAVOR]
dku evaluation-store create NAME [-P PROJECT] [-o FORMAT] [--flavor FLAVOR] [--if-not-exists]
dku evaluation-store get STORE_ID [-P PROJECT] [-o FORMAT]
dku evaluation-store evaluations STORE_ID [-P PROJECT] [-o FORMAT]
dku evaluation-store latest STORE_ID [-P PROJECT]
dku evaluation-store build STORE_ID [-P PROJECT] [--wait/--no-wait]
dku evaluation-store delete STORE_ID [-P PROJECT]
```

- `--flavor` on `create` specifies the store type: `TABULAR` (default), `LLM`, or `AGENT`. LLM eval recipes need `--flavor LLM`, agent eval recipes need `--flavor AGENT`
- `--flavor` on `list` filters by store flavor; omit to list all flavors
- `list` shows id, name, and flavor columns
- `create --if-not-exists` skips creation if a store with the same name already exists
- `latest` returns the most recent evaluation in a store (exits with error if empty)
- `build` waits for completion by default; use `--no-wait` for async

**End-to-end LLM evaluation:**
```bash
dku evaluation-store create my_eval --flavor LLM -P PROJ && \
dku dataset create eval_scored --type Filesystem -c filesystem_managed -P PROJ && \
dku dataset create eval_metrics --type Filesystem -c filesystem_managed -P PROJ && \
dku recipe create-llm-eval rag_eval \
  --input qa_responses --eval-store my_eval \
  --output-ds eval_scored --output-metrics eval_metrics \
  --task-type QUESTION_ANSWERING \
  --metrics "answerRelevancy,faithfulness" \
  --completion-llm "openai:gpt-4o" -P PROJ && \
dku recipe run rag_eval -P PROJ --wait
```

## insight

```bash
dku insight list [-P PROJECT] [-o FORMAT]
dku insight get INSIGHT_ID [-P PROJECT] [-o FORMAT]
dku insight create NAME [--type TYPE] [--dataset DS] [-P PROJECT] [--definition JSON] [--if-not-exists]
dku insight delete INSIGHT_ID [-P PROJECT]
dku insight get-definition INSIGHT_ID [-P PROJECT] [-o json]
dku insight set-definition INSIGHT_ID --definition JSON [-P PROJECT]
dku insight validate INSIGHT_ID [-P PROJECT]
dku insight set-metadata INSIGHT_ID [-P PROJECT] [--description DESC] [--short-desc DESC] [--tags TAGS]
```

- `set-metadata` updates description, short description, and/or tags. Provide at least one of `--description`, `--short-desc`, `--tags`
- `create` defaults to `--type dataset_table`. Common types: `chart`, `dataset_table`, `report`, `scenario_last_runs`, `metrics`, `eda`, `jupyter`
- `--dataset` / `--ds` binds the insight to a dataset (sets `params.datasetSmartName`). Required for chart/dataset_table types
- `--definition` overrides/extends creation info (merged with `--type` and name)
- `validate` checks chart column references against the dataset schema (client-side). Reports mismatches with fuzzy suggestions
- **Never hand-write a full `dataset_table` payload.** DSS's `shakerScript` schema has nested objects that vary across versions (e.g. `columnOrder` expects objects, not strings). Clone the live default first: `dku insight create NAME --type dataset_table --dataset DS -P PROJ && dku insight get-definition ID -P PROJ -o json > table.json`, then only edit `params.shakerScript.columnsSelection` / `sorting` / `previewMode` before `set-definition`. See `skills/dataiku/references/dashboard-charts.md` for the safe-to-edit field list

## macro

```bash
dku macro list [-P PROJECT] [-o FORMAT]
dku macro run MACRO_ID [-P PROJECT]
```

## user

```bash
dku user list [-o FORMAT]
dku user get LOGIN [-o FORMAT]
dku user create LOGIN --password PASS [--display-name NAME] [--email EMAIL] [--groups G1,G2]
dku user delete LOGIN [--yes]
dku user activity LOGIN [-o FORMAT]                        # Last login, session activity timestamps
dku user add-secret LOGIN --name NAME --value VALUE        # Add/replace a user secret
```

- `get` shows user details including display name, email, groups, and admin status
- `delete` removes the user. `--yes` skips confirmation

## flow

```bash
dku flow graph [-P PROJECT] [-o FORMAT]
dku flow visualize [-P PROJECT]
dku flow zones [-P PROJECT] [-o FORMAT]    # JSON output includes `items[]` per zone: {objectType, objectId, projectKey}
dku flow create-zone NAME [--color HEX] [-P PROJECT]
dku flow set-zone ZONE_REF [--name NAME] [--color HEX] [-P PROJECT]
dku flow move ITEM [ITEM2 ...] --zone ZONE [-t TYPE] [-P PROJECT]
dku flow propagate DATASET [-P PROJECT] [--stop-at RECIPE ...] [--mark-ok RECIPE ...] [--no-auto-rebuild] [-o FORMAT]
dku flow check [-P PROJECT] [-o FORMAT]
dku flow sources [DATASET] [-P PROJECT] [-o FORMAT]
dku flow successors NODE [-P PROJECT] [-o FORMAT]
```

- `visualize` renders the flow DAG as an ASCII tree
- `create-zone --color` sets the zone color as hex (e.g., `#FF5500`)
- `set-zone` updates a zone's name and/or color. Accepts zone name or ID
- `move` moves items to a flow zone. `--type`/`-t`: DATASET (default), RECIPE, MANAGED_FOLDER, SAVED_MODEL. Accepts multiple items at once
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
dku library sync LOCAL_DIR [REMOTE_DIR] [-P PROJECT] [--delete] [--dry-run/-n] [--exclude/-e PATTERN]
```

- `write --content @file.py` reads from local file
- `sync` uploads all files from a local directory to the project library, creating directories as needed. Skips `.git`, `__pycache__`, `.DS_Store`, `*.pyc`, `.venv`, `node_modules` by default. `--exclude` adds extra glob patterns. `--delete` removes remote files not present locally. `--dry-run` shows what would happen without uploading

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
dku agent set-prompt AGENT_ID --prompt PROMPT [-P PROJECT]
dku agent test AGENT_ID QUERY [-P PROJECT] [-o text|json]
dku agent set-metadata AGENT_REF [-P PROJECT] [--description DESC] [--short-desc DESC] [--tags TAGS]
```

- `create --type` defaults to TOOLS_USING_AGENT. Options: TOOLS_USING_AGENT, PYTHON_AGENT, PLUGIN_AGENT, STRUCTURED_AGENT
- `set-llm` and `add-tool` operate on the active version
- `set-prompt` sets the system prompt on the active version. `--prompt` accepts literal string, `@file.txt`, or `-` for stdin. Auto-detects agent type: uses `systemPrompt` for simple agents, `systemPromptAppend` for structured agents
- `test` sends a query to the agent and displays the response. ALWAYS test agents after creation or modification. `-o json` returns agent_id, query, response, and success status
- `set-metadata` updates description, short description, and/or tags. Accepts agent ID or name. Provide at least one of `--description`, `--short-desc`, `--tags`

## agent-block

Manage visual agent block graphs (structured visual agents). Blocks live inside `STRUCTURED_AGENT` agents (DSS 14.5+). Do NOT use `TOOLS_USING_AGENT` for block graphs — blocks silently fail to persist.

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
dku agent create "My SVA" --type STRUCTURED_AGENT -P PROJ
dku agent-block add My_SVA --set-start -b '{"type":"SET_STATE_ENTRIES","id":"init","entriesToSet":[{"secret":false,"key":"status","value":"'\''ready'\''"}],"nextBlock":"classify"}' -P PROJ
dku agent-block add My_SVA -b '{"type":"LLM_REQUEST","id":"classify","llmId":"openai:conn:gpt-4.1-mini","passConversationHistory":true,"systemPromptAfterHistory":"Classify intent","completionSettings":{"stopSequences":[],"outputTrajectory":true},"streamOutput":false,"outputMode":"SAVE_TO_STATE","outputKey":"intent","nextBlock":"respond"}' -P PROJ
dku agent-block add My_SVA -b '{"type":"EMIT_OUTPUT","id":"respond","templateType":"CEL_EXPANSION","template":"Intent: {{state.intent}}","addToMessages":true}' -P PROJ
dku agent-block list My_SVA -P PROJ
```

**Critical block requirements (DSS 14.5+):**
- Every CORE_LOOP / LLM_REQUEST / MANDATORY_TOOL_CALL block needs `"llmId"`
- Every block with `"outputMode": "SAVE_TO_STATE"` needs `"outputKey"` (or `"outputStateKey"`)
- SET_STATE_ENTRIES `"value"` fields are CEL — never use `""` (empty), use `"''"` instead

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
dku knowledge delete KB_REF [--yes|-y] [-P PROJECT]
```

- All commands (except `list`, `create`) accept knowledge bank ID **or name** — name is resolved via list fallback
- `create` requires `--embedding-llm` (use `dku llm list --purpose TEXT_EMBEDDING_EXTRACTION` to find one)
- `create --vector-store-type` defaults to CHROMA. Options: CHROMA, FAISS, PINECONE, ELASTICSEARCH, AZURE_AI_SEARCH, VERTEX_AI_GCS_BASED, QDRANT_LOCAL, MILVUS_LOCAL, MILVUS_REMOTE
- `set-definition` merges JSON into current settings (shallow merge). Get current: `dku knowledge get KB -o json`
- `get` expects JSON from DSS; on getitstarted instances the sleep/wake page can intercept the request and return HTML instead

## semantic-model

Semantic models map business context (entities, attributes, relationships) onto datasets, enabling text-to-SQL via the Semantic Model Query agent tool. DSS 14.4+.

```bash
dku semantic-model list [-P PROJECT] [-o FORMAT]
dku semantic-model create NAME [--if-not-exists] [-P PROJECT]
dku semantic-model get SM_REF [-P PROJECT] [-o FORMAT]
dku semantic-model delete SM_REF [-P PROJECT]
dku semantic-model versions SM_REF [-P PROJECT] [-o FORMAT]
dku semantic-model get-version SM_REF [--version VID] [-P PROJECT] [-o FORMAT]
dku semantic-model create-version SM_REF VERSION_ID [--duplicate-of VID] [-P PROJECT]
dku semantic-model set-version SM_REF --definition JSON|@file.json|- [--version VID] [-P PROJECT]
dku semantic-model set-active-version SM_REF VERSION_ID [-P PROJECT]
dku semantic-model distinct-values SM_REF [--version VID] [--entity E --attribute A] [--max N] [-P PROJECT] [-o FORMAT]
dku semantic-model update-index SM_REF [--version VID] [--wait] [-P PROJECT]

# Splice-level mutation verbs (preferred over raw set-version)
dku semantic-model add-entity SM_REF --from-dataset DS [--name N] [--pk COL[,COL2]] \
  [--index-values COL1,COL2] [--resolve-values COL1,COL2] [--description D] [--tags t1,t2] \
  [--version VID] [--if-not-exists] [-P PROJECT]
dku semantic-model remove-entity SM_REF ENTITY_NAME [--version VID] [-P PROJECT]

dku semantic-model add-relationship SM_REF --from A --to B (--on COL[,COL2] | --expression "left.x = right.x") \
  [--version VID] [--if-not-exists] [-P PROJECT]
dku semantic-model remove-relationship SM_REF --from A --to B [--version VID] [-P PROJECT]

dku semantic-model add-glossary-term SM_REF --term T [--description D] [--synonyms s1,s2] \
  [--version VID] [--if-not-exists] [-P PROJECT]
dku semantic-model remove-glossary-term SM_REF --term T [--version VID] [-P PROJECT]

dku semantic-model list-entities SM_REF [--version VID] [-P PROJECT] [-o FORMAT]
dku semantic-model list-relationships SM_REF [--version VID] [-P PROJECT] [-o FORMAT]
dku semantic-model list-glossary SM_REF [--version VID] [-P PROJECT] [-o FORMAT]

# Entity-scoped: metrics (aggregates) and filters (predicates)
dku semantic-model add-metric SM_REF --entity E --name N --expression "COUNT(*)" \
  [--description D] [--version VID] [--if-not-exists] [-P PROJECT]
dku semantic-model remove-metric SM_REF --entity E --name N [--version VID] [-P PROJECT]
dku semantic-model list-metrics SM_REF --entity E [--version VID] [-P PROJECT] [-o FORMAT]

dku semantic-model add-filter SM_REF --entity E --name N --expression "col = 'x'" \
  [--description D] [--version VID] [--if-not-exists] [-P PROJECT]
dku semantic-model remove-filter SM_REF --entity E --name N [--version VID] [-P PROJECT]
dku semantic-model list-filters SM_REF --entity E [--version VID] [-P PROJECT] [-o FORMAT]

# Attribute-scoped: curated enum values
dku semantic-model set-manual-values SM_REF --entity E --attribute A \
  (--values "a,b,c" | --clear) [--version VID] [-P PROJECT]

# Version-scoped: golden queries (NL→SQL few-shot examples)
dku semantic-model add-golden-query SM_REF --name N --question Q --sql SQL \
  [--version VID] [--if-not-exists] [-P PROJECT]
dku semantic-model remove-golden-query SM_REF --name N [--version VID] [-P PROJECT]
dku semantic-model list-golden-queries SM_REF [--version VID] [-P PROJECT] [-o FORMAT]
```

- All commands accept semantic model ID **or name** — name resolved via list fallback
- `create` returns auto-generated ID (not name) — capture it
- `--version` defaults to the active version when omitted
- `create-version` does NOT persist until the server is called — `new_version().save()` is handled internally
- `create-version --duplicate-of` clones an existing version's configuration
- `set-version` **shallow-merges** JSON into current version settings at the TOP level. This means passing `{"relationships":[{...}]}` **REPLACES the entire relationships array**, not appends. Always read current, modify, then save:
  ```bash
  dku semantic-model get-version SM -P PROJ -o json > sm.json
  jq '.relationships += [{"firstEntity":"A","secondEntity":"B","pseudoSQLExpression":"left.id = right.id"}]' sm.json > sm_new.json
  dku semantic-model set-version SM --definition @sm_new.json -P PROJ
  ```
- **Relationship JSON shape** (verified on DSS 14.4.3): `{"firstEntity":"name","secondEntity":"name","pseudoSQLExpression":"left.col = right.col"}`. Three fields. No cardinality. See `dataiku` skill's `references/semantic-models.md` for entity/glossary shapes.
- **Never guess inner JSON shapes.** `dataikuapi` treats entities/relationships/glossary as opaque dicts with no inner class definitions. Build one example in the DSS UI → export with `get-version -o json` → templatize.
- **Prefer splice verbs over `set-version` for mutations.** `add-entity`/`add-relationship`/`add-glossary-term` load the current version, splice the array, and save — no shallow-merge hazard. Use raw `set-version` only for bulk replace or top-level field changes (`description`, `indexingSettings`).
- **`add-entity --from-dataset DS`** auto-generates all attribute definitions from the dataset schema (column names, DSS types, descriptions). Pass `--index-values COL1,COL2` to enable distinct-value indexing + fuzzy resolution on specific columns. Default PK is the first dataset column — override with `--pk COL`.
- **`add-relationship --on COL`** builds `left.COL = right.COL`. Comma-separated for composite joins (`--on ACCOUNT_SK,MONTH` → `left.ACCOUNT_SK = right.ACCOUNT_SK AND left.MONTH = right.MONTH`). Use `--expression` for computed predicates (`LOWER(left.x) = LOWER(right.y)`).
- **Entity metrics/filters are pseudo-SQL.** Metrics are aggregates (`COUNT(*)`, `SUM(Amount)`, `COUNT(DISTINCT CustomerID)`). Filters are predicates (`Subscribed = 'true'`, `Date >= CURRENT_DATE - INTERVAL '30 days'`). These become the **approved** building blocks the text-to-SQL agent composes — without them the agent hand-rolls SQL from scratch, which is worse.
- **`set-manual-values` flips the attribute to curated-enum mode.** Automatically sets `distinctValuesHandlingMode=MANUAL`, `indexDistinctValues=true`, `resolveInUserRequests=true` so the agent resolves user strings ("high risk" → `RiskTolerance = 'High'`). Use `--clear` to revert to indexed scan (`mode=NONE`).
- **Golden queries drive quality more than any other single input.** Add real NL questions + the canonical SQL. The agent uses these as few-shot examples, learning join style + your column conventions.
- **From-scratch workflow, high-quality** (verified DSS 14.4.3):
  ```bash
  dku semantic-model create "My Model" -P PROJ
  dku semantic-model create-version $SM_ID v1 -P PROJ
  dku semantic-model set-active-version $SM_ID v1 -P PROJ

  # Entities (auto-generate attributes from datasets)
  dku semantic-model add-entity $SM_ID --from-dataset Customers --pk CustomerID --index-values Name,RiskTolerance -P PROJ
  dku semantic-model add-entity $SM_ID --from-dataset Orders --pk OrderID -P PROJ

  # Metrics & filters (agent's approved aggregates/predicates)
  dku semantic-model add-metric $SM_ID --entity customers --name "Total Customers" --expression "COUNT(CustomerID)" -P PROJ
  dku semantic-model add-metric $SM_ID --entity customers --name "Subscribed Customers" --expression "COUNT(CASE WHEN Subscribed='true' THEN CustomerID END)" -P PROJ
  dku semantic-model add-filter $SM_ID --entity customers --name "Subscribed" --expression "Subscribed = 'true'" -P PROJ

  # Curated enums on categorical attributes
  dku semantic-model set-manual-values $SM_ID --entity customers --attribute RiskTolerance --values "Low,Medium,High" -P PROJ

  # Joins
  dku semantic-model add-relationship $SM_ID --from customers --to orders --on CustomerID -P PROJ

  # Glossary & golden queries
  dku semantic-model add-glossary-term $SM_ID --term ARR --description "Annual Recurring Revenue" --synonyms "annual recurring revenue" -P PROJ
  dku semantic-model add-golden-query $SM_ID --name "count subscribers" --question "How many subscribed customers do we have?" --sql "SELECT COUNT(*) FROM Customers WHERE Subscribed='true'" -P PROJ

  dku semantic-model update-index $SM_ID --wait -P PROJ
  ```
- `distinct-values` requires `--entity` AND `--attribute` together, or neither (for all attributes)
- `update-index` triggers distinct values indexing (async). Use `--wait` to block until complete
- **Always `update-index --wait` after changing entities/attributes.** The text-to-SQL agent only sees indexed distinct values.
- **Limitation**: `get_semantic_model()` is lazy — the CLI calls `_get_definition()` internally to verify existence

## agent-hub

Manage Agent Hub plugin webapp instances. Agent Hub is Dataiku's multi-agent chat platform (DSS 14.2+).

```bash
dku agent-hub list [-P PROJECT] [-o FORMAT]
dku agent-hub config [--hub HUB_ID] [-P PROJECT] [-o FORMAT]
dku agent-hub set-config --definition JSON|@file.json|- [--hub HUB_ID] [-P PROJECT]
dku agent-hub list-agents [--hub HUB_ID] [-P PROJECT] [-o FORMAT]
dku agent-hub add-agent --agent-id PROJECT:agent:ID --name NAME --description DESC [--hub HUB_ID] [-P PROJECT]
dku agent-hub remove-agent --agent-id PROJECT:agent:ID [--hub HUB_ID] [-P PROJECT]
dku agent-hub set-agent --agent-id PROJECT:agent:ID [--name NAME] [--description DESC] [--examples JSON_ARRAY] [--hub HUB_ID] [-P PROJECT]
dku agent-hub set-llm LLM_ID [--hub HUB_ID] [-P PROJECT]
dku agent-hub start [--hub HUB_ID] [-P PROJECT]
dku agent-hub stop [--hub HUB_ID] [-P PROJECT]
```

- **Cannot create Agent Hub via CLI** — it's a plugin webapp, must be created in DSS UI first
- `--hub` auto-detects if exactly one Agent Hub exists in the project; required when multiple exist
- `list` filters webapps by type `webapp_agent-hub_agent-hub`
- `config` shows the full Agent Hub config (LLMs, agents, orchestration mode, My Agents settings, etc.)
- `set-config` merges JSON into current config (shallow merge). Get current: `dku agent-hub config -o json`
- `add-agent` manages both `agents_ids` and `tool_agent_configurations` atomically
- `--agent-id` format is `PROJECT:agent:ID` — find IDs with `dku agent list -P PROJ -o json`
- `set-agent --examples` accepts a JSON array string, e.g. `'["Q4 sales?", "Revenue by region"]'`
- `set-llm` sets the orchestrating LLM (must support tool calling for Tools mode)
- `start`/`stop` control the webapp backend (same as `dku webapp start/stop`)

## app-designer

```bash
# Enable/disable app homepage
dku app-designer enable [-P PROJECT] [--label LABEL] [--description DESC]
dku app-designer disable [-P PROJECT]

# Get/set full manifest
dku app-designer get [-P PROJECT] [-o json]
dku app-designer set-definition [-P PROJECT] -d JSON|@file.json|-

# Section titles and text
dku app-designer set-section [-P PROJECT] -s INDEX --title "Step 1) Upload" [--text "HTML description"]

# Tile management
dku app-designer list-tiles [-P PROJECT] [-o FORMAT]
dku app-designer add-tile [-P PROJECT] -s INDEX --type TYPE [--dataset DS] [--scenario ID] [--dashboard ID] [--folder ID] [--prompt LABEL] [--help-text TEXT] [--behavior BEH] [--button-text TEXT] [--params JSON] [--code CODE] [--definition JSON]
dku app-designer remove-tile [-P PROJECT] -s SECTION -i INDEX
```

**Notes:**
- `enable` must be called before other commands on a non-app project
- `add-tile --type` supports: `SCENARIO_RUN`, `INLINE_DATASET_EDIT`, `UPLOAD_DATASET_SET_FILE`, `DOWNLOAD_DATASET`, `DASHBOARD_LINK`, `MANAGED_FOLDER_BROWSE`, `MANAGED_FOLDER_ADD_FILE`, `DOWNLOAD_MANAGED_FOLDER_FILE`, `PROJECT_VARIABLES_EDIT`, `INLINE_PYTHON_RUN`, `PERFORM_SCHEMA_PROPAGATION`, `DATASET_EDIT_SETTINGS`, `FILES_BASED_DATASET_BROWSE_AND_PREVIEW`, `DOWNLOAD_DASHBOARD_EXPORT`, `DOWNLOAD_RMARKDOWN`, `MANAGED_FOLDER_LINK`
- `--dataset` binds tile to a specific dataset (for INLINE_DATASET_EDIT, UPLOAD_DATASET_SET_FILE, DOWNLOAD_DATASET)
- `--behavior INLINE_UPLOAD_REDETECT_AND_INFER` is best for upload tiles (auto-detects schema)
- `--definition @tile.json` overrides all shortcut flags for complex tiles (e.g., PROJECT_VARIABLES_EDIT with params)
- `set-section --text` supports HTML: `<i class="icon-warning-sign"></i>`, `<b>bold</b>`, wiki links `[text](article:ID)`
- See `dataiku` skill's `references/app-designer.md` for full tile/param type reference and UX patterns

## app

```bash
dku app list [-o FORMAT]
dku app get APP_ID [-o FORMAT]
dku app list-instances APP_ID [-o FORMAT]
dku app create-instance APP_ID --key PROJECT_KEY --name "Instance Name" [--wait|--no-wait]
```

**Notes:**
- App IDs follow `PROJECT_XXXX` format (project key prefixed with `PROJECT_`)
- `create-instance` creates a full copy of the template project
- `list` does not require a project flag

## bundle

```bash
dku bundle list [-P PROJECT] [-o FORMAT]
dku bundle export BUNDLE_ID [-P PROJECT]
dku bundle download BUNDLE_ID [-P PROJECT] [--dest DIR]
dku bundle import FILE [-P PROJECT]
dku bundle activate BUNDLE_ID [-P PROJECT]
```

- `activate` calls `preload_bundle` then `activate_bundle`

## continuous

```bash
dku continuous list [-P PROJECT] [-o FORMAT]
dku continuous start RECIPE_ID [-P PROJECT]
dku continuous stop RECIPE_ID [-P PROJECT]
dku continuous status RECIPE_ID [-P PROJECT] [-o FORMAT]
```

- Manages continuous recipe activities (streaming recipes that run indefinitely)
- `list` shows recipe ID, desired state, and current state
- `status` returns `desiredState` (STARTED/STOPPED) and `mainLoopState.state` (RUNNING/etc.)

## api-service

```bash
dku api-service list [-P PROJECT] [-o FORMAT]
dku api-service create SERVICE_ID [-P PROJECT]
dku api-service get SERVICE_ID [-P PROJECT] [-o FORMAT]
dku api-service create-package SERVICE_ID [-P PROJECT]
dku api-service list-packages SERVICE_ID [-P PROJECT] [-o FORMAT]
dku api-service add-endpoint SERVICE_ID -e ENDPOINT_ID -m MODEL_ID [-t TYPE] [-P PROJECT]
dku api-service list-endpoints SERVICE_ID [-P PROJECT] [-o FORMAT]
dku api-service publish-package SERVICE_ID --package PKG_ID [--published-service ID] [-P PROJECT]
dku api-service delete-package SERVICE_ID --package PKG_ID [-P PROJECT]
```

- `add-endpoint` types: prediction (default), clustering, forecasting, causal
- `publish-package` publishes to API Deployer. `--published-service` overrides the target service ID

## rag

```bash
dku rag list [-P PROJECT] [-o FORMAT]
dku rag create NAME --kb KB_ID --llm LLM_ID [-P PROJECT] [-o FORMAT]
dku rag get RAG_ID [-P PROJECT] [-o FORMAT]
dku rag delete RAG_ID [-P PROJECT] [--yes]
dku rag get-definition RAG_ID [-P PROJECT] [-o json]
dku rag set-definition RAG_ID --definition JSON [-P PROJECT]
```

- `create` ties a knowledge bank + LLM into a RAG LLM. Use after building an embed recipe
- The LLM ID for use elsewhere is `retrieval-augmented-llm:<RAG_ID>`
- Settings are nested: `versions[0].ragllmSettings` contains `llmId` and `kbRef`

## model-comparison

```bash
dku model-comparison list [-P PROJECT] [-o FORMAT]
dku model-comparison create NAME --type PREDICTION_TYPE [-P PROJECT] [-o FORMAT]
dku model-comparison get COMPARISON_ID [-P PROJECT] [-o json]
dku model-comparison add-model COMPARISON_ID --model FULL_MODEL_ID [-P PROJECT]
dku model-comparison remove-model COMPARISON_ID --model FULL_MODEL_ID [-P PROJECT]
dku model-comparison delete COMPARISON_ID [--yes] [-P PROJECT]
```

- Types: BINARY_CLASSIFICATION, REGRESSION, MULTICLASS, TIMESERIES_FORECAST, CAUSAL_BINARY_CLASSIFICATION, CAUSAL_REGRESSION
- Full model IDs: `S-PROJ-modelId-versionId` (saved model), `A-PROJ-analysisId-taskId-...` (lab model), `ME-PROJ-storeId-evalId` (model evaluation)
- `add-model`/`remove-model` modify the comparison then save automatically

## project-folder

```bash
dku project-folder list [-o FORMAT]
dku project-folder create NAME [--parent FOLDER_ID]
dku project-folder move-project PROJECT_KEY --folder FOLDER_ID
```

- `list` shows recursive tree from root with indented folder names, IDs, and project keys
- `create` creates a subfolder under the given parent (default: ROOT)
- `move-project` moves a project to a different folder. Get folder IDs from `list`

## meaning

```bash
dku meaning list [-o FORMAT]
dku meaning get MEANING_ID [-o json]
dku meaning create MEANING_ID --label LABEL [--type TYPE] [--description DESC]
dku meaning update MEANING_ID --definition JSON
```

- Instance-level (no project context needed), admin-only for create/update
- Types: DECLARATIVE, VALUES_LIST, VALUES_MAPPING, PATTERN
- `get` returns full definition including entries/mappings/pattern
- `update` requires the full definition dict (get → modify → update)

## cluster

```bash
dku cluster list [-o FORMAT]
dku cluster get CLUSTER_ID [-o json]
dku cluster create NAME [--type TYPE] [--arch HADOOP|KUBERNETES]
dku cluster start CLUSTER_ID
dku cluster stop CLUSTER_ID [--terminate/--no-terminate]
dku cluster status CLUSTER_ID [-o FORMAT]
dku cluster delete CLUSTER_ID [--yes]
```

- Admin-only. Manages Hadoop and Kubernetes clusters
- `start`/`stop` only work for managed clusters (not manual)
- `stop --no-terminate` detaches without deleting the underlying infra
- `delete` does NOT stop the cluster first — stop it first if it's running

## api-key

```bash
dku api-key list [-o FORMAT]
dku api-key get KEY_ID [-o json]
dku api-key create --label LABEL [--description DESC] [--admin] [-o FORMAT]
dku api-key delete KEY_ID [--yes]
```

- Admin-only. Secret key shown only at creation time
- `create --admin` grants full admin rights. Without `--admin`, key has no permissions (add groups via `get` → modify → `set_definition`)
- The `key` field in JSON output is the secret — store it securely

## admin

```bash
dku admin logs [-o FORMAT]
dku admin get-log LOG_NAME
dku admin usage [--per-project] [-o FORMAT]
dku admin instance-info [-o FORMAT]
dku admin sanity-check [--wait/--no-wait] [-o FORMAT]
```

- All commands require admin API key
- `logs` lists files with name + size. `get-log` outputs the content
- `usage` shows project/dataset/recipe/user counts. `--per-project` adds breakdown
- `instance-info` shows node type, version, hostname, Java/Python versions
- `sanity-check` runs DSS health checks and reports issues by severity

## streaming

```bash
dku streaming list [-P PROJECT] [-o FORMAT]
dku streaming create NAME --type TYPE [--connection CONN] [--topic TOPIC] [--url URL] [-P PROJECT]
dku streaming get NAME [-P PROJECT] [-o json]
dku streaming delete NAME [--yes] [-P PROJECT]
dku streaming schema NAME [-P PROJECT] [-o FORMAT]
dku streaming set-schema NAME --definition JSON [-P PROJECT]
```

- Types: kafka, httpsse, SQS, KDBPlus
- `create` for Kafka: use `--connection` + `--topic`. For HTTP SSE: use `--url`
- `schema`/`set-schema` manage the column schema independently of the endpoint settings

## app

```bash
dku app list [-o FORMAT]
dku app get APP_ID [-o json]
dku app list-instances APP_ID [-o FORMAT]
dku app create-instance APP_ID --key INSTANCE_KEY --name NAME [--wait/--no-wait]
```

- App ID format: `PROJECT_<project_key>` for project-based apps, `PLUGIN_<plugin>_<component>` for plugin apps
- `list` shows all app templates on the instance
- `list-instances` shows existing instances of a specific app
- `create-instance` creates a new project from the app template. `--key` must be globally unique

## workspace

```bash
dku workspace list [-o FORMAT]
dku workspace create KEY --name NAME [--description DESC] [--color #HEX] [-o FORMAT]
dku workspace get KEY [-o json]
dku workspace list-objects KEY [-o FORMAT]
dku workspace delete KEY [--yes]
```

- Instance-level (no project context). Admin rights needed for create/delete
- `list-objects` shows datasets, dashboards, articles, apps in the workspace. Some objects (stories/HTML links) may not have a `reference` field
- Use workspaces to organize content across projects for end-user consumption

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
dku sql query SQL --connection CONN [-o FORMAT] [--no-auto-commit]
```

- `query` accepts SQL string or `@file.sql`
- Works for SELECT, DDL (`CREATE` / `DROP` / `ALTER` / `TRUNCATE`), and DML (`INSERT` / `UPDATE` / `DELETE` / `MERGE` / `GRANT` / `REVOKE`).
- **DDL/DML auto-commits.** DSS's `sql_query` endpoint runs every statement in a streaming session that rolls back on close, so CREATE / INSERT / DROP would be silently discarded without a trailing `COMMIT`. The CLI detects DDL/DML by first-token (ignoring leading whitespace and `--` / `/* */` comments) and passes `post_queries=["COMMIT"]` to `client.sql_query()`. On success, prints `◆ Committed on <connection>`.
- Pass `--no-auto-commit` to opt out — useful when wrapping multiple statements in explicit `BEGIN; ... COMMIT;` or when testing rollback behavior.
- SELECT queries never auto-commit (no behavior change).

## whoami

```bash
dku whoami
```

Shows: user, DSS URL, DSS version, groups.

---

## govern

Nested `dku govern <group> <verb>`. Requires Govern integration + admin API key. Deep patterns, JSON payloads, signoff state machine, gotchas: `skills/dataiku/references/govern.md`. Blueprint authoring (versions, fields, hooks, views, signoff config): `skills/dataiku/references/govern-blueprint-designer.md`.

```bash
# Instance
dku govern whoami [-o FORMAT]
dku govern info [-o FORMAT]

# Artifacts — run `blueprint fields BP` first to discover schema
dku govern artifact list [-b BP] [-n NAME] [--archived|--no-archived] [--page-size N] [--all] [-o FORMAT]
dku govern artifact get ARTIFACT_ID [-o FORMAT]
dku govern artifact create (-b BP -n NAME [-f key=value ...] | --definition JSON) [-o FORMAT]
dku govern artifact set-field ARTIFACT_ID FIELD_ID VALUE
dku govern artifact set-definition ARTIFACT_ID --definition JSON
dku govern artifact delete ARTIFACT_ID --confirm

# Blueprints (read-side only — authoring verbs live in govern-blueprint-designer.md)
dku govern blueprint list [-o FORMAT]
dku govern blueprint get BP_ID [-o FORMAT]
dku govern blueprint list-versions BP_ID [-o FORMAT]
dku govern blueprint get-version BP_ID VER_ID [-o FORMAT]        # alias: get-version-definition
dku govern blueprint describe-version BP_ID VER_ID                # summary + structural lint
dku govern blueprint fields BP_ID [--version VER_ID] [-o FORMAT]
dku govern blueprint create IDENTIFIER --definition JSON [-o FORMAT]
dku govern blueprint set-definition BP_ID --definition JSON
dku govern blueprint delete BP_ID --confirm

# Sign-offs
dku govern signoff create          ARTIFACT_ID STEP_ID
dku govern signoff list            ARTIFACT_ID                                            [-o FORMAT]
dku govern signoff get             ARTIFACT_ID STEP_ID                                    [-o FORMAT]
dku govern signoff update-status   ARTIFACT_ID STEP_ID STATUS
dku govern signoff add-feedback    ARTIFACT_ID STEP_ID -g GROUP_ID -s STATUS [-c COMMENT]
dku govern signoff add-approval    ARTIFACT_ID STEP_ID            -s STATUS [-c COMMENT]
dku govern signoff delegate-feedback  ARTIFACT_ID STEP_ID -g GROUP_ID --users-container JSON
dku govern signoff delegate-approval  ARTIFACT_ID STEP_ID            --users-container JSON
dku govern signoff list-feedbacks  ARTIFACT_ID STEP_ID                                    [-o FORMAT]
dku govern signoff get-feedback    ARTIFACT_ID STEP_ID FEEDBACK_ID                        [-o FORMAT]
dku govern signoff get-approval    ARTIFACT_ID STEP_ID                                    [-o FORMAT]

# Roles / Custom pages (same CRUD shape — ID prefixes `ro.` / `cp.`)
dku govern role        {list | get ID | create IDENTIFIER --definition JSON | set-definition ID --definition JSON | delete ID --confirm}
dku govern custom-page {list | get ID | create IDENTIFIER --definition JSON | set-definition ID --definition JSON | delete ID --confirm}

# Users / Groups (admin)
dku govern user list [-o FORMAT]
dku govern user get LOGIN [-o FORMAT]
dku govern user create LOGIN --password PASS [--display-name NAME] [--email EMAIL] [--group G ...] [--profile P] [--source-type LOCAL|LDAP]
dku govern user {create-bulk | edit-bulk | delete-bulk} --definition JSON [--confirm] [-o FORMAT]
dku govern user get-own [-o FORMAT]                                   # user-session auth only
dku govern user list-activity [--enabled-only] [-o FORMAT]
dku govern group {list | get GROUP_NAME | create GROUP_NAME [--description D] [--source-type LOCAL|LDAP] | delete GROUP_NAME --confirm}

# Time series (timestamps = epoch ms; push-values upserts by default, `--no-upsert` skips existing)
dku govern time-series create [--datapoints JSON] [-o FORMAT]
dku govern time-series get TS_ID [--min EPOCH_MS] [--max EPOCH_MS] [-o FORMAT]
dku govern time-series push-values TS_ID --datapoints JSON [--no-upsert]
dku govern time-series delete TS_ID [--min EPOCH_MS] [--max EPOCH_MS] --confirm

# Files — returned `uf.<id>` goes into UPLOADED_FILE fields as array: '["uf.1"]'
dku govern file upload PATH [-o FORMAT]
dku govern file get FILE_ID [-o FORMAT]
dku govern file download FILE_ID [--dest PATH]
```

- `artifact create`: ergonomic (`-b`/`-n`/`-f`) or raw (`--definition`). `set-field` updates one field without round-tripping the full definition
- `blueprint fields` auto-resolves the ACTIVE version; prints field IDs, types, required flags, categories
- `blueprint describe-version` pretty-prints fields/workflow/signoffs/views + flags silent-failure patterns (empty `uiDefinition.views`, missing `artifactPageViewId`, fields not in any view, signoffs on non-existent steps). Prefer over `get-version | jq` when authoring
- Sign-off state machine: `NOT_STARTED → WAITING_FOR_FEEDBACK → WAITING_FOR_APPROVAL → APPROVED|REJECTED|ABANDONED`. Reset requires passing through `ABANDONED`. Feedback statuses: `APPROVED|MINOR_ISSUE|MAJOR_ISSUE`; approval: `APPROVED|REJECTED|ABANDONED`
- `--users-container` JSON: `'{"type": "user", "login": "alice"}'` — `type` is **lowercase** (`user`/`group`/`role`/`global-api-key`)
- All `--definition` / `--datapoints` flags accept literal string, `@file.json`, or `-` (stdin)
- All `delete*` commands require `--confirm` / `-y`. `blueprint delete` needs every version + artifact gone first
