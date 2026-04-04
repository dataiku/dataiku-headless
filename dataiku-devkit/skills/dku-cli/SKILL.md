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
> 2. **Use `dku ml` for ML — not Python.** `dku ml create-prediction` + `dku ml train` + `dku ml deploy` covers prediction, clustering, timeseries, and causal. Python ONLY for custom model architectures.
> 3. **Visual recipes auto-apply schema.** `create-join`/`create-group`/etc. auto-propagate output schemas. For manual control: `dku recipe apply-schema RECIPE -P PROJ`, or `--auto-update-schema` on build.
> 4. **Upload = UploadedFiles.** `dku dataset create NAME --type UploadedFiles -P PROJ`. Never Filesystem for uploads.
> 5. **Recipe create auto-creates output.** Visual recipe commands auto-create the output dataset. Do NOT pre-create it.
> 6. **Investigate with `inspect`.** `dku project inspect PROJ -o json` returns datasets, recipes, scenarios, flow, jobs, wiki, variables in ONE call. Start every investigation here.
> 7. **Chain everything.** All related commands in ONE `&&`-chained Bash call. Never separate tool calls.
> 8. **Charts need `--dataset`.** `dku insight create NAME --type chart --dataset DS -P PROJ`. Validate with `dku insight validate ID -P PROJ`.
> 9. **Verify everything.** After building, ALWAYS `dku dataset head OUTPUT -P PROJ` to confirm real data exists. Exit code 0 ≠ correct output. Also use the `dataiku` skill for platform knowledge — these two skills are a pair.
> 10. **Prefer purpose-built prepare processors over GREL.** Need to rename? `add-rename`. Parse dates? `add-step --type DateParser`. Uppercase? `add-step --type StringTransformer`. If/then/else? `add-step --type VisualIfRule`. Use `add-formula` (GREL) ONLY when no dedicated processor exists. **READ `dataiku` skill's `references/prepare-processors.md` before writing any `add-step` command** — it has the exact params and JSON for each processor.
> 11. **Sample data before transforming.** Before writing prepare steps, creating joins, or configuring group-by: run `dku dataset head INPUT -P PROJ -n 5` and `dku dataset schema INPUT -P PROJ` to inspect actual column names, values, and formats. Don't guess date formats, value ranges, or column names — verify first. For joins, check both datasets have the join key.
> 12. **Document what you build.** After creating a project, set its description (`dku project set-metadata PROJ --description "..."`). After creating datasets, describe columns (`dku dataset set-column-description DS col1 "desc" -P PROJ`). Create at least one wiki article ("Project Overview"). Use `set-metadata` on any object. Undocumented projects are incomplete projects.
> 13. **One multi-input join > cascading joins.** Joining A+B, then result+C, then result+D = 3 recipes, 3 intermediate datasets, 3x build time. Instead: one `create-join -i A -i B -i C -i D` with index-prefixed keys. See [Visual Recipe Design Patterns](#visual-recipe-design-patterns).

# dku-cli

`dku` is a kubectl-style CLI for Dataiku DSS. It wraps `dataikuapi` with auth management, output formatting, and composable shell commands. **~300 commands** across 42 groups.

## Companion Skill: `dataiku`

**This skill and `dataiku` are a pair. Always use both.**

- **This skill** tells you *how to execute* — CLI commands, flags, chaining, build patterns
- **`dataiku`** tells you *what* to build and *how DSS works* — which recipe type, which agent architecture, plugin patterns, formula syntax

**Before writing any CLI commands**, consult the `dataiku` skill to confirm you're using the right DSS approach. The CLI can create a Python recipe in seconds — but if a visual recipe exists for that task, you've chosen wrong. The `dataiku` skill's recipe decision tree and agent type selection guide prevent these mistakes.

## Verification Protocol — Build It, Run It, Prove It

**Your job is not done when commands exit 0. Your job is done when you've verified the output is correct.**

DSS commands frequently succeed silently while producing empty datasets, broken schemas, or misconfigured recipes. You MUST verify every outcome.

### After Every Pipeline Build

```bash
# 1. Build the full pipeline (always recursive + auto-schema)
dku job run --target FINAL_OUTPUT -P PROJ \
  --type RECURSIVE_BUILD \
  --auto-update-schema \
  --wait && \

# 2. VERIFY — check the final output has real data
dku dataset head FINAL_OUTPUT -P PROJ -n 5 && \

# 3. VERIFY — check row count is reasonable
dku dataset head FINAL_OUTPUT -P PROJ -o json | jq 'length'
```

### After Creating Agents

```bash
# Verify agent is alive and has tools attached
dku agent status AGENT_NAME -P PROJ && \
dku agent-tool list -P PROJ -o json | jq '[.[] | select(.agentId == "AGENT_ID")]'
```

### After Creating Knowledge Banks

```bash
# Build and then test search actually returns results
dku knowledge build KB_NAME -P PROJ --wait && \
dku knowledge search KB_NAME --query "test query" -P PROJ
```

### After Configuring Semantic Models

```bash
# Create, configure, index, and verify
dku semantic-model create "Sales Model" -P PROJ && \
dku semantic-model get-version SM_ID -P PROJ -o json  # verify entities exist
dku semantic-model update-index SM_ID --wait -P PROJ   # index distinct values
```

### After Configuring Agent Hub

```bash
# List enterprise agents and verify LLM is set
dku agent-hub list-agents -P PROJ && \
dku agent-hub config -P PROJ -o json | jq '.default_llm_id'
```

### Verification Rules

1. **Always `head` the final output dataset.** This is the #1 verification — if output looks right, the pipeline works.
2. **Never assume success from exit code alone.** A recipe can "build successfully" but produce 0 rows.
3. **Check intermediate datasets when debugging.** If the final output is wrong, `head` each intermediate dataset to find where it breaks.
4. **Validate chart insights.** `dku insight validate ID -P PROJ` catches column name mismatches that render blank charts.
5. **Test agents end-to-end.** Creating agent + tools is not enough — verify the agent can actually call its tools.

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

#### Pre-Recipe Checklist

Before creating any recipe, verify your assumptions:

```bash
# Check columns exist and see actual value formats
dku dataset head input_ds -P PROJ -n 5

# Check schema for column names and types
dku dataset schema input_ds -P PROJ

# For joins — verify both datasets have the join key
dku dataset schema ds1 -P PROJ && dku dataset schema ds2 -P PROJ
```

Don't guess date formats (`yyyy-MM-dd` vs `MM/dd/yyyy`), column names, or value patterns. A 5-row sample catches most assumption errors before they become broken recipes.

#### Recipe Decision Tree

**Follow this exactly. Do NOT skip to Python.**

```
Is the task a join/merge?           → create-join --join-key col  (NEVER pd.merge)
Is the task aggregation/groupby?    → create-group -k col1 -k col2 --agg col:sum,avg  (NEVER df.groupby)
Is the task stacking/union/concat?  → create-stack  (NEVER pd.concat)
Is the task dedup/distinct?         → create-distinct  (NEVER df.drop_duplicates)
Is the task sorting?                → create-sort  (NEVER df.sort_values)
Is the task filtering rows?         → create-filter  (NEVER df[condition])
Is the task window/rank function?   → create-window --compute 'rowNumber::rn'  (NEVER df.groupby().transform)
Is the task top/bottom N?           → create-topn --n 10 --rank-by col:desc  (NEVER df.nlargest)
Is the task top N per group?        → create-topn --n 1 --rank-by col:desc -k group_col  (NEVER groupby().first)
Is the task wide-to-long (unpivot)? → Prepare recipe + add-fold  (if UnavailableTypeException → Python pd.melt)
Is the task long-to-wide (pivot)?   → create-pivot --agg-type SUM  (NEVER df.pivot_table)
Is the task random sampling?        → create-sampling  (NEVER df.sample)
Is the task row expansion?          → create-join --join-type CROSS  (NEVER nested loops)
Is the task a passthrough/copy?     → create -t sync  (NEVER Python passthrough)
None of the above?                  → THEN use Python: create NAME -t python
```

**Python IS correct for:** custom scoring, feature engineering, API calls, ML inference, regex parsing, multi-step logic that can't be expressed as chained visual recipes.

#### Visual Recipe Selection Guide

| Task | Command | NOT this |
|------|---------|----------|
| **Join datasets** | `dku recipe create-join NAME -i ds1 -i ds2 --output-ds out -P PROJ` | ~~pd.merge()~~ |
| **Aggregate/group by** | `dku recipe create-group NAME -i ds --output-ds out -k col1 -k col2 --agg 'amount:sum,avg' -P PROJ` | ~~df.groupby()~~ |
| **Stack/union** | `dku recipe create-stack NAME -i ds1 -i ds2 --output-ds out -P PROJ` | ~~pd.concat()~~ |
| **Deduplicate** | `dku recipe create-distinct NAME -i ds --output-ds out -P PROJ` | ~~df.drop_duplicates()~~ |
| **Sort** | `dku recipe create-sort NAME -i ds --output-ds out -P PROJ` | ~~df.sort_values()~~ |
| **Filter rows** | `dku recipe create-filter NAME -i ds --output-ds out -P PROJ` | ~~df[df.x > y]~~ |
| **Window functions** | `dku recipe create-window NAME -i ds --output-ds out -k grp --order-key date --compute 'rowNumber::rn' -P PROJ` | ~~df.groupby().transform()~~ |
| **Top N** | `dku recipe create-topn NAME -i ds --output-ds out --n 10 --rank-by col:desc -P PROJ` | ~~df.nlargest()~~ |
| **Top N per group** | `dku recipe create-topn NAME -i ds --output-ds out --n 1 --rank-by date:desc -k stock -P PROJ` | ~~groupby().first()~~ |
| **Split by condition** | `dku recipe create-split NAME -i ds --output-ds out -P PROJ` | ~~manual filtering~~ |
| **Pivot (long→wide)** | `dku recipe create-pivot NAME -i ds --output-ds out --row-key id --column-key month --value-column val --agg-type SUM -P PROJ` | ~~df.pivot_table()~~ |
| **Unpivot (wide→long)** | `dku recipe add-fold PREP --columns "jan,feb,mar" --key-column month --value-column val -P PROJ` | ~~pd.melt()~~ |
| **Random sample** | `dku recipe create-sampling NAME -i ds --output-ds out --size 1000 -P PROJ` | ~~df.sample()~~ |
| **Cross join (cartesian)** | `dku recipe create-join NAME -i A -i B --output-ds out --join-type CROSS -P PROJ` | ~~itertools.product()~~ |
| **Custom logic ONLY** | `dku recipe create NAME -t python -i ds --output-ds out -P PROJ` | Last resort |

Visual recipe commands auto-create the output dataset. Configure details (join keys, aggregation functions, sort order, filter conditions) via CLI flags or `dku recipe set-definition --payload` for advanced config.

For advanced configuration beyond CLI flags (custom join conditions, additional aggregations, post-filters), use `dku recipe get-settings RECIPE -P PROJ -o json` to read the current payload, then `dku recipe set-definition RECIPE --payload '...' -P PROJ` to update. **READ `dataiku` skill's `references/visual-recipe-payloads.md` for payload schemas and `references/visual-conditions.md` for filter/condition JSON.**

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

#### First/Last Row Per Group (common pattern — NEVER use Python for this)

Use **TopN per group** to get the first or last row per group:

```bash
# First row per group (e.g., earliest transaction per stock)
dku recipe create-topn first_per_stock \
  -i transactions \
  --output-ds first_transactions \
  --n 1 \
  --rank-by date \
  -k stock \
  -P PROJ

# Last row per group (latest transaction per stock)
dku recipe create-topn last_per_stock \
  -i transactions \
  --output-ds last_transactions \
  --n 1 \
  --rank-by date:desc \
  -k stock \
  -P PROJ
```

Alternative with Window + Filter (when you need row_number for other purposes):

```bash
# Add row number partitioned by stock, ordered by date
dku recipe create-window add_rank -i data --output-ds ranked \
  -k stock --order-key date --compute 'rowNumber::rn' -P PROJ && \
# Filter to keep only first row per group
dku recipe create-filter keep_first -i ranked --output-ds first_per_group -P PROJ
# Configure filter condition (rn == 1) via DSS UI or:
# dku recipe set-definition keep_first --payload '{"filterConditions": ...}' -P PROJ
```

#### Common Recipe Mistakes

| Mistake | Fix |
|---------|-----|
| Cascading joins (A+B → temp, temp+C → out) | One `create-join -i A -i B -i C` with index-prefixed keys |
| Default INNER join when enriching | Use `--join-type LEFT` to keep all source rows |
| Python `groupby([col1, col2])` | Repeat `-k`: `-k col1 -k col2` on `create-group` |
| Python `nlargest(N)` or `sort + head` | Use `create-topn --n N --rank-by col:desc` |
| Python `groupby().first()` / `last()` | Use `create-topn --n 1 --rank-by col:desc -k group_col` |
| Python `groupby().transform(rank)` | Use `create-window --compute 'rowNumber::rn'` |
| Python `pivot_table(aggfunc='sum')` | Use `create-pivot --agg-type SUM` |
| `set-definition` doesn't change visual config | Use `--payload` (not `--definition`) for visual recipe config (aggregations, computations, etc.) |
| TopN recipe has no ordering | Use `--rank-by col:desc` and `--n N` flags |
| `set-definition` orphans auto-created output (plugin recipes) | Pre-create output datasets before `recipe create` when using plugin recipes with named roles |
| Plugin recipe SELECT values wrong case | `selectChoices` values are case-sensitive (`"none"` not `"None"`, `"json"` not `"JSON"`). Check `dku plugin recipes PLUGIN -o json` for exact values |
| `dku dataset build` fails for folder outputs | Managed folder outputs are NOT buildable via `dataset build`. Use `dku recipe run RECIPE -P PROJ --wait` instead |
| Prepare recipe `create` fails with "Output dataset does not exist" | Unlike `create-join`/`create-group`, `create --type prepare` does NOT auto-create the output. Pre-create it: `dku dataset create NAME --type Filesystem -c filesystem_managed -P PROJ` |
| `add-fold` or `add-filter-rows --formula` fails with `UnavailableTypeException` | `FoldColumnsByName` and `FilterOnFormula` are plugin processors unavailable on some DSS instances. For fold: use Python `pd.melt()`. For filter: use `add-step --type FilterOnCustomFormula --params '{"expression":"...","action":"REMOVE_ROW"}'` |
| GREL formula returns null for columns with spaces | Column names with spaces (e.g. `Return Reason`) can't be referenced via GREL variables (`Return_Reason` returns null). Use a Python recipe, or rename the column first with `add-rename` |

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

#### Plugin Source Recipes (No Input)

Some plugin recipes (e.g. `generate-rows`) are source recipes with no input role. Omit `-i` — the CLI skips input wiring:

```bash
dku recipe create gen_data -t CustomCode_my-plugin_generate-rows \
  --output-ds generated -P PROJ
```

#### Plugin Recipes with Named Roles

When using `set-definition` with plugin recipes that have named roles (not `main`), **pre-create the output dataset** before `recipe create`. The `--output-ds` auto-create wires to `main` role; `set-definition` rewires to plugin role names, orphaning the dataset:

```bash
# RIGHT — pre-create, then wire to named role
dku dataset create output_ds --type Filesystem -c filesystem_managed -P PROJ && \
dku recipe create my_step -t CustomCode_plugin_recipe -i input --output-ds output_ds --output-role output_role_name -P PROJ
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
| `project` | list, get, **inspect**, export, create, delete, duplicate, set-metadata, variables, set-variables, permissions, set-permissions, tags | No |
| `plugin` | list, get, push, delete, settings, create-code-env, set-code-env, update-code-env, usages, **recipes, list-files, get-file, put-file** | No |
| `code-env` | list, get, create, delete, update | No |
| `connection` | list, **get**, create, **delete**, test | No (admin) |
| `user` | list, **get**, create, **delete** | No (admin) |
| `sql` | query | No |
| `dataset` | list, schema, head, build, create, upload, delete, clear, get-definition, set-definition, set-schema, **set-metadata, set-column-description, ai-describe, rename, copy, partitions** | Yes |
| `recipe` | list, get, **get-definition**, run, create, delete, set-code, get-code, set-definition, **get-settings, set-settings**, add-input, add-output, check-schema, apply-schema, **create-join, create-group, create-stack, create-distinct, create-sort, create-filter, create-window, create-split, create-topn, create-pivot, create-sampling**, create-embed, create-embed-docs, create-extract, create-llm-eval, create-agent-eval, **list-steps, add-step, get-step, remove-step, disable-step, enable-step, add-formula, add-rename, add-filter-rows, add-fill-empty, add-delete-columns, add-find-replace, add-fold, add-geopoint, add-geodistance** | Yes |
| `scenario` | list, run, abort, status, create, delete, get-definition, set-definition, **last-run, runs, set-metadata, list-triggers, add-trigger, add-trigger-dataset, remove-trigger** | Yes |
| `job` | list, run, status, log, abort, wait | Yes |
| `model` | list, get, versions, set-active-version, metrics, delete-version, delete, usages, **set-metadata** | Yes |
| `folder` | list, ls, upload, download, create, delete, delete-file, get, create-dataset, **set-metadata** | Yes |
| `llm` | list, completion, embeddings | Yes |
| `webapp` | list, start, stop, status, get-definition, set-definition | Yes |
| `dashboard` | list, get, create, delete, get-definition, set-definition, **set-metadata** | Yes |
| `insight` | list, get, create, delete, validate, get-definition, set-definition, **set-metadata** | Yes |
| `macro` | list, run | Yes |
| `flow` | graph, **visualize**, zones, create-zone, **set-zone**, **move**, propagate, check, sources, successors | Yes |
| `library` | list, read, write, delete, mkdir | Yes |
| `agent` | list, create, get, delete, wake-up, shutdown, status, add-tool, set-llm, set-prompt, test, **set-metadata** | Yes |
| `agent-review` | list, create, get, delete, set-agent, set-llm, add-trait, list-tests, create-test, import-tests, export-tests, run, list-runs, results | Yes |
| `agent-tool` | list, get, **create** (--dataset, --llm, --kb), set-definition, run, types, delete | Yes (except `types`) |
| `code-studio` | list, create, get, delete, status, start, stop, change-owner, templates | Yes (except `templates`) |
| `git` | status, log, diff, commit, pull, push, fetch, branches, create-branch, delete-branch, switch, tags, create-tag, remote | Yes |
| `api-deployer` | list-infras, list-services, get-service, list-deployments, create-deployment, get-deployment, update-deployment, delete-deployment, deployment-status | No |
| `project-deployer` | list-infras, list-projects, list-deployments, create-deployment, get-deployment, update-deployment, delete-deployment, deployment-status | No |
| `notebook` | list, get, create, delete, sessions, stop, clear-outputs, history | Yes |
| `discussion` | list, get, create, reply | Yes |
| `knowledge` | list, create, get, set-definition, build, search, delete | Yes (accepts name or ID) |
| `semantic-model` | list, create, get, delete, versions, get-version, create-version, set-version, set-active-version, distinct-values, update-index | Yes (accepts name or ID) |
| `agent-hub` | list, config, set-config, list-agents, add-agent, remove-agent, set-agent, set-llm, start, stop | Yes (auto-detects hub) |
| `bundle` | list, export, download, import, activate | Yes |
| `api-service` | list, create, get, create-package, list-packages | Yes |
| `wiki` | list, create, get, update, delete | Yes |
| (root) | whoami | No |

For full command syntax with examples, see `references/commands.md`. For flag details, run `dku <noun> <verb> --help`.

Key notes:
- `dku llm list` defaults to `GENERIC_COMPLETION`. Pass `--purpose TEXT_EMBEDDING_EXTRACTION` for embedding models.
- `dku llm embeddings` rejects completion-only model IDs — list embedding models first.
- Prefer `dku ... -o json | jq ...` on success paths. Avoid `2>&1 | jq` — stderr has error payloads, not success objects.
- `dku semantic-model` — Semantic models enable text-to-SQL via the Semantic Model Query agent tool (DSS 14.4+). Versions are key: only the active version is used by agents. Always `update-index --wait` after changing entities/attributes.
- `dku agent-hub` — **Cannot create** Agent Hub via CLI (it's a plugin webapp — create in DSS UI first). `--hub` auto-detects when one hub exists; required when multiple exist. Config is shallow-merged, not replaced. Agent IDs use `PROJECT:agent:ID` format.
- `dku scenario list-triggers` / `add-trigger-dataset` — manage scenario automation triggers from CLI. Use `add-trigger-dataset` for dataset-change triggers, `add-trigger` for arbitrary trigger JSON.

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
2. `dku ml algorithms AID TID -P PROJ` — see available/enabled algorithms
3. `dku ml set-algorithm AID TID --disable-all --enable XGBoost --enable RandomForest -P PROJ` — tune algorithms
4. `dku ml train AID TID -P PROJ` — train and get model IDs
5. `dku ml details AID TID MODEL_ID -P PROJ` — check metrics
6. `dku ml deploy AID TID MODEL_ID --name MyModel --train-dataset DS -P PROJ` — deploy to flow
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

### Investigation Workflow (1-2 tool calls)

**When asked to explore, debug, or understand an existing project:**

```bash
# Tool call 1 — Full project overview (replaces 7+ separate commands)
dku project inspect MY_PROJ -o json
```

Parse the JSON output to understand the project structure. Then drill into specifics:

```bash
# Tool call 2 — Drill into details as needed
dku dataset head specific_ds -P MY_PROJ -n 5 && \
dku recipe get-settings suspect_recipe -P MY_PROJ && \
dku job status last_job_id -P MY_PROJ -o json && \
# When a build fails, inspect the full job log:
dku job log JOB_ID -P MY_PROJ
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

# List triggers on a scenario
dku scenario list-triggers BUILD_ALL -P PROJ

# Add dataset change trigger (fires when dataset is modified)
dku scenario add-trigger-dataset BUILD_ALL --dataset raw_data -P PROJ

# Add dataset change trigger with custom intervals
dku scenario add-trigger-dataset BUILD_ALL --dataset raw_data --delay 600 --grace-delay 60 -P PROJ

# Add time-based trigger via JSON
dku scenario add-trigger BUILD_ALL --trigger '{"active":true,"type":"temporal","params":{"frequency":"Daily","hour":2,"minute":0,"repeatFrequency":1,"timezone":"SERVER"}}' -P PROJ

# Remove a trigger by index
dku scenario remove-trigger BUILD_ALL --index 0 -P PROJ

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

### Structured Visual Agent (SVA) Graph — Canonical Workflow

**Use `set-graph` as the primary pattern.** The `dku agent-block connect` command does not support `PYTHON_CODE` blocks (exits with an error — use `validNextBlocksFromCode` + `NextBlock()` yield instead). For `STANDARD_REACT`, `connect` works correctly (sets `defaultNextBlock` automatically). For any non-trivial graph, always use `get-graph → patch JSON → set-graph`:

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

**`connect` is a convenience shortcut only.** Use it for simple `LLM_REQUEST → ROUTING`, `STANDARD_REACT → EMIT_OUTPUT`, or other direct wiring. For `PYTHON_CODE` blocks, `connect` will error — use `set-graph` with `validNextBlocksFromCode` and `NextBlock()` yield in `process()`.

### Agent Tool Creation (Two-Step Workflow)

Creating an agent tool requires two steps — `agent-tool create` creates the tool instance, then `agent add-tool` attaches it to an agent.

**Built-in tool types** (3 types — use `dku agent-tool types` to list):

```bash
# DatasetRowLookup — query rows by column values
dku agent-tool create row_lookup --type DatasetRowLookup --dataset customers -P PROJ && \
dku agent add-tool AGENT_ID --tool TOOL_ID -P PROJ

# VectorStoreSearch — search a knowledge bank (--kb required)
dku agent-tool create kb_search --type VectorStoreSearch --kb my_kb -P PROJ && \
dku agent add-tool AGENT_ID --tool TOOL_ID -P PROJ

# LLMMeshLLMQuery — call another LLM or agent
dku agent-tool create sub_llm --type LLMMeshLLMQuery --llm openai:conn:gpt-4o -P PROJ && \
dku agent add-tool AGENT_ID --tool TOOL_ID -P PROJ
```

**Plugin-based tools** (custom Python tools):

```bash
# Plugin tools use Custom_agent_tool_<plugin>_<tool> type format
dku agent-tool create "Web Search" \
  --type Custom_agent_tool_google-search-tool_google-search-tool \
  -P PROJ
```

> **There is no built-in PythonFunction type.** Custom Python tools MUST be built as plugins (`python-agent-tools/` folder) and deployed via `dku plugin push`. See `references/llm-tools.md` for the full plugin tool development guide.

**Discovering available tool types:**
```bash
# List built-in types (does NOT accept -P — project-independent)
dku agent-tool types
```

**Updating tool definitions post-creation:**
```bash
# Merge params (shallow merge on top-level keys)
dku agent-tool set-definition TOOL_ID -d '{"params": {"maxRecords": 10}}' -P PROJ

# From a file
dku agent-tool set-definition TOOL_ID -d @tool-config.json -P PROJ
```

> **Tip:** To discover the exact params structure for any tool type, create one in the DSS UI first, then run `dku agent-tool get TOOL_ID -P PROJ -o json` to inspect its full settings.

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

> **Positional project key:** `dku project variables PROJ`, `dku project permissions PROJ`, and `dku project tags PROJ` accept the project key as a positional argument (in addition to `-P PROJ`).

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
| Build recipe that outputs to a managed folder | `dku recipe run RECIPE -P PROJ --wait` (folders are NOT buildable via `dku dataset build`) |
| Inspect a failed build log | `dku job log JOB_ID -P PROJ` |

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

## Visual Recipe Design Patterns

### Recipe Type Semantics — When to Use What

Choosing the wrong recipe type wastes tokens debugging. Use this matrix:

| Recipe | Inputs | Semantics | Use when... | NOT for... |
|--------|--------|-----------|-------------|------------|
| **Join** | 2-5 datasets | Combine rows by matching key | Enriching a dataset with lookups | Appending rows (use Stack) |
| **Stack** | 2+ datasets | Append rows (UNION ALL) | Datasets share same schema, different rows | Key-based matching (use Join) |
| **Group** | 1 dataset | Reduce rows by aggregation | SUM/AVG/COUNT/MIN/MAX per group | Per-row transforms (use Window or Prepare) |
| **Window** | 1 dataset | Per-row compute within partitions | Running totals, rank, lag/lead, cumulative | Reducing row count (use Group) |
| **TopN** | 1 dataset | Keep N rows per group | First/last per group, top performers | Global top N without groups (use Sort + head) |
| **Filter** | 1 dataset | Keep/remove rows by condition | Simple boolean conditions on column values | Complex multi-step logic (use Prepare) |
| **Distinct** | 1 dataset | Deduplicate rows | Exact duplicate removal | Keep-first/last logic (use TopN with -k) |
| **Sort** | 1 dataset | Order rows | Explicit ordering for output | Ordering within groups (use Window) |
| **Split** | 1 dataset → 2+ | Route rows to different outputs | Different downstream paths per condition | Single-output filtering (use Filter) |
| **Pivot** | 1 dataset | Long→wide (columns from values) | Timeseries to columns, category expansion | Wide→long (use Prepare add-fold) |
| **Sampling** | 1 dataset | Reduce dataset size | Dev/test subsets, stratified samples | Filtering by condition (use Filter) |
| **Prepare** | 1 dataset | Row-level transforms, cleaning | Rename, parse dates, GREL formulas, fold | Aggregation (use Group), joins (use Join) |

### Join Design: Multi-Input > Cascading

**Anti-pattern: Cascading joins** — joining A+B → temp1, then temp1+C → temp2, then temp2+D → output. This creates:
- 3 recipes instead of 1
- 2 unnecessary intermediate datasets
- 3x schema propagation
- Column name explosion (prefixed at every step: `temp1_customers_name`)
- 3x build time

**Correct: One multi-input join** — join A+B+C+D in a single recipe:

```
# BAD — cascading joins (3 recipes, 2 intermediate datasets)
dku recipe create-join join_ab -i A -i B --output-ds temp1 --join-key id -P PROJ && \
dku recipe create-join join_abc -i temp1 -i C --output-ds temp2 --join-key id -P PROJ && \
dku recipe create-join join_abcd -i temp2 -i D --output-ds final --join-key id -P PROJ

# GOOD — one multi-input join (1 recipe, 0 intermediate datasets)
dku recipe create-join enrich_all \
  -i A -i B -i C -i D \
  --output-ds final \
  --join-key id \
  --join-key 1:id \
  --join-key 2:id \
  -P PROJ
```

**When cascading IS acceptable:** Different join types per step (e.g., LEFT join for A+B, then INNER join for result+C), or when intermediate datasets are reused by other recipes.

### Join Types

| Type | Flag | Keeps | Use when... |
|------|------|-------|-------------|
| **LEFT** | `--join-type LEFT` | All left rows, matched right | Enriching — keep all source rows even without match |
| **INNER** | `--join-type INNER` (default) | Only matched rows | Both sides must have the key |
| **RIGHT** | `--join-type RIGHT` | All right rows, matched left | Rare — usually restructure as LEFT |
| **FULL** | `--join-type FULL` | All rows from both sides | Reconciliation, finding mismatches |
| **CROSS** | `--join-type CROSS` | Cartesian product (every combo) | Row expansion (records × months) |

**Default is INNER.** If your task says "enrich" or "look up", you almost always want **LEFT** — keeps all source rows even when the lookup table has no match.

### Window Functions — Quick Guide

Window recipes compute per-row values within partitions without reducing row count.

| Compute | Syntax (`--compute`) | Use case |
|---------|---------------------|----------|
| Row number | `'rowNumber::rn'` | Sequential numbering within group |
| Rank (gaps) | `'rank::rnk'` | 1,2,2,4 ranking |
| Dense rank | `'denseRank::drnk'` | 1,2,2,3 ranking (no gaps) |
| Lag | `'lag:col:1::prev_val'` | Previous row's value |
| Lead | `'lead:col:1::next_val'` | Next row's value |
| Running sum | `'sum:amount::running_total'` | Cumulative totals |
| Running count | `'count:::running_count'` | Cumulative counts |
| Running avg | `'avg:amount::running_avg'` | Moving averages |

**Pattern — first/last per group:** `create-topn --n 1 --rank-by date:desc -k group_col` is simpler than Window + Filter. Use Window only when you need the rank column for other purposes.

### Common Pipeline Anti-Patterns

| Anti-pattern | Why it's wrong | Do this instead |
|--------------|---------------|-----------------|
| Cascading joins (A+B → temp → temp+C) | Extra recipes, intermediate datasets, column prefix explosion | One multi-input join with index-prefixed keys |
| Python `groupby` when Group recipe works | Slower, harder to maintain, no visual lineage | `create-group -k col --agg "col:sum,avg"` |
| Filter + Sort + head for top N | 3 recipes for what TopN does in 1 | `create-topn --n N --rank-by col:desc` |
| Window recipe just for first-per-group | Overkill — need Window + Filter (2 recipes) | `create-topn --n 1 -k group_col` |
| Python for column rename/type cast | Breaks visual lineage | Prepare recipe: `add-rename`, `add-step --type TypeSetter` |
| Separate Filter recipes per condition | Bloated flow, redundant scans | One Split recipe with multiple conditions |
| `pd.concat()` for stacking datasets | No visual lineage, handles schema drift poorly | `create-stack -i ds1 -i ds2` |

## Agent Evaluation Workflow (1–2 tool calls)

Use `agent-review` to evaluate agent quality with LLM-as-judge traits:

```bash
# Create review, configure, add tests, run evaluation (1 tool call)
dku agent-review create "Quality Check" -P PROJ && \
REVIEW_ID=$(dku agent-review list -P PROJ -o json | jq -r '.[0].id') && \
dku agent-review set-agent "$REVIEW_ID" --agent MY_AGENT -P PROJ && \
dku agent-review set-llm "$REVIEW_ID" --llm "openai:...:gpt-4o" -P PROJ && \
dku agent-review add-trait "$REVIEW_ID" --name "Accuracy" --criteria "Does the answer match the reference answer?" -P PROJ && \
dku agent-review add-trait "$REVIEW_ID" --name "Helpfulness" --criteria "Is the response helpful and actionable?" -P PROJ && \
dku agent-review create-test "$REVIEW_ID" -q "What is our refund policy?" -r "30-day money back guarantee" -P PROJ && \
dku agent-review run "$REVIEW_ID" -P PROJ
```

```bash
# Check results (tool call 2)
RUN_ID=$(dku agent-review list-runs "$REVIEW_ID" -P PROJ -o json | jq -r '.[0].id') && \
dku agent-review results "$REVIEW_ID" --run "$RUN_ID" -P PROJ -o json
```

For bulk testing, import from a dataset:
```bash
dku agent-review import-tests "$REVIEW_ID" --dataset test_cases --query-column question --reference-column answer -P PROJ
```

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

# Scenario with dataset change trigger
dku scenario create daily_build --if-not-exists -P MY_PROJ && \
dku scenario add-trigger-dataset daily_build --dataset raw_data -P MY_PROJ && \

# Wiki (--if-not-exists = safe to re-run)
dku wiki create "Project Overview" --body "# My Project\nAutomated data pipeline." --if-not-exists -P MY_PROJ && \

# Document the project (descriptions, column docs)
dku project set-metadata MY_PROJ --description "Automated data pipeline — enriches raw data, computes summary statistics, scores items." && \
dku dataset set-column-description raw_data id "Unique record ID" name "Item name" amount "Transaction amount in USD" -P MY_PROJ && \
dku scenario set-metadata daily_build --description "Nightly rebuild of the full pipeline" -P MY_PROJ
```

**Tool call 2 — Build the pipeline:**

```bash
dku job run --target scored -P MY_PROJ \
  --type RECURSIVE_BUILD \
  --auto-update-schema \
  --wait
```

**Tool call 3 — Verify (MANDATORY — never skip this):**

```bash
# Check final output has real data (not empty)
dku dataset head scored -P MY_PROJ -n 5 && \
# Check pipeline topology is correct
dku flow graph -P MY_PROJ -o json | jq '.nodes | keys' && \
# Check row count is reasonable
dku dataset head scored -P MY_PROJ -o json | jq 'length'
```

> **You are NOT done until Tool call 3 passes.** If `head` returns 0 rows or wrong columns, debug before reporting success.

---

## Documentation Workflow — Always Document What You Build

**Undocumented projects fail review.** Teams can't maintain what they don't understand. Every project you build should have:

1. A project description (`--description` on create, or `set-metadata` after)
2. Column descriptions on key datasets (`set-column-description`)
3. At least one wiki article ("Project Overview")

### Metadata Commands (one command per object, no JSON needed)

| Object | Command |
|--------|---------|
| Project | `dku project set-metadata PROJ --description "..." --name "..."` |
| Dataset | `dku dataset set-metadata DS --description "..." --tags "etl,source" -P PROJ` |
| Dataset columns | `dku dataset set-column-description DS col1 "Revenue" col2 "Customer ID" -P PROJ` |
| Dataset (AI) | `dku dataset ai-describe DS --save -P PROJ` |
| Dashboard | `dku dashboard set-metadata ID --description "..." -P PROJ` |
| Insight | `dku insight set-metadata ID --description "..." -P PROJ` |
| Scenario | `dku scenario set-metadata ID --description "..." -P PROJ` |
| Model | `dku model set-metadata ID --description "..." -P PROJ` |
| Agent | `dku agent set-metadata REF --description "..." -P PROJ` |
| Folder | `dku folder set-metadata REF --description "..." -P PROJ` |
| Zone | `dku flow set-zone ZONE --name "..." --color "#2ab1ac" -P PROJ` |

All `set-metadata` commands accept `--description`, `--short-desc`, and `--tags` (comma-separated). Zone uses `--name` and `--color` instead.

### Minimum Documentation Checklist

After wiring a pipeline, add these to your setup:

```bash
# 1. Project description
dku project set-metadata MY_PROJ --description "Customer churn analytics — joins customer data with events, computes risk features, summarizes by segment."

# 2. Column descriptions on key datasets
dku dataset set-column-description customers \
  customer_id "Unique customer identifier" \
  monthly_spend "Monthly subscription amount in USD" \
  tenure_months "Months since customer signup" \
  -P MY_PROJ

# 3. AI-generated descriptions (quick alternative — requires AI Services enabled)
dku dataset ai-describe customers --save -P MY_PROJ

# 4. Wiki overview
dku wiki create "Project Overview" --body "# Customer Churn Analytics\n\nPipeline that identifies at-risk customers using behavioral features.\n\n## Datasets\n- customers: Source customer data\n- events: User activity events\n- churn_features: Computed risk features\n\n## Recipes\n- join_data: Joins customers with events\n- compute_features: Groups and aggregates features\n\n## Schedule\n- daily_build: Runs nightly at 2am UTC" --if-not-exists -P MY_PROJ
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
  --text-column content \
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

### Knowledge Bank + Embed Pipeline (create -> configure -> build)

**CRITICAL: Vector store defaults to CHROMA.** FAISS can fail silently on some DSS installations.

```bash
# Step 1: Find an embedding model (REQUIRED)
EMBED_LLM=$(dku llm list --purpose TEXT_EMBEDDING_EXTRACTION -P PROJ -o json | jq -r '.[0].id') && \

# Step 2: Create embed recipe with column specified
dku recipe create-embed embed_my_data \
  --input source_dataset \
  --output-kb my_kb \
  --embedding-llm "$EMBED_LLM" \
  --embed-column text_content \
  -P PROJ && \

# Step 3: Run to populate the KB
dku recipe run embed_my_data -P PROJ --wait && \

# Step 4: Verify
dku knowledge search my_kb --query "test query" -P PROJ
```

**Common mistakes:**
- Using a completion LLM ID instead of an embedding LLM ID (`--purpose TEXT_EMBEDDING_EXTRACTION`)
- Omitting `--embed-column` (build will fail with "Embedding column missing")
- Forgetting to `run` the embed recipe after creating it

## Data Reshaping Patterns

### Wide-to-Long (Unpivot/Fold)

When columns like `jan`, `feb`, `mar` need to become rows with `month` + `value`:

```bash
# Create prepare recipe, add fold step, build
dku recipe create reshape --type prepare -i wide_data --output-ds long_data -c filesystem_managed -P PROJ && \
dku recipe add-fold reshape --columns "jan,feb,mar" --key-column month --value-column sales -P PROJ && \
dku job run --target long_data --auto-update-schema --wait -P PROJ
```

For pattern-based folding (all columns matching a regex):
```bash
dku recipe add-fold reshape --pattern ".*-25" --key-column month --value-column value -P PROJ
```

## Prepare Recipe Steps

Prepare recipes support ~95 processor types for data cleaning, enrichment, and transformation. **ALWAYS prefer purpose-built processors over `CreateColumnWithGREL` (GREL formulas).** GREL is the last resort.

**Before adding prepare steps, READ `dataiku` skill's `references/prepare-processors.md`.** It has the processor decision table, required params for each type, and canonical JSON examples. Do not guess params — each processor has specific required fields that differ.

### Step Management Commands

| Command | Purpose |
|---------|---------|
| `list-steps RECIPE -P PROJ` | Show all steps (index, type, disabled, target) |
| `add-step RECIPE --type TYPE --params JSON -P PROJ` | Add any of ~95 processor types (append) |
| `add-step RECIPE --type TYPE --params JSON --at N -P PROJ` | Insert step at index N (0-based) |
| `get-step RECIPE --index N -P PROJ` | Get full step JSON |
| `remove-step RECIPE --index N -P PROJ` | Remove step(s) by index |
| `disable-step RECIPE --index N -P PROJ` | Skip step during execution |
| `enable-step RECIPE --index N -P PROJ` | Re-enable a disabled step |

### Named Shortcuts (prefer these for common operations)

| Task | Command |
|------|---------|
| Computed column (GREL) | `add-formula RECIPE --expr "upper(city)" --column city_upper -P PROJ` |
| Rename columns | `add-rename RECIPE --from old --to new -P PROJ` |
| Filter/flag rows | `add-filter-rows RECIPE --column status --values "active" --action KEEP_ROW -P PROJ` |
| Filter by formula | `add-filter-rows RECIPE --formula "price > 100" --action REMOVE_ROW -P PROJ` |
| Fill empty cells | `add-fill-empty RECIPE --column age --value "0" -P PROJ` |
| Delete columns | `add-delete-columns RECIPE --columns "tmp1,tmp2" -P PROJ` |
| Find & replace | `add-find-replace RECIPE --column city --find "NYC" --replace "New York" -P PROJ` |
| Fold (wide→long) | `add-fold RECIPE --columns "jan,feb,mar" --key-column month --value-column val -P PROJ` |
| Create geopoint | `add-geopoint RECIPE --lat-column lat --lon-column lon -P PROJ` |
| Geo distance | `add-geodistance RECIPE --from-column origin --to-column dest -P PROJ` |

### Processor Selection: Don't Default to GREL

Before reaching for `add-formula`, check if a purpose-built processor exists:

| Need to... | Use this instead of GREL |
|------------|--------------------------|
| Rename columns | `add-rename` (not GREL concat workarounds) |
| Uppercase/lowercase | `add-step --type StringTransformer` (not GREL `upper()`) |
| Concatenate columns | `add-step --type ColumnsConcat` (not GREL `col1 + " " + col2`) |
| If/then/else logic | `add-step --type VisualIfRule` (not GREL `if()` chains) |
| Parse dates | `add-step --type DateParser` (not GREL `toDate()`) |
| Extract year/month/day | `add-step --type DateComponentsExtractor` (not GREL `year()`) |
| Date differences | `add-step --type DateDifference` (not GREL `dateDiff()`) |
| Fill empty values | `add-fill-empty` (not GREL `if(isBlank())`) |
| Bin numbers | `add-step --type BinnerProcessor` (not GREL `if` chains) |
| Split column | `add-step --type ColumnSplitter` (not GREL `split()`) |
| Flatten JSON | `add-step --type JSONFlattener` (not Python json.loads) |
| Remove empty rows | `add-step --type RemoveRowsOnEmpty` (not GREL filter) |
| Filter invalid types | `add-step --type FilterOnBadType` (not GREL type checks) |

**Before writing any `add-step` command, READ `dataiku` skill's `references/prepare-processors.md`** to get the exact params and canonical JSON for the processor you need. The examples above cover common cases, but each processor has required fields that vary — guessing params will fail silently or produce broken steps.

### add-step Examples (processors without shortcuts)

```bash
# Parse date strings to ISO 8601
dku recipe add-step prep --type DateParser \
  --params '{"appliesTo":"SINGLE_COLUMN","columns":["order_date"],"formats":["yyyy-MM-dd"],"lang":"auto","timezone_id":"UTC","outType":{"name":"out","type":"date"}}' -P PROJ

# Extract year and month from parsed date
dku recipe add-step prep --type DateComponentsExtractor \
  --params '{"column":"order_date","timezone_id":"UTC","outYearColumn":"order_year","outMonthColumn":"order_month"}' -P PROJ

# Uppercase a text column
dku recipe add-step prep --type StringTransformer \
  --params '{"mode":"UPPERCASE","appliesTo":"SINGLE_COLUMN","columns":["city"]}' -P PROJ

# Concatenate first + last name
dku recipe add-step prep --type ColumnsConcat \
  --params '{"columns":["first_name","last_name"],"join":" ","outputColumn":"full_name"}' -P PROJ

# Flatten a JSON metadata column
dku recipe add-step prep --type JSONFlattener \
  --params '{"inCol":"metadata","flattenArrays":false,"maxDepth":10,"nullAsEmpty":true,"prefixOutputs":true,"separator":"_"}' -P PROJ

# Remove rows with non-numeric price values
dku recipe add-step prep --type FilterOnBadType \
  --params '{"appliesTo":"SINGLE_COLUMN","columns":["price"],"type":"DoubleMeaning","action":"REMOVE_ROW","considerEmptyAsInvalid":false,"booleanMode":"AND"}' -P PROJ

# Remove all empty rows
dku recipe add-step prep --type RemoveRowsOnEmpty \
  --params '{"appliesTo":"ALL","columns":[],"keep":false}' -P PROJ
```

### Complete Prepare Workflow (chaining multiple processor types)

```bash
# Pre-create output (required for prepare — unlike create-join/create-group, prepare does NOT auto-create)
dku dataset create clean_data --type Filesystem -c filesystem_managed -P PROJ && \
dku recipe create clean_data --type prepare -i raw_data --output-ds clean_data -P PROJ && \
dku recipe add-rename clean_data --from "CustomerName" --to "customer_name" -P PROJ && \
dku recipe add-rename clean_data --from "OrderDate" --to "order_date" -P PROJ && \
dku recipe add-step clean_data --type RemoveRowsOnEmpty --params '{"appliesTo":"ALL","columns":[],"keep":false}' -P PROJ && \
dku recipe add-step clean_data --type StringTransformer --params '{"mode":"LOWERCASE","appliesTo":"SINGLE_COLUMN","columns":["customer_name"]}' -P PROJ && \
dku recipe add-fill-empty clean_data --column price --value "0" -P PROJ && \
dku recipe add-step clean_data --type FilterOnBadType --params '{"appliesTo":"SINGLE_COLUMN","columns":["price"],"type":"DoubleMeaning","action":"REMOVE_ROW","considerEmptyAsInvalid":false,"booleanMode":"AND"}' -P PROJ && \
dku recipe add-delete-columns clean_data --columns "debug_col,temp_id" -P PROJ && \
dku job run --target clean_data --auto-update-schema --wait -P PROJ
```

### Long-to-Wide (Pivot)

```bash
dku recipe create-pivot pivot_monthly -i long_data --output-ds wide_data \
  --row-key customer_id --column-key month --value-column sales -P PROJ
```

### Cross Join (Row Expansion)

Generate all combinations (e.g., records × future months):
```bash
dku recipe create-join expand -i records -i months --output-ds expanded --join-type CROSS -P PROJ
```

### Multi-Input Join (2-5 datasets in one recipe)

**ALWAYS prefer one multi-input join over cascading joins.** See [Join Design: Multi-Input > Cascading](#join-design-multi-input--cascading) for why.

```bash
# Join main with 3 lookups — each with different join keys
dku recipe create-join enrich \
  -i main -i lookup_a -i lookup_b -i lookup_c \
  --output-ds enriched \
  --join-key entity=company \
  --join-key 1:platform \
  --join-key 2:channel=Channel \
  -P PROJ
```

**Index prefix rules:**
- Unprefixed `--join-key col` → applies to join 0 (main ↔ first `-i` after main)
- `1:col` → join 1 (main ↔ second `-i`)
- `2:col` → join 2 (main ↔ third `-i`)
- `col=other_col` → left column `col` matches right column `other_col`
- Same column name on both sides? Just `--join-key col`

```bash
# Example: enrich sales with customer, product, and region lookups
dku recipe create-join enrich_sales \
  -i sales -i customers -i products -i regions \
  --output-ds enriched_sales \
  --join-key customer_id \
  --join-key 1:product_id \
  --join-key 2:region_code=code \
  --join-type LEFT \
  -P PROJ
```

### Random Sampling

```bash
dku recipe create-sampling sample_1k -i big_data --output-ds sample --method RANDOM_FIXED_NB --size 1000 -P PROJ
```

Methods: `RANDOM_FIXED_NB`, `RANDOM_FIXED_RATIO` (use `--ratio 0.1`), `HEAD_SEQUENTIAL`, `STRATIFIED`.

---

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

**Full JSON reference:** See `skills/dataiku/references/dashboard-charts.md`
