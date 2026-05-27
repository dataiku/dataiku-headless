# dku-cli Core Command Syntax

Exact command syntax for core project, data, flow, and automation operations. For safety, workflows, and gotchas read `safety.md`, `recipe-operations.md`, and `common-gotchas.md`.

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
dku dataset list [-P PROJECT] [-o FORMAT] [--own-only]   # Includes foreign/shared datasets by default; PROJECT column shows source
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
