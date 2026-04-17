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
> 1. **STOP — DO NOT write Python for joins, aggregations, dedup, sort, filter, stack, or window ops.** Use `create-join`, `create-group`, `create-stack`, `create-distinct`, `create-sort`, `create-filter`, `create-window`, `create-topn`. Python is ONLY for custom logic. See `references/recipe-decision.md`.
> 2. **Use `dku ml` for ML — not Python.** `dku ml create-prediction` + `dku ml train` + `dku ml deploy` covers prediction, clustering, timeseries, and causal. Python ONLY for custom model architectures.
> 3. **Visual recipes auto-apply schema.** `create-join`/`create-group`/etc. auto-propagate output schemas. For manual control: `dku recipe apply-schema RECIPE -P PROJ`, or `--auto-update-schema` on build.
> 4. **Upload = UploadedFiles.** `dku dataset create NAME --type UploadedFiles -P PROJ`. Never Filesystem for uploads.
> 5. **Code recipes need `--connection`** when project has no default managed connection. Visual recipe shortcuts auto-create outputs and apply schema.
> 6. **Investigate with `inspect`.** `dku project inspect PROJ -o json` returns datasets, recipes, scenarios, flow, jobs, wiki, variables in ONE call.
> 7. **Chain everything.** All related commands in ONE `&&`-chained Bash call. Never separate tool calls.
> 8. **Charts need `--dataset`.** `dku insight create NAME --type chart --dataset DS -P PROJ`. Validate with `dku insight validate ID -P PROJ`.
> 9. **Verify everything.** After building, ALWAYS `dku dataset head OUTPUT -P PROJ` to confirm real data exists. `dku dataset head OUTPUT -o json` returning `[]` means 0 rows, not success. Exit code 0 ≠ correct output. Also use the `dataiku` skill for platform knowledge — these two skills are a pair.
> 10. **Prefer purpose-built prepare processors over GREL.** `add-rename`, `add-step --type DateParser`, `add-step --type StringTransformer`, `add-step --type VisualIfRule`. Use `add-formula` (GREL) ONLY when no dedicated processor exists. See `dataiku` skill's `references/prepare-processors.md`.
> 11. **Gauge before you grab.** Run `dku dataset info DS -P PROJ` BEFORE `head` or any build. If >1M rows or >1GB, ask the user before triggering builds or LLM recipes.
> 12. **Sample data before transforming.** Run `dku dataset head INPUT -P PROJ -n 5` and `dku dataset schema INPUT -P PROJ` to inspect actual column names, values, and formats. Don't guess date formats or column names — verify first. For joins, check both datasets have the join key.
> 13. **Document what you build.** `dku project set-metadata PROJ --description "..."`, `dku dataset set-column-description DS col1 "desc" -P PROJ`, at least one wiki article. Undocumented projects are incomplete projects.
> 14. **One multi-input join > cascading joins.** One `create-join -i A -i B -i C -i D` with index-prefixed keys, not A+B → temp → temp+C → out.
> 15. **Read reference files BEFORE exploring.** This skill has detailed reference docs in `references/`. Read the relevant file first — don't try to figure it out from `--help` alone.
> 16. **Cross-connection landing is a first-class feature.** `dku recipe create -t sync --connection X` moves data between connections. Never write a Python passthrough. See `references/sql-engines.md`.
> 17. **SVAs need STRUCTURED_AGENT.** `dku agent create NAME --type STRUCTURED_AGENT -P PROJ`. Every CORE_LOOP block needs `"llmId"`. Every SAVE_TO_STATE block needs `"outputKey"`. Never use `""` in SET_STATE_ENTRIES values (use `"''"` for empty CEL string). See `references/agent-patterns.md`.

# dku-cli

`dku` is a kubectl-style CLI for Dataiku DSS. It wraps `dataikuapi` with auth management, output formatting, and composable shell commands.

## Companion Skill: `dataiku`

**This skill and `dataiku` are a pair. Always use both.**

- **This skill** tells you *how to execute* — CLI commands, flags, chaining
- **`dataiku`** tells you *what* to build and *how DSS works* — platform features, recipe types, agent architectures

## Think Dataiku-First (CRITICAL)

**Platform feature first, Python last.** Before any command:

1. **"Does DSS have a visual recipe for this?"** — join, group, stack, filter, sort, window. If yes, use it.
2. **"Does DSS have a purpose-built processor?"** — rename → `add-rename`, dates → `DateParser`, uppercase → `StringTransformer`.
3. **"Am I cascading when I should combine?"** — one `create-join -i A -i B -i C` instead of A+B → temp → temp+C.
4. **"Does DSS have built-in ML?"** — `dku ml create-prediction` handles classification, regression, clustering, timeseries.

## Verification Protocol

**Your job is done when you've verified the output, not when commands exit 0.**

```bash
# Build + verify
dku job run --target FINAL_OUTPUT -P PROJ \
  --type RECURSIVE_BUILD \
  --auto-update-schema \
  --wait && \
dku dataset head FINAL_OUTPUT -P PROJ -n 5 && \
dku dataset info FINAL_OUTPUT -P PROJ --recompute
```

**Rules:**
- Always `head` the final output
- Never assume success from exit code alone
- Check intermediate datasets when debugging

> For detailed verification (agents, KB, semantic models), see `references/workflow-templates.md`.

## Prerequisites

```bash
dku --version
uv tool install git+https://github.com/dataiku/dataiku-cli.git
dku auth login
```

> For CI/CD setup, see `references/setup.md`.

## When to Use dku vs Python API

| Use `dku` CLI | Use Python API |
|---|---|
| Quick queries, CRUD, shell scripts | Complex multi-step workflows |
| Piping to jq/grep | DataFrame operations |

## Command Pattern

`dku <noun> <verb> [ARGS] [OPTIONS]`

### Global Options

| Flag | Env Var | Purpose |
|---|---|---|
| `--url URL` | `DKU_URL` | DSS instance URL |
| `--api-key KEY` | `DKU_API_KEY` | API key |
| `--profile NAME` / `-p` | — | Auth profile |
| `--quiet` / `-q` | — | Suppress messages |
| `--errors text\|json` | — | Error format |

### Project Resolution

1. `--project KEY` / `-P KEY` flag
2. `DKU_PROJECT` env var
3. `dku config set default_project KEY`

### Output Formats

| Format | Flag | Best for |
|---|---|---|
| Rich table | `-o table` | Human reading |
| JSON | `-o json` | Piping to jq |
| CSV | `-o csv` | Spreadsheets |

## Quick Reference

| Group | Key Verbs |
|---|---|
| `project` | list, inspect, create |
| `dataset` | list, schema, info, head, create, upload, build |
| `recipe` | list, get-definition, run, create, delete, create-join, create-group, create-stack |
| `job` | run, status, log |
| `scenario` | list, run, status, runs |
| `agent` | list, create, add-tool, set-llm |
| `knowledge` | list, create, build, search |
| `insight` | list, create, validate |
| `llm` | list, completion, embeddings |

### Dataset Types (CRITICAL)

| Type | Upload? | Use For |
|---|---|---|
| `UploadedFiles` | Yes | CLI uploads |
| `Filesystem` | No | Recipe outputs |

> **Rule:** If uploading, MUST use `--type UploadedFiles`.

### Recipe Decision Tree

```
join/merge?         → create-join --join-key col
aggregation?        → create-group -k col1 -k col2 --agg col:sum,avg
stacking?           → create-stack
dedup?              → create-distinct
sorting?            → create-sort
filter rows?        → create-filter
window/rank?        → create-window --compute 'rowNumber::rn'
top N?              → create-topn --n 10 --rank-by col:desc
pivot (long→wide)?  → create-pivot --agg-type SUM
unpivot (wide→long)?→ Prepare recipe + add-fold
random sample?      → create-sampling --size 1000
cross join?         → create-join --join-type CROSS
passthrough/copy?   → create -t sync
cross-connection?   → create -t sync --connection TARGET_CONN
None of above?      → create -t python
```

> For full recipe examples, see `references/recipe-decision.md`.

### Deletion Commands

Both prompt by default. Use `--yes` / `-y` to skip confirmation:
```bash
dku dataset delete DS -P PROJ --yes
dku recipe delete RECIPE -P PROJ --yes
dku project delete PROJ --yes
```

### Chaining Rule

**ALWAYS chain related commands with `&&` in ONE Bash call.** Each separate call = separate agent turn.

```bash
# GOOD — 1 call
dku dataset create raw --type UploadedFiles -P PROJ && \
dku dataset upload raw data.csv -P PROJ && \
dku recipe create-join enrich -i raw -i lookup --output-ds out --join-key id -P PROJ
```

> For complete templates, see `references/workflow-templates.md`.

## Investigation Workflow

```bash
# Step 1: Full project overview
dku project inspect PROJ -o json

# Step 2: Gauge data (ALWAYS before head)
dku dataset info SOURCE_DS -P PROJ

# Step 3: Sample data
dku dataset head SOURCE_DS -P PROJ -n 10
dku dataset schema SOURCE_DS -P PROJ
```

## Reference Files

| File | Read when... |
|---|---|
| `references/commands-list.md` | Quick command groups + verbs |
| `references/commands.md` | Exact flags for any `dku` command |
| `references/setup.md` | Auth, CI/CD, env vars |
| `references/workflow-templates.md` | Complete project templates |
| `references/recipe-decision.md` | Recipe decision tree + examples |
| `references/recipe-examples.md` | Detailed visual recipe code |
| `references/agent-patterns.md` | Agent + tool creation |
| `references/genai-recipes.md` | Embedding, RAG, KB, LLM |
| `references/prompt-recipe-payload.md` | Full payload schema for `dku recipe create -t prompt` |
| `references/prepare-steps.md` | Prepare steps with add-step |
| `references/dashboard-patterns.md` | Charts, dashboards |
| `references/sql-engines.md` | SQL landing, GREL push-down |

> Also use `dataiku` skill for platform knowledge (recipes, agents, plugins, formulas).
