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
> 5. **Recipe create auto-creates output for code recipes, but projects without a default managed connection still need `--connection`.** If `dku recipe create -t python|sql` fails on output creation, retry with `--connection NAME`. Visual recipe shortcuts (`create-join`, `create-group`, etc.) auto-create outputs and apply schema.
> 6. **Investigate with `inspect`.** `dku project inspect PROJ -o json` returns datasets, recipes, scenarios, flow, jobs, wiki, variables in ONE call. Start every investigation here.
> 7. **Chain everything.** All related commands in ONE `&&`-chained Bash call. Never separate tool calls.
> 8. **Charts need `--dataset`.** `dku insight create NAME --type chart --dataset DS -P PROJ`. Validate with `dku insight validate ID -P PROJ`.
> 9. **Verify everything.** After building, ALWAYS `dku dataset head OUTPUT -P PROJ` to confirm real data exists. `dku dataset head OUTPUT -o json` returning `[]` means 0 rows, not success. Exit code 0 ≠ correct output. Also use the `dataiku` skill for platform knowledge — these two skills are a pair.
> 10. **Prefer purpose-built prepare processors over GREL.** Need to rename? `add-rename`. Parse dates? `add-step --type DateParser`. Uppercase? `add-step --type StringTransformer`. If/then/else? `add-step --type VisualIfRule`. Use `add-formula` (GREL) ONLY when no dedicated processor exists. **READ `dataiku` skill's `references/prepare-processors.md` before writing any `add-step` command** — it has the exact params and JSON for each processor.
> 11. **Gauge before you grab.** Run `dku dataset info DS -P PROJ` BEFORE `head` or any build. Datasets can be millions of rows / gigabytes. If >1M rows or >1GB, ask the user before triggering builds or LLM recipes. Never blindly `head -n 1000` on a dataset you haven't gauged. For existing projects, follow the exploration protocol in the `dataiku` skill.
> 12. **Sample data before transforming.** After gauging size, run `dku dataset head INPUT -P PROJ -n 5` and `dku dataset schema INPUT -P PROJ` to inspect actual column names, values, and formats. Don't guess date formats, column names, or value patterns — verify first. For joins, check both datasets have the join key.
> 13. **Document what you build.** After creating a project, set its description (`dku project set-metadata PROJ --description "..."`). After creating datasets, describe columns (`dku dataset set-column-description DS col1 "desc" -P PROJ`). Create at least one wiki article ("Project Overview"). Use `set-metadata` on any object. Undocumented projects are incomplete projects.
> 14. **One multi-input join > cascading joins.** Joining A+B, then result+C, then result+D = 3 recipes, 3 intermediate datasets, 3x build time. Instead: one `create-join -i A -i B -i C -i D` with index-prefixed keys. See [Visual Recipe Design Patterns](#visual-recipe-design-patterns).
> 15. **Read reference files BEFORE exploring.** This skill has detailed reference docs in `references/`. When you need syntax, examples, or patterns for a specific task, **read the relevant reference file first** — don't try to figure it out from `--help` alone or by trial and error. The reference index at the bottom tells you which file covers what.

# dku-cli

`dku` is a kubectl-style CLI for Dataiku DSS. It wraps `dataikuapi` with auth management, output formatting, and composable shell commands.

## Think Dataiku-First (CRITICAL — read before every task)

**You are not writing Python scripts that happen to use DSS. You are operating a platform that has purpose-built features for nearly everything.**

Before you construct ANY command, stop and ask:

1. **"Does DSS have a visual recipe for this?"** — Join, group, stack, filter, sort, distinct, window, topN, pivot, split, sampling. If yes, use it. If you're about to write `pd.merge()`, `df.groupby()`, `pd.concat()`, or `df.drop_duplicates()` inside a Python recipe — you've already gone wrong. Go back and use the visual recipe.

2. **"Does DSS have a purpose-built processor for this?"** — Before writing ANY GREL formula in a prepare recipe, check: is there a dedicated processor? Rename → `add-rename`. Dates → `DateParser`. Uppercase → `StringTransformer`. If/else → `VisualIfRule`. Concat → `ColumnsConcat`. GREL is the LAST resort, not the default. Read `dataiku` skill's `references/prepare-processors.md` — there are ~95 processors.

3. **"Am I cascading when I should combine?"** — If you're about to create join A+B → temp, then temp+C → output, STOP. One `create-join -i A -i B -i C` does it in a single recipe with zero intermediate datasets.

4. **"Does DSS have a built-in ML workflow for this?"** — `dku ml create-prediction` + `train` + `deploy` handles classification, regression, clustering, timeseries, and causal inference. Python ML code is only for custom model architectures.

**The pattern is always the same: platform feature first, Python last.** DSS visual recipes give you lineage tracking, schema propagation, visual debugging, and reproducibility for free. Python recipes give you none of that. Every time you choose Python over a visual recipe, you're making the project harder to maintain.

**This is the single most important behavioral rule in this skill.** If you get nothing else right, get this right.

## Companion Skill: `dataiku`

**This skill and `dataiku` are a pair. Always use both.**

- **This skill** tells you *how to execute* — CLI commands, flags, chaining, build patterns
- **`dataiku`** tells you *what* to build and *how DSS works* — which recipe type, which agent architecture, plugin patterns, formula syntax

**Before writing any CLI commands**, consult the `dataiku` skill to confirm you're using the right DSS approach. The CLI can create a Python recipe in seconds — but if a visual recipe exists for that task, you've chosen wrong.

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

### Verification Rules

1. **Always `head` the final output dataset.** This is the #1 verification — if output looks right, the pipeline works.
2. **Never assume success from exit code alone.** A recipe can "build successfully" but produce 0 rows.
3. **Check intermediate datasets when debugging.** If the final output is wrong, `head` each intermediate dataset to find where it breaks.
4. **Validate chart insights.** `dku insight validate ID -P PROJ` catches column name mismatches that render blank charts.
5. **Test agents end-to-end.** Creating agent + tools is not enough — verify the agent can actually call its tools.

> For task-specific verification blocks (agents, knowledge banks, semantic models, agent hub), see `references/workflow-templates.md`.

## Prerequisites

```bash
dku --version    # Check if installed
```

If not installed:

```bash
uv tool install git+https://github.com/dataiku/dataiku-cli.git
dku auth login          # authenticate to your DSS instance
```

> **Chaining Rule:** Always `&&`-chain related `dku` commands in a **single Bash tool call**. Each separate tool call costs a full agent turn (~$0.05 + 3s). A 10-command workflow should be 1 tool call, not 10. See `references/workflow-templates.md` for chaining templates.

> For detailed auth setup (CI/CD, env vars, profiles), see `references/setup.md`.

## When to Use dku vs Python API

| Use `dku` CLI | Use Python API directly |
|---|---|
| Quick queries: list, inspect, status | Complex multi-step workflows |
| CRUD: create, delete, configure resources | DataFrame operations (pandas) |
| Shell scripts / CI/CD pipelines | Custom transformations |
| Piping output to jq/grep/awk | Bulk programmatic operations |
| End-to-end project automation | When CLI doesn't cover the API |

> **Within the CLI, visual recipes vs Python recipes is a separate choice.** The table above is CLI vs Python API. For recipe type selection, see [Recipe Decision Tree](#recipe-decision-tree). Default to visual recipes; use Python recipes only for custom logic.

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

| Format | Flag | Best for |
|---|---|---|
| Rich table | `-o table` (default) | Human reading |
| JSON | `-o json` | Piping to jq, programmatic use |
| CSV | `-o csv` | Spreadsheets, further processing |

JSON goes to stdout (clean for piping). Status messages go to stderr.

### JSON Input

Creation/mutation commands accept `--definition JSON` (literal, `@file.json`, or `-` for stdin). Code commands accept `--code` with the same patterns.

---

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

> For multi-dataset projects and full lifecycle templates, see `references/workflow-templates.md`.

---

## Creating Recipes (CRITICAL — visual first, Python last)

**STOP. Re-read [Think Dataiku-First](#think-dataiku-first-critical--read-before-every-task) before creating any recipe.**

If your next command is `dku recipe create NAME -t python`, ask yourself: is there a visual recipe that does this? In 90% of cases, there is. The recipe decision tree below is exhaustive — if the task appears there, use the visual recipe. Python is the escape hatch for custom logic that no visual recipe can express.

### Pre-Recipe Checklist

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

### Recipe Decision Tree

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

### Visual Recipe Selection Guide

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
| **Pivot (long->wide)** | `dku recipe create-pivot NAME -i ds --output-ds out --row-key id --column-key month --value-column val --agg-type SUM -P PROJ` | ~~df.pivot_table()~~ |
| **Unpivot (wide->long)** | `dku recipe add-fold PREP --columns "jan,feb,mar" --key-column month --value-column val -P PROJ` | ~~pd.melt()~~ |
| **Random sample** | `dku recipe create-sampling NAME -i ds --output-ds out --size 1000 -P PROJ` | ~~df.sample()~~ |
| **Cross join (cartesian)** | `dku recipe create-join NAME -i A -i B --output-ds out --join-type CROSS -P PROJ` | ~~itertools.product()~~ |
| **Custom logic ONLY** | `dku recipe create NAME -t python -i ds --output-ds out -P PROJ` | Last resort |

Visual recipe commands auto-create the output dataset. For advanced configuration beyond CLI flags (custom join conditions, additional aggregations, post-filters), use `dku recipe get-settings RECIPE -P PROJ -o json` to read the current payload, then `dku recipe set-definition RECIPE --payload '...' -P PROJ` to update. **READ `dataiku` skill's `references/visual-recipe-payloads.md` for payload schemas and `references/visual-conditions.md` for filter/condition JSON.**

> For detailed recipe code examples (join, group, topN, window, reshaping), see `references/recipe-examples.md`.

### Common Recipe Mistakes

| Mistake | Fix |
|---------|-----|
| Cascading joins (A+B -> temp, temp+C -> out) | One `create-join -i A -i B -i C` with index-prefixed keys |
| Default INNER join when enriching | Use `--join-type LEFT` to keep all source rows |
| Python `groupby([col1, col2])` | Repeat `-k`: `-k col1 -k col2` on `create-group` |
| Python `nlargest(N)` or `sort + head` | Use `create-topn --n N --rank-by col:desc` |
| Python `groupby().first()` / `last()` | Use `create-topn --n 1 --rank-by col:desc -k group_col` |
| Python `groupby().transform(rank)` | Use `create-window --compute 'rowNumber::rn'` |
| Python `pivot_table(aggfunc='sum')` | Use `create-pivot --agg-type SUM` |
| `set-definition` doesn't change visual config | Use `--payload` (not `--definition`) for visual recipe config |
| TopN recipe has no ordering | Use `--rank-by col:desc` and `--n N` flags |
| `set-definition` orphans auto-created output (plugin recipes) | Pre-create output datasets before `recipe create` when using plugin recipes with named roles |
| Plugin recipe SELECT values wrong case | `selectChoices` values are case-sensitive. Check `dku plugin recipes PLUGIN -o json` for exact values |
| `dku dataset build` fails for folder outputs | Use `dku recipe run RECIPE -P PROJ --wait` for managed folder outputs |
| Prepare recipe `create` fails with "Output dataset does not exist" | Unlike visual recipes, `create --type prepare` does NOT auto-create the output. Pre-create it first |
| `add-fold` or `add-filter-rows --formula` fails with `UnavailableTypeException` | Plugin processors unavailable on some instances. For fold: use Python `pd.melt()`. For filter: use `add-step --type FilterOnCustomFormula` |
| GREL formula returns null for columns with spaces | Columns with spaces can't be referenced via GREL. Use `add-rename` first, or a Python recipe |

### Python Recipe (ONLY when visual recipes can't express the logic)

```bash
dku recipe create compute_risk_score -t python -i customer_features --output-ds risk_scores -P PROJ && \
dku recipe set-code compute_risk_score -P PROJ --code @score.py
```

**Flags for `dku recipe create` (Python/SQL):**
- `--type python` / `-t python` — recipe type
- `--input NAME` / `-i NAME` / `--input-ds NAME` — input dataset (MUST already exist)
- `--output-ds NAME` — output dataset (auto-created for code recipes)
- `--connection NAME` / `-c NAME` — required when the DSS project has no default managed connection (common in Snowflake-backed projects)
- `-P PROJECT` — project key

If you need the output connection name and `dku connection list` is unavailable, inspect an existing managed dataset:

```bash
dku dataset get-definition ANY_DATASET -P PROJ -o json | jq -r '.params.connection'
```

#### Cross-Project Inputs

Recipes can read datasets from another project by referencing them as `PROJECT_KEY.DATASET_NAME` in recipe inputs:

```bash
dku recipe create compute_metrics -t python \
  -i EDP_GOLD_DATASETS.account_base \
  --output-ds account_metrics \
  --connection filesystem_managed \
  -P PROJ
```

This cross-project reference works in recipe inputs even when `dku dataset head PROJECT_KEY.DATASET_NAME` does not.

#### Python ID Casting Pattern

When ID columns can contain nulls or non-numeric strings, coerce before casting:

```python
df["ACCOUNT_SK"] = pd.to_numeric(df["ACCOUNT_SK"], errors="coerce")
df = df.dropna(subset=["ACCOUNT_SK"])
df["ACCOUNT_SK"] = df["ACCOUNT_SK"].astype("int64")
```

Direct `.astype("int64")` on dirty data fails with `IntCastingNaNError`.

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

### Deleting Datasets, Recipes, and Projects

`dku dataset delete` and `dku recipe delete` prompt by default and support `--yes` / `-y` to skip confirmation. `dku project delete` requires `--confirm`, `--yes`, or `-y`.

```bash
# Dataset delete (prompts without --yes)
dku dataset delete my_data -P MY_PROJ --yes

# Recipe delete (prompts without --yes)
dku recipe delete my_recipe -P MY_PROJ --yes

# Project delete (requires --confirm, --yes, or -y)
dku project delete MY_PROJ --yes
```

---

## Quick Reference

For flag details on any command, run `dku <noun> <verb> --help`. For full command syntax with examples, **read `references/commands.md`**.

### Command Groups

| Group | Verbs | Needs Project? |
|---|---|---|
| `auth` | login, logout, status, list, switch | No |
| `config` | set, get, list, path, variables, set-variables | No |
| `project` | list, get, **inspect**, export, create, delete, duplicate, set-metadata, variables, set-variables, permissions, set-permissions, tags, **ai-describe, timeline** | No |
| `plugin` | list, get, push, delete, **download**, settings, create-code-env, set-code-env, update-code-env, usages, **recipes, list-files, get-file, put-file, rename-file, move-file, install-from-store, install-from-git, update-from-store, update-from-git** | No |
| `code-env` | list, get, create, delete, update | No |
| `connection` | list, **get**, create, **delete**, test, **schemas, tables, sync-acls** | No (admin, schemas/tables need `-P`) |
| `user` | list, **get**, create, **delete, activity, add-secret** | No (admin) |
| `sql` | query | No |
| `dataset` | list, schema, **info**, head, build, create, upload, delete, clear, get-definition, set-definition, set-schema, **set-metadata, set-column-description, ai-describe, rename, copy, partitions, exists, usages, lineage, detect, zone, share, unshare** | Yes |
| `recipe` | list, get, **get-definition**, run, create, delete, set-code, get-code, set-definition, **get-settings, set-settings**, add-input, add-output, check-schema, apply-schema, **rename, status**, **create-join, create-group, create-stack, create-distinct, create-sort, create-filter, create-window, create-split, create-topn, create-pivot, create-sampling**, create-embed, create-embed-docs, create-extract, create-llm-eval, create-agent-eval, **list-steps, add-step, get-step, remove-step, disable-step, enable-step, add-formula, add-rename, add-filter-rows, add-fill-empty, add-delete-columns, add-find-replace, add-fold, add-geopoint, add-geodistance** | Yes |
| `scenario` | list, run, abort, status, create, delete, get-definition, set-definition, **last-run, runs, avg-duration, run-log, set-metadata, list-triggers, add-trigger, add-trigger-dataset, remove-trigger** | Yes |
| `job` | list, run, status, log, abort, wait | Yes |
| `model` | list, get, versions, set-active-version, metrics, delete-version, delete, usages, **set-metadata, create-mlflow, import-mlflow, create-external** | Yes |
| `folder` | list, ls, upload, download, create, delete, delete-file, get, create-dataset, **set-metadata** | Yes |
| `llm` | list, completion, embeddings, **generate-image, rerank** | Yes |
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
| `api-service` | list, create, get, create-package, list-packages, **add-endpoint, list-endpoints, publish-package, delete-package** | Yes |
| `rag` | **list, create, get, delete, get-definition, set-definition** | Yes |
| `continuous` | **list, start, stop, status** | Yes |
| `meaning` | **list, get, create, update** | No (admin) |
| `project-folder` | **list, create, move-project** | No |
| `model-comparison` | **list, create, get, add-model, remove-model, delete** | Yes |
| `workspace` | **list, create, get, list-objects, delete** | No |
| `app` | **list, get, list-instances, create-instance** | No |
| `streaming` | **list, create, get, delete, schema, set-schema** | Yes |
| `admin` | **logs, get-log, usage, instance-info, sanity-check** | No (admin) |
| `api-key` | **list, get, create, delete** | No (admin) |
| `cluster` | **list, get, create, start, stop, status, delete** | No (admin) |
| `wiki` | list, create, get, update, delete | Yes |
| (root) | whoami | No |

Key notes:
- `dku llm list` defaults to `GENERIC_COMPLETION`. Pass `--purpose TEXT_EMBEDDING_EXTRACTION` for embedding models.
- `dku llm embeddings` rejects completion-only model IDs — list embedding models first.
- `dku semantic-model` — Versions are key: only the active version is used by agents. Always `update-index --wait` after changing entities/attributes.
- `dku agent-hub` — **Cannot create** Agent Hub via CLI (it's a plugin webapp — create in DSS UI first). `--hub` auto-detects when one hub exists; required when multiple exist.

---

## Chaining Rule

**NEVER issue related `dku` commands as separate tool calls.** Chain with `&&` in ONE Bash call. Separate calls = separate agent turns = 2x slower, 2.5x more expensive.

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

> For complete chaining templates (pipeline, agent+KB, ML, deploy, plugin), see `references/workflow-templates.md`.

---

## Investigation Workflow (1-3 tool calls)

**When asked to explore, debug, or understand an existing project:**

```bash
# Tool call 1 — Full project overview (replaces 7+ separate commands)
dku project inspect MY_PROJ -o json
```

Parse the JSON output to understand the project structure. Then **gauge sizes before touching data**:

```bash
# Tool call 2 — Gauge key datasets (ALWAYS before head/build)
dku dataset info source_ds1 -P MY_PROJ && \
dku dataset info source_ds2 -P MY_PROJ && \
dku dataset info final_output -P MY_PROJ
```

Only after gauging sizes, drill into specifics:

```bash
# Tool call 3 — Sample data and inspect recipes
dku dataset head specific_ds -P MY_PROJ -n 10 && \
dku recipe get-settings suspect_recipe -P MY_PROJ && \
dku job status last_job_id -P MY_PROJ -o json && \
# When a build fails, start with focused log inspection:
dku job log JOB_ID -P MY_PROJ --errors-only --tail 80
```

> **Cost rule:** If `info` shows >1M rows or >1GB, don't trigger builds or LLM recipes without asking the user. Escalate with the size info and estimated impact.

---

## Agent Creation + Tool Creation

### Creating Agents

Agents require `--type`. Default is `TOOLS_USING_AGENT` (visual agent with tools).

```bash
# Create agent with LLM and tools — all one call
dku agent create my_agent --type TOOLS_USING_AGENT -P PROJ && \
dku agent set-llm my_agent --llm-id "openai:gpt-4o-mini" -P PROJ && \
dku agent add-tool my_agent --tool my_tool -P PROJ
```

Valid types: `TOOLS_USING_AGENT`, `PYTHON_AGENT`, `PLUGIN_AGENT`, `STRUCTURED_AGENT`.

### Agent Tool Types (Two-Step: create tool, then attach)

**Built-in tool types** (use `dku agent-tool types` to list):

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

> **No built-in PythonFunction type.** Custom Python tools must be built as plugins. For SVA graph patterns, plugin tools, agent evaluation, and LLM ID discovery, see `references/agent-patterns.md`.

---

## Critical Patterns

### Join Column Name Prefixing

DSS join recipes prefix column names with the dataset name. If you join `customers` and `orders`, the resulting columns are `customers_name`, `orders_amount`, etc. Plan downstream column references accordingly.

### Project Variables

```bash
# Set individual standard variables (--set is repeatable)
dku project set-variables -P PROJ --set threshold=0.8 --set env=staging

# Replace ALL variables from JSON
dku project set-variables -P PROJ --definition '{"standard": {"key": "val"}, "local": {}}'
```

**Common mistake:** `--json` does not exist. Use `--set key=value` for individual vars or `--definition JSON` for full replacement.

### Deleting Datasets and Projects

Both `dku dataset delete` and `dku project delete` support `--yes` / `-y` to skip confirmation:

```bash
dku dataset delete my_data -P MY_PROJ --yes
dku project delete MY_PROJ --yes
```

---

## Pipeline Building Best Practices

### Anti-Pattern: Step-by-Step Builds

```bash
# BAD — each build is non-recursive, no schema updates.
# If schemas don't match between steps, every downstream build fails.
dku dataset build ds_a -P PROJ --wait && \
dku dataset build ds_b -P PROJ --wait && \
dku dataset build ds_c -P PROJ --wait
```

### Correct Pattern: Wire First, Build Once

**Step 1:** Wire the entire pipeline (datasets + recipes) in one `&&` chain. Visual recipe commands auto-create managed output datasets.

```bash
dku dataset create customers --type UploadedFiles -P PROJ && \
dku dataset upload customers /tmp/customers.csv -P PROJ && \
dku dataset create orders --type UploadedFiles -P PROJ && \
dku dataset upload orders /tmp/orders.csv -P PROJ && \
dku recipe create-join enrich -i customers -i orders --output-ds enriched --join-key customer_id -P PROJ && \
dku recipe create-group summarize -i enriched --output-ds summary -k customer_id --agg "amount:sum,avg" -P PROJ
```

**Step 2:** Build with auto-schema (one command):

```bash
dku job run --target summary -P PROJ \
  --type RECURSIVE_BUILD \
  --auto-update-schema \
  --wait
```

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
| Build recipe that outputs to a managed folder | `dku recipe run RECIPE -P PROJ --wait` (folders NOT buildable via `dataset build`) |
| Inspect a failed build log | `dku job log JOB_ID -P PROJ` |

### Build Types

| Type | Behavior |
|---|---|
| `NON_RECURSIVE_FORCED_BUILD` | Build only specified outputs (default) |
| `RECURSIVE_BUILD` | Build outputs + upstream dependencies that need building |
| `RECURSIVE_FORCED_BUILD` | Force-rebuild outputs + ALL upstream dependencies |
| `RECURSIVE_MISSING_ONLY_BUILD` | Build only outputs that have never been built |

### Schema Propagation vs Auto-Update Schema

- **`dku flow propagate SOURCE_DS`**: Propagates schema changes through downstream recipes WITHOUT building.
- **`--auto-update-schema` on build/run**: Updates schemas DURING the build.
- **`dku recipe check-schema` + `apply-schema`**: Per-recipe schema inspection. Only works for visual recipes.

---

## Visual Recipe Design Patterns

### Recipe Type Semantics — When to Use What

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
| **Split** | 1 dataset -> 2+ | Route rows to different outputs | Different downstream paths per condition | Single-output filtering (use Filter) |
| **Pivot** | 1 dataset | Long->wide (columns from values) | Timeseries to columns, category expansion | Wide->long (use Prepare add-fold) |
| **Sampling** | 1 dataset | Reduce dataset size | Dev/test subsets, stratified samples | Filtering by condition (use Filter) |
| **Prepare** | 1 dataset | Row-level transforms, cleaning | Rename, parse dates, GREL formulas, fold | Aggregation (use Group), joins (use Join) |

### Join Design: Multi-Input > Cascading

One `create-join -i A -i B -i C -i D` with index-prefixed keys is ALWAYS better than cascading A+B -> temp -> temp+C -> out (3 recipes, 2 intermediate datasets, column prefix explosion).

```bash
dku recipe create-join enrich_sales \
  -i sales -i customers -i products -i regions \
  --output-ds enriched_sales \
  --join-key customer_id \
  --join-key 1:product_id \
  --join-key 2:region_code=code \
  --join-type LEFT \
  -P PROJ
```

**When cascading IS acceptable:** Different join types per step, or when intermediate datasets are reused by other recipes.

### Join Types

| Type | Flag | Keeps | Use when... |
|------|------|-------|-------------|
| **LEFT** | `--join-type LEFT` | All left rows, matched right | Enriching — keep all source rows even without match |
| **INNER** | `--join-type INNER` (default) | Only matched rows | Both sides must have the key |
| **RIGHT** | `--join-type RIGHT` | All right rows, matched left | Rare — usually restructure as LEFT |
| **FULL** | `--join-type FULL` | All rows from both sides | Reconciliation, finding mismatches |
| **CROSS** | `--join-type CROSS` | Cartesian product (every combo) | Row expansion (records x months) |

**Default is INNER.** If your task says "enrich" or "look up", you almost always want **LEFT**.

### Common Pipeline Anti-Patterns

| Anti-pattern | Why it's wrong | Do this instead |
|--------------|---------------|-----------------|
| Cascading joins (A+B -> temp -> temp+C) | Extra recipes, intermediate datasets, column prefix explosion | One multi-input join with index-prefixed keys |
| Python `groupby` when Group recipe works | Slower, harder to maintain, no visual lineage | `create-group -k col --agg "col:sum,avg"` |
| Filter + Sort + head for top N | 3 recipes for what TopN does in 1 | `create-topn --n N --rank-by col:desc` |
| Window recipe just for first-per-group | Overkill — need Window + Filter (2 recipes) | `create-topn --n 1 -k group_col` |
| Python for column rename/type cast | Breaks visual lineage | Prepare recipe: `add-rename`, `add-step --type TypeSetter` |
| Separate Filter recipes per condition | Bloated flow, redundant scans | One Split recipe with multiple conditions |
| `pd.concat()` for stacking datasets | No visual lineage, handles schema drift poorly | `create-stack -i ds1 -i ds2` |

> For detailed recipe code examples (window functions, data reshaping, multi-input joins), see `references/recipe-examples.md`.

---

## Documentation — Always Document What You Build

**Undocumented projects fail review.** Every project you build must have:

1. A project description (`--description` on create, or `set-metadata` after)
2. Column descriptions on key datasets (`set-column-description`)
3. At least one wiki article ("Project Overview")

### Metadata Commands

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

All `set-metadata` commands accept `--description`, `--short-desc`, and `--tags` (comma-separated).

> For full documentation code examples (wiki creation, column descriptions), see `references/workflow-templates.md`.

---

## Prepare Recipe — Named Shortcuts

**STOP. Before writing ANY prepare step, re-read [Think Dataiku-First](#think-dataiku-first-critical--read-before-every-task) rule #2.**

There are ~95 purpose-built processors. If you're about to write `add-formula` with a GREL expression, you are almost certainly using the wrong tool. Check the table below, then check `references/prepare-guide.md`, then check `dataiku` skill's `references/prepare-processors.md`. Use `add-formula` (GREL) ONLY when you've confirmed no dedicated processor exists for your task.

| Task | Command |
|------|---------|
| Computed column (GREL) | `add-formula RECIPE --expr "toUppercase(city)" --column city_upper -P PROJ` |
| Rename columns | `add-rename RECIPE --from old --to new -P PROJ` |
| Filter/flag rows | `add-filter-rows RECIPE --column status --values "active" --action KEEP_ROW -P PROJ` |
| Filter by formula | `add-filter-rows RECIPE --formula "price > 100" --action REMOVE_ROW -P PROJ` |
| Fill empty cells | `add-fill-empty RECIPE --column age --value "0" -P PROJ` |
| Delete columns | `add-delete-columns RECIPE --columns "tmp1,tmp2" -P PROJ` |
| Find & replace | `add-find-replace RECIPE --column city --find "NYC" --replace "New York" -P PROJ` |
| Fold (wide->long) | `add-fold RECIPE --columns "jan,feb,mar" --key-column month --value-column val -P PROJ` |
| Create geopoint | `add-geopoint RECIPE --lat-column lat --lon-column lon -P PROJ` |
| Geo distance | `add-geodistance RECIPE --from-column origin --to-column dest -P PROJ` |

> **Before writing any `add-step` command**, read `references/prepare-guide.md` for the step management commands and JSON params for each processor type, and the `dataiku` skill's `references/prepare-processors.md` for the full processor decision table.

---

## Reference Files

**Read the relevant reference file BEFORE attempting a task.** These files contain the detailed syntax, examples, and patterns you need. Don't try to guess from `--help` alone — the reference files are faster and more complete.

| File | Read when... |
|---|---|
| `references/commands.md` | Need exact flags, syntax, or examples for any `dku` command |
| `references/setup.md` | Setting up auth, CI/CD environment variables, output format details |
| `references/workflow-templates.md` | Need a complete project template, chaining examples, or composability patterns |
| `references/recipe-examples.md` | Need detailed recipe code (join, group, topN, window, reshape, plugin recipes) |
| `references/agent-patterns.md` | Building SVAs, agent tools, agent evaluation, LLM ID discovery |
| `references/genai-recipes.md` | Embedding, RAG pipelines, knowledge banks, LLM eval, model deployment |
| `references/prepare-guide.md` | Adding prepare steps with `add-step`, processor JSON params, step management |
| `references/dashboard-patterns.md` | Charts, dashboards, tiles, chart JSON anatomy |

Also use the companion `dataiku` skill's references for platform knowledge:
- `references/visual-recipe-payloads.md` — JSON payloads for join/group/window/filter recipes
- `references/visual-conditions.md` — Filter/condition JSON schemas
- `references/prepare-processors.md` — Full processor decision table (~95 types)
- `references/dashboard-charts.md` — Full chart JSON anatomy
- `references/structured-agents.md` — SVA design guide, block types, state management
