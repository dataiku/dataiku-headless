# dku-cli Command Reference

Full reference for all `dku` commands. Read this when you need exact flags, argument names, or behavior details for a specific command group.

## Table of Contents

- [auth](#auth) — login, logout, status, list, switch
- [config](#config) — set, get, list, path, variables, set-variables
- [project](#project) — list, get, export, create, delete, duplicate, variables, set-variables, permissions, set-permissions, tags
- [dataset](#dataset) — list, schema, head, build, create, upload, delete, clear, get-definition, set-definition, set-schema
- [recipe](#recipe) — list, get, run, create, delete, set-code, get-code, set-definition, add-input, add-output
- [scenario](#scenario) — list, run, abort, status, create, delete, get-definition, set-definition
- [job](#job) — list, status, log, abort, wait
- [plugin](#plugin) — list, push, settings
- [code-env](#code-env) — list, get, create, delete, update
- [connection](#connection) — list, create, test
- [model](#model) — list, get, versions
- [folder](#folder) — list, ls, upload, download
- [llm](#llm) — list, completion, embeddings
- [webapp](#webapp) — list, start, stop, status
- [macro](#macro) — list, run
- [user](#user) — list, create
- [flow](#flow) — graph, zones, create-zone, propagate, sources, successors
- [library](#library) — list, read, write, delete, mkdir
- [agent](#agent) — list, create, get, delete, wake-up, shutdown, status, add-tool, set-llm
- [agent-tool](#agent-tool) — list, get, run, delete
- [knowledge](#knowledge) — list, create, get, build, search, delete
- [bundle](#bundle) — list, export, download, import, activate
- [api-service](#api-service) — list, create, get, create-package, list-packages
- [wiki](#wiki) — list, create, get
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
dku project create PROJECT_KEY --name NAME [--description DESC] [-o FORMAT]
dku project delete PROJECT_KEY --confirm
dku project duplicate PROJECT_KEY --target-key KEY --target-name NAME [-o FORMAT]
dku project variables [-P PROJECT] [-o FORMAT]
dku project set-variables [-P PROJECT] --set key=value [--set key2=value2]
dku project set-variables [-P PROJECT] --definition JSON
dku project permissions [-P PROJECT] [-o FORMAT]
dku project set-permissions [-P PROJECT] --definition JSON
dku project tags [-P PROJECT] [-o FORMAT]
```

- `delete` requires `--confirm` flag (safety guard)
- `set-variables --set` modifies individual standard vars; `--definition` replaces all

## dataset

All commands require project (`-P KEY` / `DKU_PROJECT` / config default).

```bash
dku dataset list [-P PROJECT] [-o FORMAT]
dku dataset schema DATASET_NAME [-P PROJECT] [-o FORMAT]
dku dataset head DATASET_NAME [-P PROJECT] [-n ROWS] [-o FORMAT]
dku dataset build DATASET_NAME [-P PROJECT] [--wait]
dku dataset create DATASET_NAME --type TYPE [-c CONNECTION] [-P PROJECT] [--definition JSON]
dku dataset upload DATASET_NAME FILE [-P PROJECT] [--no-autodetect]
dku dataset delete DATASET_NAME [-P PROJECT]
dku dataset clear DATASET_NAME [-P PROJECT]
dku dataset get-definition DATASET_NAME [-P PROJECT]
dku dataset set-definition DATASET_NAME [-P PROJECT] --definition JSON
dku dataset set-schema DATASET_NAME [-P PROJECT] --definition JSON
```

- `upload` auto-detects format + schema after upload (calls `autodetect_settings`)
- `upload --no-autodetect` skips detection (if you'll set format manually)
- `head` defaults to 10 rows, override with `-n`
- `build --wait` blocks until job completes
- `create --type UploadedFiles` for CSV upload targets

## recipe

```bash
dku recipe list [-P PROJECT] [-o FORMAT]
dku recipe get RECIPE_NAME [-P PROJECT] [-o FORMAT]
dku recipe run RECIPE_NAME [-P PROJECT] [--wait]
dku recipe create RECIPE_NAME --type TYPE --input DS --output DS [-P PROJECT]
dku recipe delete RECIPE_NAME [-P PROJECT]
dku recipe set-code RECIPE_NAME --code CODE [-P PROJECT]
dku recipe get-code RECIPE_NAME [-P PROJECT]
dku recipe set-definition RECIPE_NAME --definition JSON [-P PROJECT]
dku recipe add-input RECIPE_NAME --ref DS [--role main] [-P PROJECT]
dku recipe add-output RECIPE_NAME --ref DS [--role main] [-P PROJECT]
```

- `create` requires both `--input` and `--output` datasets to exist already
- `set-code` accepts `--code @file.py` to read from file
- `get-code` prints code to stdout (can redirect: `> recipe.py`)

## scenario

```bash
dku scenario list [-P PROJECT] [-o FORMAT]
dku scenario run SCENARIO_ID [-P PROJECT] [--wait]
dku scenario abort SCENARIO_ID [-P PROJECT]
dku scenario status SCENARIO_ID [-P PROJECT] [-o FORMAT]
dku scenario create NAME [--type step_based] [-P PROJECT] [--definition JSON]
dku scenario delete SCENARIO_ID [-P PROJECT]
dku scenario get-definition SCENARIO_ID [-P PROJECT]
dku scenario set-definition SCENARIO_ID --definition JSON [-P PROJECT]
```

## job

```bash
dku job list [-P PROJECT] [-o FORMAT]
dku job status JOB_ID [-P PROJECT] [-o FORMAT]
dku job log JOB_ID [-P PROJECT]
dku job abort JOB_ID [-P PROJECT]
dku job wait JOB_ID [-P PROJECT] [--timeout SECONDS]
```

## plugin

Instance-level (no project needed).

```bash
dku plugin list [-o FORMAT]
dku plugin push ZIP_PATH [--update/--install]
dku plugin settings PLUGIN_ID [-o FORMAT] [--set key=value ...]
```

- `push` reads plugin ID from `plugin.json` inside ZIP, auto-detects update vs install

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
dku llm list [-P PROJECT] [-o FORMAT]
dku llm completion LLM_ID MESSAGE [-P PROJECT] [--system MSG] [--json-output] [-o text|json]
dku llm embeddings LLM_ID --text TEXT [-P PROJECT]
```

- LLM IDs follow `provider:model` pattern (e.g., `openai:gpt-4o-mini`)
- `completion -o json` returns text + usage stats

## webapp

No create via API (DSS UI only).

```bash
dku webapp list [-P PROJECT] [-o FORMAT]
dku webapp start WEBAPP_ID [-P PROJECT]
dku webapp stop WEBAPP_ID [-P PROJECT]
dku webapp status WEBAPP_ID [-P PROJECT]
```

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
dku flow zones [-P PROJECT] [-o FORMAT]
dku flow create-zone NAME [-P PROJECT]
dku flow propagate [-P PROJECT] [-o FORMAT]
dku flow sources [-P PROJECT] [-o FORMAT]
dku flow successors NODE [-P PROJECT] [-o FORMAT]
```

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

## agent-tool

```bash
dku agent-tool list [-P PROJECT] [-o FORMAT]
dku agent-tool get TOOL_ID [-P PROJECT] [-o FORMAT]
dku agent-tool run TOOL_ID [--input JSON] [-P PROJECT] [-o FORMAT]
dku agent-tool delete TOOL_ID [-P PROJECT]
```

## knowledge

Knowledge banks.

```bash
dku knowledge list [-P PROJECT] [-o FORMAT]
dku knowledge create NAME [-P PROJECT]
dku knowledge get KB_ID [-P PROJECT] [-o FORMAT]
dku knowledge build KB_ID [-P PROJECT] [--wait]
dku knowledge search KB_ID --query TEXT [--max-documents N] [-P PROJECT] [-o FORMAT]
dku knowledge delete KB_ID [-P PROJECT]
```

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
dku wiki create TITLE [--body TEXT] [-P PROJECT]
dku wiki get ARTICLE_ID [-P PROJECT] [-o FORMAT]
```

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
