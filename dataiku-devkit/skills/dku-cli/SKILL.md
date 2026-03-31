---
name: dku-cli
description: Use the `dku` CLI to interact with Dataiku DSS from the terminal. Use when the user asks to list/inspect/manage/create/delete DSS projects, datasets, recipes, scenarios, jobs, plugins, code environments, connections, models, folders, LLMs, webapps, dashboards, insights, macros, users, flow, agents, knowledge banks, bundles, API services, wiki, SQL, or library files — via shell commands. Also use when automating DSS operations in CI/CD pipelines, composing DSS queries with shell pipes, or when `dku` commands are the most efficient way to get information. Prefer this over the Python API skill when the task is a quick query, pipeline script, or shell-composable operation.
triggers:
  - dku
  - dku-cli
  - dataiku cli
  - dss command
  - list projects
  - list datasets
  - dku recipe
  - dku scenario
  - dku agent
metadata:
  author: dataiku
  version: "1.0.0"
  tags: dataiku, dss, cli, kubectl, devops
---

> **Agent Cheat Sheet (read this first)**
>
> 1. **STOP — DO NOT write Python for joins, geo joins, aggregations, dedup, sort, filter, stack, or window ops.** Use `create-join`, `create-geojoin`, `create-fuzzy-join`, `create-group`, `create-stack`, `create-distinct`, `create-sort`, `create-filter`, `create-window`, `create-topn`. Python is ONLY for custom logic (scoring, feature engineering, API calls). **One join recipe handles 3+ datasets** — prefer a single multi-input join over cascading separate ones. **NEVER write Python haversine — use `create-geojoin` instead.** See [Recipe Decision Tree](#recipe-decision-tree).
> 2. **Use `dku ml` for ML — not Python.** `dku ml create-prediction` + `dku ml train` + `dku ml deploy` covers prediction, clustering, timeseries, and causal. Python ONLY for custom model architectures.
> 3. **Visual recipes auto-apply schema.** `create-join`/`create-group`/etc. auto-propagate output schemas. For manual control: `dku recipe apply-schema RECIPE -P PROJ`, or `--auto-update-schema` on build.
> 4. **Upload = UploadedFiles.** `dku dataset create NAME --type UploadedFiles -P PROJ`. Never Filesystem for uploads.
> 5. **Recipe create auto-creates output.** Visual recipe commands auto-create the output dataset. Do NOT pre-create it.
> 6. **Chain everything.** All related commands in ONE `&&`-chained Bash call. Never separate tool calls.
> 7. **Set project once, not per-command.** `dku config set default_project KEY` (persistent) or `export DKU_PROJECT=KEY` (session) — then omit `-P` from all subsequent commands.
> 8. **SVA blocks require agent ID, not name.** `dku agent-block` commands reject names — use the ID from `dku agent list -o json`. On DSS 14.5+, blocks live in `structuredAgentSettings` (not `toolsUsingAgentSettings`), use `GENERATE_OUTPUT` (not `EMIT_OUTPUT`). Always inspect a real agent first: `dku agent get <ID> -o json -P PROJ`.

# dku-cli

`dku` is a kubectl-style CLI for Dataiku DSS. It wraps `dataikuapi` with auth management, output formatting, and composable shell commands. **~244 commands** across 32 groups.

## Prerequisites

The `dku` CLI must be installed. Check with:

```bash
dku --version
```

If not installed:

```bash
uv tool install git+https://github.com/dataiku/dataiku-cli.git
dku auth login          # authenticate to your DSS instance
```

> **CRITICAL — Chaining Rule:** Always `&&`-chain related `dku` commands in a **single Bash tool call**. Each separate tool call costs a full agent turn (~$0.05 + 3s). A 10-command workflow should be 1 tool call, not 10. See [Chaining Patterns](#chaining-patterns) for templates.

## When to Use dku vs Python API

| Use `dku` CLI | Use Python API directly |
|---|---|
| Quick queries: list, inspect, status | Complex multi-step workflows |
| CRUD: create, delete, configure resources | DataFrame operations (pandas) |
| Shell scripts / CI/CD pipelines | Custom transformations |
| Piping output to jq/grep/awk | Bulk programmatic operations |
| End-to-end project automation | When CLI doesn't cover the API |

> **Within the CLI, visual recipes vs Python recipes is a separate choice.** The table above is CLI vs Python API. For recipe type selection, see [Recipe Decision Tree](#recipe-decision-tree). Default to visual recipes; use Python recipes only for custom logic.

## Setup

```bash
# Install
uv tool install git+https://github.com/dataiku/dataiku-cli.git

# Authenticate (interactive)
dku auth login

# Authenticate (non-interactive / CI)
dku auth login --url https://dss.example.com --api-key YOUR_KEY --profile prod

# Environment variables (CI/CD)
export DKU_URL=https://dss.example.com
export DKU_API_KEY=your-api-key
export DKU_PROJECT=MY_PROJECT
```

## Command Pattern

Every command follows: `dku <noun> <verb> [ARGS] [OPTIONS]`

### Global Options (on every command)

| Flag | Env Var | Purpose |
|---|---|---|
| `--url URL` | `DKU_URL` | DSS instance URL |
| `--api-key KEY` | `DKU_API_KEY` | API key |
| `--profile NAME` / `-p` | — | Auth profile name |
| `--quiet` / `-q` | — | Suppress info/success messages (stderr) |
| `--errors text|json` | — | Error output format on stderr |

### Project Resolution

Many commands need a project. Resolution order:
1. `--project KEY` / `-P KEY` flag
2. `DKU_PROJECT` env var
3. `dku config set default_project KEY` saved default

### Output Formats

All list/get commands support `-o FORMAT`:

| Format | Flag | Best for |
|---|---|---|
| Rich table | `-o table` (default) | Human reading |
| JSON | `-o json` | Piping to jq, programmatic use |
| CSV | `-o csv` | Spreadsheets, further processing |

JSON goes to stdout (clean for piping). Status messages go to stderr.

Use `--errors json` when the failure path also needs to be machine-readable. Do not merge stderr into stdout before `jq`; parse stdout on success, stderr on failure.

```bash
dku --errors json recipe get missing_recipe -P PROJ -o json
```

### JSON Input

Creation/mutation commands accept `--definition JSON`:
- Literal JSON string: `--definition '{"key": "value"}'`
- From file: `--definition @config.json`
- From stdin: `--definition -`

Code commands accept `--code` with the same patterns: literal string, `@file.py`, or `-` for stdin (heredoc-friendly).

## Core Workflow: Create Project + Upload Data

This is the most common operation. Get it right first time — wrong dataset types waste 10+ commands debugging.

### Dataset Types (CRITICAL)

| Type | Create Flag | Supports Upload? | Supports Build? | Use For |
|---|---|---|---|---|
| **`UploadedFiles`** | `--type UploadedFiles` | **Yes** | No | CSV/file upload via CLI |
| `Filesystem` | `--type Filesystem -c CONNECTION` | **No** | Yes | Recipe outputs, managed storage |
| (none/default) | (no `--type`) | **No** | Yes | Creates Filesystem on default connection |

**Rule: If you need to upload a file, you MUST use `--type UploadedFiles`.** Filesystem datasets reject `dku dataset upload`. There is no workaround — delete and recreate with the correct type.

### Complete Project Setup (copy-paste template)

```bash
# 1. Create project (--if-not-exists = safe to re-run)
dku project create MY_PROJ --name "My Project" --if-not-exists && \

# 2. Generate synthetic CSV
cat > /tmp/data.csv << 'EOF'
id,name,email,age,city
1,Alice,alice@example.com,32,Amsterdam
2,Bob,bob@example.com,28,Berlin
3,Clara,clara@example.com,35,Paris
EOF

# 3. Create dataset (MUST be UploadedFiles for upload)
dku dataset create my_data --type UploadedFiles -P MY_PROJ && \

# 4. Upload CSV (auto-detects format + schema)
dku dataset upload my_data /tmp/data.csv -P MY_PROJ && \

# 5. Verify
dku dataset schema my_data -P MY_PROJ && \
dku dataset head my_data -P MY_PROJ -n 3
```

### Multi-Dataset Project (e-commerce example)

```bash
# Create project + 3 datasets + upload — ALL ONE CALL
dku project create ECOM --name "E-Commerce" --if-not-exists && \

# Generate CSVs
cat > /tmp/customers.csv << 'EOF'
customer_id,name,email,country
C001,Alice,alice@ex.com,France
C002,Bob,bob@ex.com,USA
EOF

cat > /tmp/orders.csv << 'EOF'
order_id,customer_id,product,quantity,price
O001,C001,Widget,2,29.99
O002,C002,Gadget,1,49.99
EOF

# Create all as UploadedFiles (required for upload)
dku dataset create customers --type UploadedFiles -P ECOM && \
dku dataset create orders --type UploadedFiles -P ECOM && \

# Upload all
dku dataset upload customers /tmp/customers.csv -P ECOM && \
dku dataset upload orders /tmp/orders.csv -P ECOM
```

### Creating Recipes (CRITICAL — visual first, Python last)

**ALWAYS prefer visual recipes over Python.** DSS has purpose-built visual recipes for common data operations. Python recipes are for custom logic only.

#### Recipe Decision Tree

**Follow this exactly. Do NOT skip to Python.**

```
Is the task a join/merge?           → create-join -i ds1 -i ds2 [-i ds3...]  (NEVER pd.merge)
  Joining 3+ datasets?             → Prefer ONE create-join with all -i flags over cascading joins
Is the task a geospatial join?      → create-geojoin -i ds1 -i ds2  (NEVER Python haversine)
Is the task fuzzy/approximate match?→ create-fuzzy-join -i ds1 -i ds2  (NEVER fuzzywuzzy in Python)
Is the task aggregation/groupby?    → create-group -k col --agg col:sum,avg  (NEVER df.groupby)
Is the task stacking/union/concat?  → create-stack  (NEVER pd.concat)
Is the task dedup/distinct?         → create-distinct  (NEVER df.drop_duplicates)
Is the task sorting?                → create-sort  (NEVER df.sort_values)
Is the task filtering rows?         → create-filter  (NEVER df[condition])
Is the task window/rank function?   → create-window  (NEVER df.groupby().transform)
Is the task top/bottom N?           → create-topn  (NEVER df.nlargest)
Is the task a passthrough/copy?     → create -t sync  (NEVER Python passthrough)
None of the above?                  → THEN use Python: create NAME -t python
```

**Python IS correct for:** custom scoring, feature engineering, API calls, ML inference, regex parsing, multi-step logic that can't be expressed as chained visual recipes.

#### Visual Recipe Selection Guide

| Task | Command | NOT this |
|------|---------|----------|
| **Join datasets** | `dku recipe create-join NAME -i ds1 -i ds2 [-i ds3...] --output-ds out -P PROJ` | ~~pd.merge()~~ |
| **Geo join (spatial)** | `dku recipe create-geojoin NAME -i ds1 -i ds2 --output-ds out --operator WITHIN_DISTANCE --distance 5000 -P PROJ` | ~~haversine in Python~~ |
| **Fuzzy join (approx match)** | `dku recipe create-fuzzy-join NAME -i ds1 -i ds2 --output-ds out --fuzzy-key name -P PROJ` | ~~fuzzywuzzy~~ |
| **Aggregate/group by** | `dku recipe create-group NAME -i ds --output-ds out -k col -P PROJ` | ~~df.groupby()~~ |
| **Stack/union** | `dku recipe create-stack NAME -i ds1 -i ds2 --output-ds out -P PROJ` | ~~pd.concat()~~ |
| **Deduplicate** | `dku recipe create-distinct NAME -i ds --output-ds out -P PROJ` | ~~df.drop_duplicates()~~ |
| **Sort** | `dku recipe create-sort NAME -i ds --output-ds out -P PROJ` | ~~df.sort_values()~~ |
| **Filter rows** | `dku recipe create-filter NAME -i ds --output-ds out -P PROJ` | ~~df[df.x > y]~~ |
| **Window functions** | `dku recipe create-window NAME -i ds --output-ds out -P PROJ` | ~~df.groupby().transform()~~ |
| **Top N** | `dku recipe create-topn NAME -i ds --output-ds out -P PROJ` | ~~df.nlargest()~~ |
| **Split by condition** | `dku recipe create-split NAME -i ds --output-ds out -P PROJ` | ~~manual filtering~~ |
| **Custom logic ONLY** | `dku recipe create NAME -t python -i ds --output-ds out -P PROJ` | Last resort |

Visual recipe commands auto-create the output dataset. **`create-join` and `create-group` are fully configured via CLI flags.** For `create-sort`, `create-filter`, `create-window`, `create-topn`, and `create-split`: the recipe is created but requires configuration (sort columns, filter conditions, window partitions, etc.) via the DSS UI or `dku recipe set-definition` before it can be built — otherwise `dku flow check` will report a fatal error on that recipe.

#### Join Example (replaces Python merge)

**One join recipe can handle multiple datasets — prefer this over cascading separate joins.**

```bash
# BAD — cascading joins (3 recipes for 4 datasets)
dku recipe create-join join_1 -i customers -i orders --output-ds temp1 -P PROJ && \
dku recipe create-join join_2 -i temp1 -i products --output-ds temp2 -P PROJ && \
dku recipe create-join join_3 -i temp2 -i regions --output-ds enriched -P PROJ

# GOOD — single join recipe with all inputs (1 recipe for 4 datasets)
dku recipe create-join enrich_all \
  -i customers -i orders -i products -i regions \
  --output-ds enriched \
  --join-key customer_id \
  --join-key 1:product_id \
  --join-key 2:region_id \
  -P PROJ
```

Join indices: unprefixed `--join-key col` targets join 0 (customers↔orders). `1:col` targets join 1 (customers↔products). `2:col` targets join 2 (customers↔regions). Keys auto-detect from matching column names if omitted.

```bash
# Simple 2-dataset join (auto-detects key if column names match)
dku recipe create-join join_orders_customers \
  -i orders -i customers \
  --output-ds enriched_orders \
  --join-key customer_id \
  -P PROJ && \

# Build (schema auto-applied by create-join)
dku dataset build enriched_orders -P PROJ --wait
```

#### Group Example (replaces Python groupby)

```bash
# Aggregate orders by customer with SUM and AVG — DSS visual recipe
dku recipe create-group summarize_by_customer \
  -i orders \
  --output-ds customer_summary \
  -k customer_id \
  --agg "amount:sum,avg" \
  --agg "order_id:count" \
  -P PROJ && \

# Build (schema auto-applied by create-group)
dku dataset build customer_summary -P PROJ --wait
```

#### Python Recipe (ONLY when visual recipes can't express the logic)

```bash
# Python recipe — for custom transformations, computed columns, ML scoring
# --connection is REQUIRED on instances without a default managed connection
dku recipe create compute_risk_score -t python -i customer_features --output-ds risk_scores --connection filesystem_managed -P PROJ && \
dku recipe set-code compute_risk_score -P PROJ --code @score.py
```

**Flags for `dku recipe create` (Python/SQL):**
- `--type python` / `-t python` — recipe type
- `--input NAME` / `-i NAME` / `--input-ds NAME` — input dataset (MUST already exist)
- `--output-ds NAME` — output dataset (auto-created for code recipes)
- `--connection NAME` / `-c NAME` — connection for output dataset (required if no default managed connection; use `dku connection list` to find one)
- `-P PROJECT` — project key

**Adding extra inputs** after creation:

```bash
dku recipe add-input RECIPE_NAME DATASET_NAME -P PROJ
```

> **Note on Filesystem datasets:** If you need to manually create a Filesystem dataset (rare — usually recipe create does this), you MUST specify `--connection`: `dku dataset create NAME --type Filesystem -c filesystem_managed -P PROJ`. Without `-c`, it errors. Run `dku connection list` to find available connections.

> **UploadedFiles on cloud DSS:** If `dku dataset create NAME --type UploadedFiles` fails with "Cannot create dataset without a target connection", add `--connection <NAME>` (e.g. `--connection dataiku-managed-storage`). The CLI auto-detects the upload connection when possible, but some cloud instances require it explicitly.

#### Prepare Recipe Steps (replaces Python column transforms)

Use prepare recipe step commands instead of Python for computed columns, renames, filters, and data cleaning:

```bash
# Create prepare recipe (output must exist first, or use create-sort/etc. which auto-create)
dku recipe create prep1 -t prepare -i raw_data --output-ds cleaned_data -P PROJ && \

# Add computed column (GREL expression)
dku recipe add-formula prep1 --column revenue --expr "price * quantity" -P PROJ && \

# Rename column
dku recipe add-rename prep1 --from country --to region -P PROJ && \

# Delete columns
dku recipe add-delete-columns prep1 --columns "temp_col,debug_col" -P PROJ && \

# Filter rows by formula
dku recipe add-filter-rows prep1 --formula "price > 0" --action KEEP_ROW -P PROJ && \

# Fill empty values
dku recipe add-fill-empty prep1 --column status --value "unknown" -P PROJ && \

# Find and replace
dku recipe add-find-replace prep1 --column country --find "USA" --replace "United States" -P PROJ && \

# List all steps
dku recipe list-steps prep1 -P PROJ && \

# Build with schema update
dku dataset build cleaned_data -P PROJ --wait --auto-update-schema
```

| Command | Key Flags | Python Equivalent |
|---------|-----------|-------------------|
| `add-formula` | `--expr GREL --column COL` | `df["col"] = expr` |
| `add-rename` | `--from OLD --to NEW` or `--mappings '{"a":"b"}'` | `df.rename()` |
| `add-delete-columns` | `--columns "a,b,c"` | `df.drop(columns=[...])` |
| `add-filter-rows` | `--formula GREL --action KEEP_ROW\|REMOVE_ROW` or `--column COL --values "a,b"` | `df[df.x > y]` |
| `add-fill-empty` | `--column COL --value VAL` | `df.fillna()` |
| `add-find-replace` | `--column COL --find X --replace Y [--matching SUBSTRING]` | `df.str.replace()` |
| `add-fold` | `--columns "a,b,c" --key-column K --value-column V` | `pd.melt()` |
| `add-geopoint` | `--lat-column LAT --lon-column LON` | Manual WKT formatting |
| `add-geodistance` | `--from-column A --to-column B` | Haversine in Python |

Step management: `list-steps`, `get-step INDEX`, `remove-step INDEX`, `enable-step INDEX`, `disable-step INDEX`.

### Deleting Datasets and Projects

Both `dku dataset delete` and `dku project delete` support `--yes` / `-y` to skip confirmation:

```bash
# Dataset delete (prompts without --yes)
dku dataset delete my_data -P MY_PROJ --yes

# Project delete (requires --confirm, --yes, or -y)
dku project delete MY_PROJ --yes
```

---

## Quick Reference

For flag details on any command, run `dku <noun> <verb> --help`.

### Command Groups

| Group | Verbs | Needs Project? |
|---|---|---|
| `auth` | login, logout, status, list, switch | No |
| `config` | set, get, list, path, variables, set-variables | No |
| `project` | list, get, export, create, delete, duplicate, set-metadata, variables, set-variables, permissions, set-permissions, tags | No |
| `plugin` | list, get, push, delete, settings, create-code-env, set-code-env, update-code-env, usages | No |
| `code-env` | list, get, create, delete, update | No |
| `connection` | list, create, test | No (admin) |
| `user` | list, create | No (admin) |
| `sql` | query | No |
| `dataset` | list, schema, head, build, create, upload, delete, clear, get-definition, set-definition, set-schema | Yes |
| `dq` | list, create, compute, status, results, delete, project-status | Yes |
| `recipe` | list, get, run, create, delete, set-code, get-code, set-definition, add-input, add-output, check-schema, apply-schema, **create-join, create-geojoin, create-fuzzy-join, create-group, create-stack, create-distinct, create-sort, create-filter, create-window, create-split, create-topn, create-pivot, create-sampling**, create-embed, create-embed-docs, create-extract, create-llm-eval, create-agent-eval, **add-formula, add-rename, add-filter-rows, add-fill-empty, add-delete-columns, add-find-replace, add-fold, add-geopoint, add-geodistance**, list-steps, get-step, remove-step, enable-step, disable-step | Yes |
| `scenario` | list, run, abort, status, create, delete, get-definition, set-definition | Yes |
| `job` | list, run, status, log, abort, wait | Yes |
| `model` | list, get, versions, set-active-version, metrics, delete-version | Yes |
| `ml` | create-prediction, create-clustering, create-timeseries, create-causal, list, status, train, models, details, deploy, redeploy, settings, algorithms, set-algorithm, delete | Yes |
| `analysis` | list, create, get, delete, tasks | Yes |
| `evaluation-store` | list, create, get, evaluations, latest, build, delete | Yes |
| `folder` | list, ls, upload, download | Yes |
| `llm` | list, completion, embeddings | Yes |
| `webapp` | list, start, stop, status, get-definition, set-definition | Yes |
| `dashboard` | list, get, create, delete, get-definition, set-definition | Yes |
| `insight` | list, get, create, delete, get-definition, set-definition | Yes |
| `macro` | list, run | Yes |
| `flow` | graph, zones, create-zone, propagate, check, sources, successors | Yes |
| `library` | list, read, write, delete, mkdir | Yes |
| `agent` | list, create, get, delete, wake-up, shutdown, status, add-tool, set-prompt, set-llm | Yes |
| `agent-block` | list, get, add, remove, connect, disconnect, set-start, set-mode, get-graph, set-graph | Yes |
| `agent-tool` | list, get, run, delete, **create**, set-definition, types | Yes (except `types`) |
| `knowledge` | list, create, get, set-definition, build, search, delete | Yes |
| `bundle` | list, export, download, import, activate | Yes |
| `api-service` | list, create, get, create-package, list-packages | Yes |
| `wiki` | list, create, get, update, delete | Yes |
| (root) | whoami | No |

For full command syntax with examples, see `references/commands.md`. For flag details, run `dku <noun> <verb> --help`.

Key notes:
- `dku llm list` defaults to `GENERIC_COMPLETION`. Pass `--purpose TEXT_EMBEDDING_EXTRACTION` for embedding models.
- `dku llm embeddings` rejects completion-only model IDs — list embedding models first.
- Prefer `dku ... -o json | jq ...` on success paths. Avoid `2>&1 | jq` — stderr has error payloads, not success objects.

## Chaining Patterns

**NEVER issue related `dku` commands as separate tool calls.** Chain with `&&` in ONE Bash call. Separate calls = separate agent turns = 2x slower, 2.5x more expensive.

### Data Pipeline (1 tool call)

```bash
# Project + datasets + visual recipes + build — all one call
dku project create MY_PROJ --name "My Project" --if-not-exists && \
dku dataset create raw_data --type UploadedFiles -P MY_PROJ && \
dku dataset upload raw_data data.csv -P MY_PROJ && \
dku dataset create lookups --type UploadedFiles -P MY_PROJ && \
dku dataset upload lookups lookups.csv -P MY_PROJ && \
dku recipe create-join enrich -i raw_data -i lookups --output-ds enriched -P MY_PROJ && \
dku recipe create-group summarize -i enriched --output-ds summary -k category -P MY_PROJ && \
dku scenario create daily_build -P MY_PROJ
```

### Agent + Knowledge Bank (1 tool call)

```bash
# First, find an embedding model for the knowledge bank
dku llm list --purpose TEXT_EMBEDDING_EXTRACTION -P MY_PROJ -o json | jq -r '.[0].id'

# Create agent with tools and knowledge — all one call
dku agent create my_agent -P MY_PROJ && \
dku agent set-llm my_agent --llm-id openai:gpt-4o -P MY_PROJ && \
dku knowledge create my_kb --embedding-llm "openai:conn:text-embedding-3-small" -P MY_PROJ && \
dku knowledge build my_kb -P MY_PROJ --wait && \
dku agent add-tool my_agent --tool my_tool -P MY_PROJ
```

### ML Pipeline (1 tool call)

```bash
# Create prediction task, train, deploy to flow — all one call
dku ml create-prediction customers churn --type BINARY_CLASSIFICATION -P MY_PROJ -o json && \
dku ml train ANALYSIS_ID MLTASK_ID -P MY_PROJ -o json && \
dku ml deploy ANALYSIS_ID MLTASK_ID MODEL_ID --name ChurnModel --train-dataset customers -P MY_PROJ
```

**Typical ML workflow:**
1. `dku ml create-prediction DS TARGET -P PROJ` — creates analysis + ML task, returns `analysis_id` and `mltask_id`
2. `dku ml algorithms AID TID -P PROJ -o json | jq -r '.[].name'` — see available algorithm names (JSON key is `name`)
3. `dku ml set-algorithm AID TID --disable-all --enable XGBOOST_REGRESSION --enable RANDOM_FOREST_REGRESSION -P PROJ` — tune algorithms (use exact algorithm names from step 2)
4. `dku ml train AID TID -P PROJ -o json | jq -r '.model_ids[0]'` — train and get model IDs
5. `dku ml models AID TID -P PROJ -o json | jq '.[] | select(.state=="DONE") | .id'` — list DONE models (JSON key is `id`, not `model_id`)
6. `dku ml details AID TID MODEL_ID -P PROJ` — check metrics
7. `dku ml deploy AID TID MODEL_ID --name MyModel --train-dataset DS -P PROJ` — deploy to flow (model must be in DONE state)
7. `dku model set-active-version MODEL_ID VERSION_ID -P PROJ` — activate specific version
8. `dku model metrics MODEL_ID -P PROJ` — check deployed model metrics

### Deploy (1 tool call)

```bash
# Export + download bundle — all one call
dku bundle export v1 -P MY_PROJ && \
dku bundle download v1 -P MY_PROJ --dest ./bundles
```

### Plugin Lifecycle (1 tool call)

```bash
# First install: push + create code env + assign it
dku plugin push plugin.zip --install && \
dku plugin create-code-env my-plugin && \
dku plugin set-code-env my-plugin plugin_my_plugin_managed

# Update: push + rebuild code env (if deps changed)
dku plugin push plugin.zip && \
dku plugin update-code-env my-plugin

# Check plugin state
dku plugin get my-plugin -o json
dku plugin usages my-plugin

# Discover plugin recipe types
dku plugin recipes                      # all plugins
dku plugin recipes my-plugin -o json    # specific plugin

# Create a plugin recipe (type = CustomCode_<pluginId>_<recipeId>)
dku recipe create my_step -t CustomCode_my-plugin_my-recipe \
  -i input_ds --output-ds output_ds --params '{"key": "val"}' -P PROJ
```

### Shell Variable Capture

```bash
# When a downstream command needs output from an upstream one
JOB_ID=$(dku dataset build output -P PROJ 2>/dev/null | sed -n 's/.*Job ID: //p') && \
dku job wait "$JOB_ID" -P PROJ --timeout 300
```

### Safe JSON Piping

```bash
# Success path: parse stdout only
dku recipe get my_recipe -P PROJ -o json | jq '.type'

# Failure path: request machine-readable stderr
if ! dku --errors json recipe get missing_recipe -P PROJ -o json >out.json 2>err.json; then
  jq '.error.code, .error.message' err.json
fi
```

### Anti-pattern

```bash
# BAD — 3 separate tool calls (3 turns, ~$0.15, ~9s overhead):
# Tool call 1: dku dataset create raw_data --type UploadedFiles -P PROJ
# Tool call 2: dku dataset upload raw_data data.csv -P PROJ
# Tool call 3: dku dataset build output -P PROJ --wait

# GOOD — 1 tool call (1 turn, ~$0.05, ~3s overhead):
dku dataset create raw_data --type UploadedFiles -P PROJ && \
dku dataset upload raw_data data.csv -P PROJ && \
dku dataset build output -P PROJ --wait
```

## Composability Patterns

```bash
# Get all project keys as plain list
dku project list -o json | jq -r '.[].key'

# Find datasets with "customer" in name
dku dataset list -P PROJ -o json | jq '.[] | select(.name | test("customer"; "i"))'

# Export all projects
for key in $(dku project list -o json | jq -r '.[].key'); do
  dku project export "$key" -d ./exports
done

# Run scenario and check result
dku scenario run BUILD_ALL -P PROJ --wait || echo "Scenario failed"

# Build dataset in CI (quiet mode, non-interactive)
dku --quiet dataset build output_table -P PROJ --wait

# Dump recipe code to file
dku recipe get-code my_recipe -P PROJ > recipe.py
```

## Multi-Profile Workflow

```bash
# Set up multiple instances
dku auth login --profile dev --url https://dev-dss.example.com --api-key DEV_KEY
dku auth login --profile prod --url https://prod-dss.example.com --api-key PROD_KEY

# Switch context
dku auth switch prod

# Or use per-command override
dku project list --profile dev
dku project list --profile prod

# List profiles
dku auth list
```

## Critical Patterns (Battle-Tested)

These patterns come from real production usage. Ignoring them wastes 5-60 calls per run.

> **Dataset creation + upload is documented in [Core Workflow](#core-workflow-create-project--upload-data) above. Read that first.**

### Agent Creation

Agents require `--type`. Default is `TOOLS_USING_AGENT` (simple visual agent with tools). For block-graph agents, use `STRUCTURED_AGENT` — **type is immutable after creation**.

```bash
# Simple agent (tools only, no block graph)
dku agent create my_agent --type TOOLS_USING_AGENT -P PROJ && \
dku agent set-llm my_agent --llm-id "openai:gpt-4o-mini" -P PROJ && \
dku agent add-tool my_agent --tool my_tool -P PROJ

# Structured agent (block graph — DSS 14.5+)
dku agent create my_sva --type STRUCTURED_AGENT -P PROJ && \
dku agent set-llm my_sva --llm-id "openai:gpt-4o" -P PROJ
```

Valid types: `TOOLS_USING_AGENT`, `PYTHON_AGENT`, `PLUGIN_AGENT`, `STRUCTURED_AGENT`.

### Incremental Agent Build (test at each step)

1. Create ONE tool → `dku agent-tool run TOOL_ID -P PROJ` → verify it works
2. Create agent → `dku agent add-tool AGENT --tool TOOL_ID -P PROJ`
3. Add ONE block → `dku agent get AGENT -o json -P PROJ` → verify block persisted
4. Test agent → repeat for remaining tools/blocks

**DO NOT:** create all tools → build full graph → test at the end.

### Structured Visual Agent (SVA) Graph — Canonical Workflow

> **Version caveat:** Block type names and settings paths differ across DSS versions.
> - **DSS 13.x:** `STANDARD_REACT` / `EMIT_OUTPUT`, settings in `toolsUsingAgentSettings`
> - **DSS 14.5+:** `CORE_LOOP` / `GENERATE_OUTPUT`, settings in `structuredAgentSettings`
> - The CLI auto-detects the correct path. Always inspect a working agent first (cheat sheet rule 7).

**Use `set-graph` as the primary pattern.** The `dku agent-block connect` command does not support `PYTHON_CODE` blocks (exits with an error — use `validNextBlocksFromCode` + `NextBlock()` yield instead). For `STANDARD_REACT`/`CORE_LOOP`, `connect` works correctly (sets `defaultNextBlock` automatically). For any non-trivial graph, always use `get-graph → patch JSON → set-graph`:

```bash
# 1. Add all blocks
dku agent-block add AGENT_ID -b @parse_block.json --set-start -P PROJ && \
dku agent-block add AGENT_ID -b @routing_block.json -P PROJ && \
dku agent-block add AGENT_ID -b @python_code_block.json -P PROJ && \
dku agent-block add AGENT_ID -b @react_block.json -P PROJ

# 2. Export the graph
dku agent-block get-graph AGENT_ID -P PROJ -o json > /tmp/graph.json

# 3. Patch connections in Python (nextBlock, defaultNextBlock, etc.)
python3 -c "
import json
g = json.load(open('/tmp/graph.json'))
# wire blocks by editing g['blocks']
json.dump(g, open('/tmp/graph.json', 'w'))
"

# 4. Push the patched graph back
dku agent-block set-graph AGENT_ID -d @/tmp/graph.json -P PROJ
```

**`connect` is a convenience shortcut only.** Use it for simple `LLM_REQUEST → ROUTING`, `CORE_LOOP → GENERATE_OUTPUT`, or other direct wiring. For `PYTHON_CODE` blocks, `connect` will error — use `set-graph` with `validNextBlocksFromCode` and `NextBlock()` yield in `process()`.

### Agent Tool Creation (Two-Step Workflow)

Creating a plugin-based agent tool requires two separate commands — `agent-tool create` creates the tool instance, then `agent add-tool` attaches it to an agent.

```bash
# Step 1: Create the tool (returns a tool ID)
dku agent-tool create "Web Search" \
  --type Custom_agent_tool_google-search-tool_google-search-tool \
  -P PROJ

# Step 2: Attach to agent (use the tool ID from step 1)
dku agent add-tool AGENT_ID --tool TOOL_ID -P PROJ
```

**Discovering available tool types:**
```bash
# List available tool types (does NOT accept -P — this is project-independent)
dku agent-tool types
```

> **Gotcha:** `dku agent-tool types` is listed under the `agent-tool` group but does NOT accept a `-P` flag. Passing `-P` will throw an error. Run it without a project argument.

**Updating tool definitions:** Use `dku agent-tool set-definition` to update tool parameters after creation (e.g., inject an API key):
```bash
# Update specific fields (merges into existing definition)
dku agent-tool set-definition TOOL_ID -d '{"params": {"apiKey": "secret"}}' -P PROJ

# Or from a file
dku agent-tool set-definition TOOL_ID -d @tool-config.json -P PROJ
```

### LLM ID Format

LLM IDs in DSS follow the pattern `provider:connection:model`. Use `dku llm list` to discover available IDs:

```bash
# Completion models (default)
dku llm list -P PROJ -o json | jq -r '.[].id'

# Embedding models (MUST use --purpose for GenAI workflows)
dku llm list --purpose TEXT_EMBEDDING_EXTRACTION -P PROJ -o json | jq -r '.[].id'
```

### Adding extra inputs/outputs to a recipe

`add-input` and `add-output` take the dataset as a positional argument:

```bash
# Add a second input (e.g., for a join or lookup)
dku recipe add-input my_recipe second_dataset -P PROJ

# Add with a custom role (default is "main")
dku recipe add-input my_recipe lookup_table --role lookup -P PROJ

# Add an extra output
dku recipe add-output my_recipe extra_output -P PROJ
```

### Join Recipes — Column Names

DSS join recipes do NOT prefix column names by default. Columns from both datasets are merged as-is. Only conflicting column names (same name in both datasets) get prefixed with the dataset name (e.g., `customers_id` and `orders_id`). Plan downstream column references using the original names unless there's a conflict.

### Project Variables

Set project variables with `--set key=value` (repeatable) or `--definition` for full JSON replacement:

```bash
# Set individual standard variables (--set is repeatable)
dku project set-variables -P PROJ --set threshold=0.8 --set env=staging

# Replace ALL variables from JSON
dku project set-variables -P PROJ --definition '{"standard": {"key": "val"}, "local": {}}'

# Replace from file
dku project set-variables -P PROJ --definition @vars.json
```

**Common mistake:** `--json` does not exist. Use `--set key=value` for individual vars or `--definition JSON` for full replacement.

## Pipeline Building Best Practices

### Prefer Multi-Input Joins Over Cascading Joins

When joining 3+ datasets, a single multi-input join is usually cleaner than cascading separate join recipes — fewer recipes, no throwaway intermediate datasets.

```bash
# Cascading — 3 recipes, 2 intermediate datasets
dku recipe create-join join_ab -i A -i B --output-ds AB -P PROJ && \
dku recipe create-join join_abc -i AB -i C --output-ds ABC -P PROJ && \
dku recipe create-join join_abcd -i ABC -i D --output-ds final -P PROJ

# Single multi-input join — 1 recipe, no intermediates
dku recipe create-join join_all -i A -i B -i C -i D --output-ds final \
  --join-key id --join-key 1:id --join-key 2:id -P PROJ
```

`create-join` supports **2+ input datasets in a single recipe**. Each additional input creates a join pair indexed from 0. Use `--join-key N:col` to target specific pairs. Use separate joins when you need different join types per pair or need to filter/transform between joins.

### Anti-Pattern: Step-by-Step Builds (costs 50%+ extra tokens)

```bash
# BAD — each build is non-recursive, no schema updates.
# If schemas don't match between steps, every downstream build fails.
# Agent spends 10+ turns debugging schema mismatches.
dku dataset build ds_a -P PROJ --wait && \
dku dataset build ds_b -P PROJ --wait && \
dku dataset build ds_c -P PROJ --wait
```

### Correct Pattern: Wire First, Build Once

**Step 1:** Wire the entire pipeline (datasets + recipes + code) in one `&&` chain.
Note: `dku recipe create` auto-creates output datasets — do NOT pre-create them.

```bash
# Upload source data
dku dataset create raw_data --type UploadedFiles -P PROJ && \
dku dataset upload raw_data data.csv -P PROJ && \

# Recipe 1: raw_data -> cleaned (output auto-created)
dku recipe create clean_step --type python --input raw_data --output-ds cleaned --connection filesystem_managed -P PROJ && \
dku recipe set-code clean_step -P PROJ --code @clean.py && \

# Recipe 2: cleaned -> final (output auto-created)
dku recipe create agg_step --type python --input cleaned --output-ds final --connection filesystem_managed -P PROJ && \
dku recipe set-code agg_step -P PROJ --code @aggregate.py
```

**Step 2:** Build the final output with recursive + auto-schema (one command):

```bash
dku job run --target final -P PROJ \
  --type RECURSIVE_BUILD \
  --auto-update-schema \
  --wait
```

This single command traces upstream from `final`, builds all dependencies in order, and auto-updates output schemas before each recipe run. No manual propagation needed.

### Visual Recipe Pipeline: Wire First, Build Once

**Step 1:** Wire the entire pipeline with visual recipes in one `&&` chain.
Visual recipe commands auto-create managed output datasets.

```bash
# Upload source data
dku dataset create customers --type UploadedFiles -P PROJ && \
dku dataset upload customers /tmp/customers.csv -P PROJ && \
dku dataset create orders --type UploadedFiles -P PROJ && \
dku dataset upload orders /tmp/orders.csv -P PROJ && \

# Recipe 1: Join customers + orders (output auto-created)
dku recipe create-join enrich -i customers -i orders --output-ds enriched --join-key customer_id -P PROJ && \

# Recipe 2: Aggregate enriched by customer (output auto-created)
dku recipe create-group summarize -i enriched --output-ds summary -k customer_id --agg "amount:sum,avg" -P PROJ
```

**Step 2:** Build with auto-schema (handles apply-schema automatically):

```bash
dku job run --target summary -P PROJ \
  --type RECURSIVE_BUILD \
  --auto-update-schema \
  --wait
```

`--auto-update-schema` eliminates the need for manual `apply-schema` on each recipe when doing a full pipeline build.

### When to Use What

| Scenario | Command |
|---|---|
| Build one dataset (schema already correct) | `dku dataset build NAME --wait` |
| Build entire pipeline from leaf dataset | `dku job run --target NAME --type RECURSIVE_BUILD --auto-update-schema --wait` |
| Schema changed on source, propagate downstream | `dku flow propagate SOURCE_DS -P PROJ` |
| Check if a recipe's output schema is stale | `dku recipe check-schema RECIPE -P PROJ` |
| Apply pending schema updates for a recipe | `dku recipe apply-schema RECIPE -P PROJ` |
| Run consistency check on entire flow | `dku flow check -P PROJ` |
| Force rebuild everything | `dku job run --target NAME --type RECURSIVE_FORCED_BUILD --auto-update-schema --wait` |
| Build only missing outputs | `dku job run --target NAME --type RECURSIVE_MISSING_ONLY_BUILD --wait` |

### Build Types

| Type | Behavior |
|---|---|
| `NON_RECURSIVE_FORCED_BUILD` | Build only specified outputs (default) |
| `RECURSIVE_BUILD` | Build outputs + upstream dependencies that need building |
| `RECURSIVE_FORCED_BUILD` | Force-rebuild outputs + ALL upstream dependencies |
| `RECURSIVE_MISSING_ONLY_BUILD` | Build only outputs that have never been built |

### Schema Propagation vs Auto-Update Schema

- **`dku flow propagate SOURCE_DS`**: Propagates schema changes from a source dataset through downstream recipes. Use when you've changed a source schema and want to update downstream schemas WITHOUT building.
- **`--auto-update-schema` on build/run**: Updates schemas during the build. Use when you want to build AND fix schemas in one shot.
- **`dku recipe check-schema` + `apply-schema`**: Per-recipe schema inspection. Use when debugging a specific recipe's schema issues. Only works for visual recipes (not Python/R code recipes).

## Full Project Template (Copy-Paste)

This template covers the complete lifecycle in **3 tool calls**: setup, build, and extras. Use this when the task requires a project with pipeline + library + wiki + variables.

**Tool call 1 — Wire everything:**

```bash
# Create project (--if-not-exists = idempotent, safe to re-run)
dku project create MY_PROJ --name "My Project" --if-not-exists && \

# Upload source data (UploadedFiles for CSV upload)
dku dataset create raw_data --type UploadedFiles -P MY_PROJ && \
dku dataset upload raw_data /tmp/data.csv -P MY_PROJ && \

# Recipe 1: raw_data + lookup → enriched (VISUAL join — not Python)
dku recipe create-join join_enriched -i raw_data -i lookup --output-ds enriched --join-key id -P MY_PROJ && \

# Recipe 2: enriched → summary (VISUAL group — not Python)
dku recipe create-group compute_summary -i enriched --output-ds summary -k category --agg "amount:sum,avg" -P MY_PROJ && \

# Recipe 3: summary → scored (Python — ONLY because custom scoring logic)
dku recipe create compute_scored --type python --input summary --output-ds scored --connection filesystem_managed -P MY_PROJ && \
dku recipe set-code compute_scored -P MY_PROJ --code @score.py && \

# Library files
dku library write python/utils/helpers.py -P MY_PROJ --content @helpers.py && \

# Project variables
dku project set-variables -P MY_PROJ --set threshold=0.8 --set env=staging && \

# Scenario
dku scenario create daily_build --if-not-exists -P MY_PROJ && \

# Wiki (--if-not-exists = safe to re-run)
dku wiki create "Project Overview" --body "# My Project\nAutomated data pipeline." --if-not-exists -P MY_PROJ
```

**Tool call 2 — Build the pipeline:**

```bash
dku job run --target scored -P MY_PROJ \
  --type RECURSIVE_BUILD \
  --auto-update-schema \
  --wait
```

**Tool call 3 — Verify:**

```bash
dku dataset head scored -P MY_PROJ -n 5 && \
dku flow graph -P MY_PROJ -o json | jq '.nodes | keys'
```

---

## GenAI Recipe Types

### Finding Embedding Models (REQUIRED for GenAI workflows)

Most GenAI recipes need an embedding LLM ID. The default `dku llm list` only shows **completion** models — embedding models are hidden unless you specify `--purpose`:

```bash
# Find embedding models (REQUIRED before create-embed, knowledge create, etc.)
dku llm list --purpose TEXT_EMBEDDING_EXTRACTION -P PROJ

# Get just the IDs
dku llm list --purpose TEXT_EMBEDDING_EXTRACTION -P PROJ -o json | jq -r '.[].id'
```

Use the returned ID for `--embedding-llm` flags on `recipe create-embed`, `recipe create-embed-docs`, `recipe create-llm-eval`, `recipe create-agent-eval`, and `knowledge create`.

### API-Supported (full CLI creation)

| Command | dataikuapi Type | Purpose |
|---|---|---|
| `create-embed` | `nlp_llm_rag_embedding` | Embed text columns -> Knowledge Bank |
| `create-embed-docs` | `embed_documents` | Extract + embed documents -> Knowledge Bank |
| `create-extract` | `extract_content` | Extract structured content from docs (VLM) |
| `create-llm-eval` | `nlp_llm_evaluation` | Evaluate LLM outputs (RAG, QA, summarization) |
| `create-agent-eval` | `nlp_agent_evaluation` | Evaluate agent tool-calling accuracy |

`create-llm-eval` and `create-agent-eval` do not create datasets for you. If you pass `--output-ds` or `--output-metrics`, those datasets must already exist in DSS.

### UI-Only (NOT available via API)

These recipe types have **no dataikuapi builder classes** — create them in the DSS UI, then manage via `dku recipe get/set-definition/run`:

- **Prompt Recipe** (Prompt, Classify, Summarize, Extract, Simplify, Translate)
- **RAG Query Recipe**

Workaround: create via UI, then `dku recipe get RECIPE -P PROJ -o json > recipe_def.json` to capture the definition, and `dku recipe set-definition RECIPE -P PROJ --definition @recipe_def.json` to modify.

### RAG Evaluation Flow (1 tool call)

```bash
# End-to-end: embed data -> create eval -> configure -> run
dku recipe create-embed embed_step \
  --input qa_documents \
  --output-kb qa_kb \
  --embedding-llm "openai:text-embedding-3-small" \
  -P PROJ && \
dku recipe run embed_step -P PROJ --wait && \
dku dataset create eval_scored --type Filesystem -P PROJ && \
dku dataset create eval_metrics --type Filesystem -P PROJ && \
dku recipe create-llm-eval rag_eval \
  --input rag_responses \
  --eval-store my_eval_store \
  --output-ds eval_scored \
  --output-metrics eval_metrics \
  --task-type QUESTION_ANSWERING \
  --metrics "answerRelevancy,faithfulness,contextRelevancy" \
  --input-col question \
  --output-col answer \
  --ground-truth-col expected \
  --context-col context \
  --completion-llm "openai:gpt-4o" \
  --embedding-llm "openai:text-embedding-3-small" \
  -P PROJ && \
dku recipe run rag_eval -P PROJ --wait
```

### LLM Evaluation Metrics

| Metric Name | Task Type | Description |
|---|---|---|
| `answerRelevancy` | QA | Answer relevance to the question |
| `faithfulness` | QA | Answer grounded in provided context |
| `contextRelevancy` | QA | Retrieved context relevant to question |
| `toolCallExactMatch` | Agent | Exact match on tool calls |
| `toolCallPartialMatch` | Agent | Partial match on tool calls |
| `toolCallPrecisionRecallF1` | Agent | Precision/Recall/F1 for tool calls |
| `agentGoalAccuracyWithoutReference` | Agent | Goal accuracy without ground truth |

### LLM Evaluation Task Types

`QUESTION_ANSWERING`, `SUMMARIZATION`, `CLASSIFICATION`, and others. Use `--task-type` to set.

## Dashboard & Chart Patterns

### Workflow: Three Steps

1. **Create chart insight** bound to a dataset
2. **Configure the chart** via `set-definition` (dimensions, measures, chart type)
3. **Create dashboard** with tiles referencing the insight

```bash
# Step 1: Create insight with dataset binding
dku insight create "Sales Trend" --type chart --dataset sales_monthly -P PROJ

# Step 2: Configure chart (see dashboard-charts.md for full JSON anatomy)
dku insight set-definition INSIGHT_ID -d @chart.json -P PROJ

# Step 3: Validate column references
dku insight validate INSIGHT_ID -P PROJ

# Step 4: Create dashboard and add tiles
dku dashboard create "Sales Dashboard" -P PROJ
dku dashboard set-definition DASH_ID -d @dashboard.json -P PROJ
```

### Chart Types

| Type | Description |
|------|-------------|
| `lines` | Line chart |
| `multi_columns_lines` | Bar/column chart (multi-series) |
| `stacked_bars` | Stacked bar chart |
| `grouped_columns` | Grouped columns |
| `stacked_area` | Stacked area |
| `pie` | Pie / donut |
| `scatter` | Scatter plot |
| `pivot_table` | Pivot table |

### Key JSON Fields

| Field | Path | Purpose |
|-------|------|---------|
| Dataset binding | `params.datasetSmartName` | Which dataset the chart reads |
| Chart type | `params.def.type` | Chart visualization type |
| X-axis | `params.def.genericDimension0` | Category/time dimensions |
| Color breakdown | `params.def.genericDimension1` | Series grouping |
| Y-axis values | `params.def.genericMeasures` | Aggregated values |
| Tile position | `pages[i].grid.tiles[j].box` | `{top, left, width, height}` on 36-col grid |

### Common Mistakes

| Mistake | Fix |
|---------|-----|
| Tiles at `pages[i].tiles` | Must be `pages[i].grid.tiles` |
| Missing `params.datasetSmartName` | Use `--dataset` on `insight create` |
| Wrong column names (chart renders blank) | Run `dku insight validate ID -P PROJ` |
| Missing `engineType: "LINO"` | Always include in chart params |
| Visual recipe output on wrong connection | CLI prefers `filesystem_managed`. If issues, pre-create output dataset on correct connection first |
| CSV upload → all-string schema → group/window SUM fails | After upload, fix types: `dku dataset set-schema DS -d '{"columns": [{"name":"col","type":"double"},...]}' -P PROJ`. Note: `set-schema` requires `{"columns": [...]}` wrapper — NOT the raw array from `schema -o json`. |
| `agent-block` rejects agent name | These commands require the agent **ID**, not name. Get it with `dku agent list -o json \| jq '.[].id'` |
| SVA blocks in wrong settings path | DSS 14.5+: blocks are in `structuredAgentSettings`, not `toolsUsingAgentSettings`. No `mode` field. `get-graph` returns `structuredAgentSettings` directly. |
| `EMIT_OUTPUT` block gets renamed | On DSS 14.5+, `EMIT_OUTPUT` is silently converted to `GENERATE_OUTPUT`. Use `GENERATE_OUTPUT` to avoid confusion. |
| `knowledge build` fails with "Computable not found" | KB has no data source. Add one with `dku recipe create-embed` first. |
| `agent-tool set-definition` has no effect | Saves to DSS but running instance uses cached params. Re-push plugin to reload: `dku plugin push plugin.zip` |
| `agent-tool types` doesn't show plugin tools | Plugin tools follow naming: `Custom_agent_tool_<plugin-id>_<tool-folder>`. Built-in `types` command now shows this template. |
| Agent tool shows "no dataset selected" | CLI writes to both `datasetRef` and `datasetSmartName` for version compatibility. If still wrong, use `dku agent-tool set-definition` |
| SVA block plugin directory wrong | Version-dependent: DSS 14.5+ → `python-structured-agent-blocks/`, DSS 14.4.x → `python-blocks-graph-blocks/`. Wrong name → 0 components, no error |
| SVA `block.json` uses wrong fields | Use `pyClazzName: "pkg.mod.Class"` (single field). NOT `kind`/`blockHandlerClass`/`blockHandlerModule` (silently ignored) |
| SVA BlockHandler `process()` wrong signature | Use `process_stream(self, trace)` generator yielding `NextBlock()`. NOT `process(self, context, input_data, block_definition)` returning tuple |
| `ColumnNotEmptyRule` compute: "Threshold type cannot be null" | DSS 14.5 beta bug. Use `--type column-min --column COL --min 1` as workaround |
| DQ rule uses `column` (singular) in `--config` JSON | Must be `"columns": ["COL"]` (array). CLI `--column` flag handles this automatically |
| `ColumnValueInRangeRule` type doesn't exist | Use `--type value-in-range` (creates ColumnMin + ColumnMax pair) |
| Min/max/avg/sum rule on STRING column | Returns "Cannot check: STRING is not numeric". Check types: `dku dataset schema DS -P PROJ` |
| `dku dq project-status` returns empty | Default = monitored only. Use `--all`. Enable monitoring via DSS UI (no API) |
| Plugin recipe create fails / unknown type | Use `CustomCode_<pluginId>_<recipeId>` as `--type`. Discover with `dku plugin recipes`. Output dataset must exist first |

**Full JSON reference:** See `skills/dataiku/references/dashboard-charts.md`

## Data Quality Rules

### Workflow: Create + Compute + Check (1 tool call)

```bash
# Create rules, compute, and check results — all one call
dku dq create my_dataset --type record-count --min 1 --name "Has records" -P PROJ && \
dku dq create my_dataset --type column-min --column Price --min 0 --name "Price >= 0" -P PROJ && \
dku dq create my_dataset --type value-in-range --column Latitude --min -90 --max 90 -P PROJ && \
dku dq compute my_dataset -P PROJ && \
dku dq results my_dataset -P PROJ
```

### Rule Type Reference

| Shorthand | DSS Type | What It Checks | `--column`? | Numeric Only? |
|---|---|---|---|---|
| `record-count` | `RecordCountInRangeRule` | Total row count in range | No | N/A |
| `not-empty` | `ColumnNotEmptyRule` | Column has no nulls/blanks | Yes | No — **BUGGY in DSS 14.5 beta** |
| `value-in-range` | Creates 2 rules: `ColumnMinInRangeRule` + `ColumnMaxInRangeRule` | All values in column within bounds | Yes | Yes |
| `column-min` | `ColumnMinInRangeRule` | Minimum value in range | Yes | Yes |
| `column-max` | `ColumnMaxInRangeRule` | Maximum value in range | Yes | Yes |
| `column-avg` | `ColumnAvgInRangeRule` | Average value in range | Yes | Yes |
| `column-sum` | `ColumnSumInRangeRule` | Sum of values in range | Yes | Yes |

For unlisted types (median, stddev, schema, file-size), use `--config` with raw JSON:

```bash
dku dq create my_dataset -c '{"type":"ColumnMedianInRangeRule","columns":["Score"],"softMinimum":50,"softMinimumEnabled":true}' -P PROJ
```

Full catalog of all 13 rule types: `docs/dq-rule-types.md`

### Thresholds

- `--min` / `--max` = warning level (`softMinimum` / `softMaximum`)
- For hard error thresholds (`minimum` / `maximum`), use `--config` with raw JSON
- Each threshold has an `*Enabled` boolean companion (CLI sets automatically)

### Monitoring

- `dku dq project-status -P PROJ` — shows monitored datasets only by default
- `dku dq project-status --all -P PROJ` — includes all datasets with rules
- No public API to enable/disable monitoring — toggle in DSS UI
