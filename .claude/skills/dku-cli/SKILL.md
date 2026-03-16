---
name: dku-cli
description: Use the `dku` CLI to interact with Dataiku DSS from the terminal. Use when the user asks to list/inspect/manage/create/delete DSS projects, datasets, recipes, scenarios, jobs, plugins, code environments, connections, models, folders, LLMs, webapps, macros, users, flow, agents, knowledge banks, bundles, API services, wiki, SQL, or library files — via shell commands. Also use when automating DSS operations in CI/CD pipelines, composing DSS queries with shell pipes, or when `dku` commands are the most efficient way to get information. Prefer this over the Python API skill when the task is a quick query, pipeline script, or shell-composable operation.
---

# dku-cli

`dku` is a kubectl-style CLI for Dataiku DSS. It wraps `dataikuapi` with auth management, output formatting, and composable shell commands. **130 commands** across 26 groups.

> **CRITICAL — Chaining Rule:** Always `&&`-chain related `dku` commands in a **single Bash tool call**. Each separate tool call costs a full agent turn (~$0.05 + 3s). A 10-command workflow should be 1 tool call, not 10. See [Chaining Patterns](#chaining-patterns) for templates.

## When to Use dku vs Python API

| Use `dku` CLI | Use Python API directly |
|---|---|
| Quick queries: list, inspect, status | Complex multi-step workflows |
| CRUD: create, delete, configure resources | DataFrame operations (pandas) |
| Shell scripts / CI/CD pipelines | Custom transformations |
| Piping output to jq/grep/awk | Bulk programmatic operations |
| End-to-end project automation | When CLI doesn't cover the API |

## Setup

```bash
# Install
pip install dku-cli     # or: pipx install dku-cli / uv tool install dku-cli

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

### JSON Input

Creation/mutation commands accept `--definition JSON`:
- Literal JSON string: `--definition '{"key": "value"}'`
- From file: `--definition @config.json`
- From stdin: `--definition -`

Code commands accept `--code` with the same `@file` pattern.

## Quick Reference

For flag details on any command, run `dku <noun> <verb> --help`.

### Command Groups

| Group | Verbs | Needs Project? |
|---|---|---|
| `auth` | login, logout, status, list, switch | No |
| `config` | set, get, list, path, variables, set-variables | No |
| `project` | list, get, export, create, delete, duplicate, variables, set-variables, permissions, set-permissions, tags | No |
| `plugin` | list, push, settings | No |
| `code-env` | list, get, create, delete, update | No |
| `connection` | list, create, test | No (admin) |
| `user` | list, create | No (admin) |
| `sql` | query | No |
| `dataset` | list, schema, head, build, create, upload, delete, clear, get-definition, set-definition, set-schema | Yes |
| `recipe` | list, get, run, create, delete, set-code, get-code, set-definition, add-input, add-output | Yes |
| `scenario` | list, run, abort, status, create, delete, get-definition, set-definition | Yes |
| `job` | list, status, log, abort, wait | Yes |
| `model` | list, get, versions | Yes |
| `folder` | list, ls, upload, download | Yes |
| `llm` | list, completion, embeddings | Yes |
| `webapp` | list, start, stop, status | Yes |
| `macro` | list, run | Yes |
| `flow` | graph, zones, create-zone, propagate, sources, successors | Yes |
| `library` | list, read, write, delete, mkdir | Yes |
| `agent` | list, create, get, delete, wake-up, shutdown, status, add-tool, set-llm | Yes |
| `agent-tool` | list, get, run, delete | Yes |
| `knowledge` | list, create, get, build, search, delete | Yes |
| `bundle` | list, export, download, import, activate | Yes |
| `api-service` | list, create, get, create-package, list-packages | Yes |
| `wiki` | list, create, get | Yes |
| (root) | whoami | No |

### Command Syntax Reference

Individual command syntax — for flag details run `dku <noun> <verb> --help`. **In practice, always chain related commands** (see [Chaining Patterns](#chaining-patterns)).

```bash
# Identity & projects
dku whoami
dku project list -o json | jq '.[].key'
dku project create MY_PROJECT --name "My Project"
dku project get MY_PROJECT
dku project variables -P PROJ
dku project set-variables -P PROJ --set env=production
dku project delete PROJ --confirm

# Datasets
dku dataset list -P PROJ
dku dataset create raw_data --type UploadedFiles -P PROJ
dku dataset upload raw_data data.csv -P PROJ
dku dataset schema ds1 -P PROJ
dku dataset set-schema ds1 -P PROJ --definition '{"columns":[{"name":"id","type":"int"}]}'
dku dataset head ds1 -P PROJ -n 5
dku dataset build ds1 -P PROJ --wait

# Recipes
dku recipe create transform --type python --input raw_data --output clean_data -P PROJ
dku recipe set-code transform -P PROJ --code @transform.py
dku recipe get-code transform -P PROJ
dku recipe run transform -P PROJ --wait

# Scenarios & jobs
dku scenario create daily_build -P PROJ
dku scenario run my_scenario -P PROJ --wait
dku job wait JOB_ID -P PROJ --timeout 300

# GenAI
dku agent create my_agent -P PROJ
dku agent set-llm my_agent --llm-id openai:gpt-4o -P PROJ
dku agent add-tool my_agent --tool tool1 -P PROJ
dku knowledge create my_kb -P PROJ
dku knowledge build my_kb -P PROJ --wait
dku knowledge search my_kb --query "revenue targets" -P PROJ
dku llm completion llm1 "Summarize this" -P PROJ

# Deploy & admin
dku bundle export v1 -P PROJ
dku bundle download v1 -P PROJ --dest ./bundles
dku plugin push my-plugin.zip
dku sql query "SELECT * FROM users LIMIT 10" --connection my_pg
dku library write python/utils/helpers.py -P PROJ --content @helpers.py
```

## Chaining Patterns

**NEVER issue related `dku` commands as separate tool calls.** Chain with `&&` in ONE Bash call. Separate calls = separate agent turns = 2x slower, 2.5x more expensive.

### Data Pipeline (1 tool call)

```bash
# Project + dataset + recipe + upload + build — all one call
dku project create MY_PROJ --name "My Project" && \
dku dataset create raw_data --type UploadedFiles -P MY_PROJ && \
dku dataset upload raw_data data.csv -P MY_PROJ && \
dku dataset set-schema raw_data -P MY_PROJ --definition @schema.json && \
dku recipe create transform --type python --input raw_data --output clean_data -P MY_PROJ && \
dku recipe set-code transform -P MY_PROJ --code @transform.py && \
dku library write python/utils/helpers.py -P MY_PROJ --content @helpers.py && \
dku scenario create daily_build -P MY_PROJ
```

### Agent + Knowledge Bank (1 tool call)

```bash
# Create agent with tools and knowledge — all one call
dku agent create my_agent -P MY_PROJ && \
dku agent set-llm my_agent --llm-id openai:gpt-4o -P MY_PROJ && \
dku knowledge create my_kb -P MY_PROJ && \
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
JOB_ID=$(dku dataset build output -P PROJ 2>/dev/null | grep -oP 'Job ID: \K.*') && \
dku job wait "$JOB_ID" -P PROJ --timeout 300
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

### CSV Upload Workflow

`dku dataset upload` auto-detects format and schema after upload. The correct workflow:

```bash
# Create + upload (format/schema auto-detected)
dku dataset create customers --type UploadedFiles -P PROJ && \
dku dataset upload customers customers.csv -P PROJ
```

If you need to skip auto-detection: `--no-autodetect`.

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

LLM IDs in DSS follow the pattern `provider:model`. Use `dku llm list` to discover available IDs. Common patterns:

```bash
dku llm list -P PROJ -o json | jq -r '.[].id'
# Examples: "openai:gpt-4o-mini", "azure-openai:gpt-4", "anthropic:claude-sonnet-4-20250514"
```

### Python Recipes for Computed Columns

DSS doesn't support computed columns (like `quantity * unit_price`) in visual recipes. Use a Python recipe:

```bash
# Create output dataset first, then recipe, then set code
dku dataset create output_ds --type Filesystem -P PROJ && \
dku recipe create compute_step --type python --input raw_data --output output_ds -P PROJ && \
dku recipe set-code compute_step -P PROJ --code @compute.py
```

### Recipe create requires both --input and --output to exist

Both the input and output datasets must exist before creating a recipe. Create output datasets first:

```bash
dku dataset create input_ds --type UploadedFiles -P PROJ && \
dku dataset create output_ds --type Filesystem -P PROJ && \
dku recipe create transform --type python --input input_ds --output output_ds -P PROJ
```

### Join Recipes — Column Name Prefixing

DSS join recipes prefix column names with the dataset name. If you join `customers` and `orders`, the resulting columns are `customers_name`, `orders_amount`, etc. Plan downstream column references accordingly.

## Running in This Repo

```bash
uv sync              # Install deps
uv run dku           # Run locally
uv run dku --help    # Help
uv run pytest -v     # Run tests (247 tests, all mocked)
```
