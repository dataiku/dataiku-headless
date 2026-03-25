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
> 1. **STOP — DO NOT write Python for joins, aggregations, dedup, sort, filter, stack, or window ops.** Use `create-join`, `create-group`, `create-stack`, `create-distinct`, `create-sort`, `create-filter`, `create-window`, `create-topn`. Python is ONLY for custom logic (scoring, feature engineering, API calls). See [Recipe Decision Tree](#recipe-decision-tree).
> 2. **Visual recipes auto-apply schema.** `create-join`/`create-group`/etc. auto-propagate output schemas. For manual control: `dku recipe apply-schema RECIPE -P PROJ`, or `--auto-update-schema` on build.
> 3. **Upload = UploadedFiles.** `dku dataset create NAME --type UploadedFiles -P PROJ`. Never Filesystem for uploads.
> 4. **Recipe create auto-creates output.** Visual recipe commands auto-create the output dataset. Do NOT pre-create it.
> 5. **Chain everything.** All related commands in ONE `&&`-chained Bash call. Never separate tool calls.

# dku-cli

`dku` is a kubectl-style CLI for Dataiku DSS. It wraps `dataikuapi` with auth management, output formatting, and composable shell commands. **149 commands** across 28 groups.

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
Is the task a join/merge?           → create-join --join-key col  (NEVER pd.merge)
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
| **Join datasets** | `dku recipe create-join NAME -i ds1 -i ds2 --output-ds out -P PROJ` | ~~pd.merge()~~ |
| **Aggregate/group by** | `dku recipe create-group NAME -i ds --output-ds out -k col -P PROJ` | ~~df.groupby()~~ |
| **Stack/union** | `dku recipe create-stack NAME -i ds1 -i ds2 --output-ds out -P PROJ` | ~~pd.concat()~~ |
| **Deduplicate** | `dku recipe create-distinct NAME -i ds --output-ds out -P PROJ` | ~~df.drop_duplicates()~~ |
| **Sort** | `dku recipe create-sort NAME -i ds --output-ds out -P PROJ` | ~~df.sort_values()~~ |
| **Filter rows** | `dku recipe create-filter NAME -i ds --output-ds out -P PROJ` | ~~df[df.x > y]~~ |
| **Window functions** | `dku recipe create-window NAME -i ds --output-ds out -P PROJ` | ~~df.groupby().transform()~~ |
| **Top N** | `dku recipe create-topn NAME -i ds --output-ds out -P PROJ` | ~~df.nlargest()~~ |
| **Split by condition** | `dku recipe create-split NAME -i ds --output-ds out -P PROJ` | ~~manual filtering~~ |
| **Custom logic ONLY** | `dku recipe create NAME -t python -i ds --output-ds out -P PROJ` | Last resort |

Visual recipe commands auto-create the output dataset. Configure details (join keys, aggregation functions, sort order, filter conditions) in the DSS UI or via `dku recipe set-definition`.

#### Join Example (replaces Python merge)

```bash
# Upload two datasets, then join them visually
dku dataset create customers --type UploadedFiles -P PROJ && \
dku dataset upload customers /tmp/customers.csv -P PROJ && \
dku dataset create orders --type UploadedFiles -P PROJ && \
dku dataset upload orders /tmp/orders.csv -P PROJ && \

# Visual join with explicit key (auto-detects if --join-key omitted)
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
dku recipe create compute_risk_score -t python -i customer_features --output-ds risk_scores -P PROJ && \
dku recipe set-code compute_risk_score -P PROJ --code @score.py
```

**Flags for `dku recipe create` (Python/SQL):**
- `--type python` / `-t python` — recipe type
- `--input NAME` / `-i NAME` / `--input-ds NAME` — input dataset (MUST already exist)
- `--output-ds NAME` — output dataset (auto-created for code recipes)
- `-P PROJECT` — project key

**Adding extra inputs** after creation:

```bash
dku recipe add-input RECIPE_NAME DATASET_NAME -P PROJ
```

> **Note on Filesystem datasets:** If you need to manually create a Filesystem dataset (rare — usually recipe create does this), you MUST specify `--connection`: `dku dataset create NAME --type Filesystem -c filesystem_managed -P PROJ`. Without `-c`, it errors. Run `dku connection list` to find available connections.

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
| `plugin` | list, push, settings | No |
| `code-env` | list, get, create, delete, update | No |
| `connection` | list, create, test | No (admin) |
| `user` | list, create | No (admin) |
| `sql` | query | No |
| `dataset` | list, schema, head, build, create, upload, delete, clear, get-definition, set-definition, set-schema | Yes |
| `recipe` | list, get, run, create, delete, set-code, get-code, set-definition, add-input, add-output, check-schema, apply-schema, **create-join, create-group, create-stack, create-distinct, create-sort, create-filter, create-window, create-split, create-topn**, create-embed, create-embed-docs, create-extract, create-llm-eval, create-agent-eval | Yes |
| `scenario` | list, run, abort, status, create, delete, get-definition, set-definition | Yes |
| `job` | list, run, status, log, abort, wait | Yes |
| `model` | list, get, versions | Yes |
| `folder` | list, ls, upload, download | Yes |
| `llm` | list, completion, embeddings | Yes |
| `webapp` | list, start, stop, status, get-definition, set-definition | Yes |
| `dashboard` | list, get, create, delete, get-definition, set-definition | Yes |
| `insight` | list, get, create, delete, get-definition, set-definition | Yes |
| `macro` | list, run | Yes |
| `flow` | graph, zones, create-zone, propagate, check, sources, successors | Yes |
| `library` | list, read, write, delete, mkdir | Yes |
| `agent` | list, create, get, delete, wake-up, shutdown, status, add-tool, set-llm | Yes |
| `agent-tool` | list, get, run, delete | Yes |
| `knowledge` | list, create, get, build, search, delete | Yes |
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

### Deploy (1 tool call)

```bash
# Export + download bundle — all one call
dku bundle export v1 -P MY_PROJ && \
dku bundle download v1 -P MY_PROJ --dest ./bundles
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

Agents require `--type`. Default is `TOOLS_USING_AGENT` (visual agent with tools).

```bash
# Create agent with LLM and tools — all one call
dku agent create my_agent --type TOOLS_USING_AGENT -P PROJ && \
dku agent set-llm my_agent --llm-id "openai:gpt-4o-mini" -P PROJ && \
dku agent add-tool my_agent --tool my_tool -P PROJ
```

Valid types: `TOOLS_USING_AGENT`, `PYTHON_AGENT`, `PLUGIN_AGENT`, `STRUCTURED_AGENT`.

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

### Join Recipes — Column Name Prefixing

DSS join recipes prefix column names with the dataset name. If you join `customers` and `orders`, the resulting columns are `customers_name`, `orders_amount`, etc. Plan downstream column references accordingly.

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
dku recipe create clean_step --type python --input raw_data --output-ds cleaned -P PROJ && \
dku recipe set-code clean_step -P PROJ --code @clean.py && \

# Recipe 2: cleaned -> final (output auto-created)
dku recipe create agg_step --type python --input cleaned --output-ds final -P PROJ && \
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
dku recipe create compute_scored --type python --input summary --output-ds scored -P MY_PROJ && \
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
