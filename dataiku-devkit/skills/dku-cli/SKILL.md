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
> 2. **Use `dku ml` for ML — not Python.** Full visual chain: `dku ml create-prediction` → `dku ml set-algorithm --disable-all --enable X` → `dku ml set-feature ... --role REJECT` (per non-spec column) → `dku ml train` → `dku ml deploy --train-dataset DS` → `dku recipe create-prediction-scoring` for the in-Flow scorer. Python recipes whose only output is `{status: ok, ml_task_id: …}` are an anti-pattern — recipes produce data, not bookkeeping. ML namespace is `dku ml` (NOT `dku analysis`); scoring lives in `dku recipe create-prediction-scoring`. Same chain applies to clustering / timeseries / causal.
> 3. **Visual recipes auto-apply schema.** `create-join`/`create-group`/etc. auto-propagate output schemas. For manual control: `dku recipe apply-schema RECIPE -P PROJ`, or `--auto-update-schema` on build.
> 4. **Upload = UploadedFiles.** `dku dataset create NAME --type UploadedFiles -P PROJ`. Never Filesystem for uploads.
> 5. **Code recipes need `--connection`** when project has no default managed connection. Visual recipe shortcuts auto-create outputs and apply schema.
> 6. **Investigate with `inspect`.** `dku project inspect PROJ -o json` returns datasets, recipes, scenarios, flow, jobs, wiki, variables in ONE call.
> 7. **Chain everything.** All related commands in ONE `&&`-chained Bash call. Never separate tool calls.
> 8. **Charts need `--dataset`.** `dku insight create NAME --type chart --dataset DS -P PROJ`. Validate with `dku insight validate ID -P PROJ`.
> 9. **Verify everything.** After building, ALWAYS `dku dataset head OUTPUT -P PROJ` to confirm real data exists. `dku dataset head OUTPUT -o json` returning `[]` means 0 rows, not success. Exit code 0 ≠ correct output. Also use the `dataiku` skill for platform knowledge — these two skills are a pair.
> 10. **Prefer purpose-built prepare processors over GREL.** Need to rename? `add-rename`. Parse dates? `DateParser`. Format dates (custom pattern)? `DateFormatter`. Truncate dates? `DateTruncate` (`datePart` param). Epoch→date? `UNIXTimestampParser` (`milliseconds` BOOLEAN, not `unit`). All date processors use `inCol`/`outCol` — **never** `column`/`outputColumn` (DSS errors with misleading "Empty column name"). GREL `toString(date,"fmt")` / `formatDate()` / `toDate()` don't work. Uppercase? `StringTransformer`. If/else? `VisualIfRule`. Use `add-formula` (GREL) ONLY when no processor exists. **READ `dataiku` skill's `references/prepare-processors.md` before any `add-step`.**
> 11. **Gauge before you grab.** Run `dku dataset info DS -P PROJ` BEFORE `head` or any build. If >1M rows or >1GB, ask the user before triggering builds or LLM recipes.
> 12. **Sample data before transforming.** Run `dku dataset head INPUT -P PROJ -n 5` and `dku dataset schema INPUT -P PROJ` to inspect actual column names, values, and formats. Don't guess date formats or column names — verify first. For joins, check both datasets have the join key.
> 13. **Document what you build.** `dku project set-metadata PROJ --description "..."`, `dku dataset set-column-description DS col1 "desc" -P PROJ`, at least one wiki article. Undocumented projects are incomplete projects.
> 14. **One multi-input join > cascading joins.** One `create-join -i A -i B -i C -i D` with index-prefixed keys, not A+B → temp → temp+C → out.
> 15. **Read reference files BEFORE exploring.** This skill has detailed reference docs in `references/`. Read the relevant file first — don't try to figure it out from `--help` alone.
> 16. **Cross-connection landing is a first-class feature.** `dku recipe create -t sync --connection X` moves data between connections. Never write a Python passthrough. See `references/sql-engines.md`.
> 17. **SVAs need STRUCTURED_AGENT.** `dku agent create NAME --type STRUCTURED_AGENT -P PROJ`. Every CORE_LOOP block needs `"llmId"`. Every SAVE_TO_STATE block needs `"outputKey"`. Never use `""` in SET_STATE_ENTRIES values (use `"''"` for empty CEL string). See `references/agent-patterns.md`.
> 18. **Guarded mode is default (exit 77).** Destructive commands (delete, clear, set-permissions, etc.) refuse to run without `--yes`. On exit code **77**, stderr contains an `AGENT INSTRUCTION:` block — read the verbatim question to ask the user and the exact re-run command. Tier-3 cascades (`project delete`, `plugin delete --force`, `git delete-branch --force`) also require `--confirm-name <target>` matching the resource. Never guess; ask the user first.
> 19. **`@file` silently uses leftover content.** If your prior Write was rejected ("File has not been read yet"), Bash still runs and `dku <cmd> --body @file` reads whatever was on disk — often stale content from a previous session. Either Read first so Write accepts the overwrite, or use a per-session path like `/tmp/dku_${RANDOM}_X.md`. Applies to every `--body @`, `--code @`, `--content @`, `--definition @`, `--payload @`, `--params @` flag.
> 20. **`dku admin` writes can lock users out.** `license upload`, `sso/ldap/azure-ad set`, `settings set`, `infra push-base-images`, `users-sync resync-all`, `messaging create` all dry-run without `--yes`. IAM `set` also requires `--i-understand-lockout-risk`. ALWAYS `get` → edit → `set` (never hand-write IAM payloads). See `references/admin-safety.md`.
> 19. **Profile node type matters.** `dku` refuses project-scoped commands on a GOVERN profile with exit **4** and a hint to use `dku govern …`. Govern nodes have no projects, datasets, or recipes — only blueprints, artifacts, signoffs, and roles. Check `dku whoami` (shows `[GOVERN]` / `[DESIGN]` / …) before running a command that targets the wrong node type. If an older profile shows `[?]` in `dku auth list`, re-run `dku auth login --profile X` to refresh it.
> 20. **Global flags go BEFORE the subcommand.** `--errors json`, `--profile`, `--dangerous`, `--url`, `--api-key` are options on the root `dku` app. Pass them before the noun: `dku --errors json user delete X` ✓, NOT `dku user delete X --errors json` ✗.
> 22. **Agent prompt/LLM/tool changes default to in-place — pass `--new-version --activate` for reversibility.** `dku agent set-prompt AGENT --prompt @sys.txt --new-version --activate -P PROJ` publishes a new version and flips active so you can roll back with `dku agent set-active-version AGENT v1 -P PROJ`. Same flags work on `set-llm` and `add-tool`. `dku agent list-versions AGENT -P PROJ` shows history. Without the flags the active version is mutated in place — lossy and not what you want for prompt iteration.
> 21. **Semantic models: use splice verbs for everything.** `add-entity --from-dataset DS` auto-maps columns to attributes. `add-relationship --from A --to B --on COL` builds join predicate. `add-metric` / `add-filter` for pseudoSQL aggregates and predicates. `set-manual-values --values "Low,Medium,High"` flips an attribute to curated enum + enables fuzzy resolution. `add-golden-query` for NL→SQL few-shot examples (biggest quality lever). Never hand-write entity/relationship JSON — schema isn't in `dataikuapi`. `set-version` is a **shallow merge** — use splice verbs instead. See `dataiku` skill's `references/semantic-models.md`.

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
| `--dangerous` | `DKU_DANGEROUS` | Skip safety guards (tiers 2–3). Not for agent use unless user explicitly asks. |

**Global options MUST come BEFORE the subcommand:** `dku --profile X whoami`, NOT `dku whoami --profile X`. This is a Click/Typer limitation — the root parser only sees options placed before the subcommand name.

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
| SQL-engine push-down / cross-connection landing | See `references/sql-engines.md` for sync+connection, GREL→SQL compilation gotchas, and stale-table recovery |
| Date processor returns "Empty column name" | Wrong param names. `DateFormatter`/`DateTruncate`/`UNIXTimestampParser` use `inCol`/`outCol`, NOT `column`/`outputColumn`. The `dku recipe add-step` CLI catches this and points to the fix. |
| Agent loops formatting dates with GREL | GREL `toString(date,"fmt")`/`formatDate()`/`toDate()` don't work. Use the `DateFormatter` processor (`inCol`/`outCol`/`format`). For epoch → date use `UNIXTimestampParser` (`milliseconds` BOOLEAN). For timestamp → date-only use `DateParser` with `outType: dateonly` + `outCol` (in-place = all nulls). |
| SQL query recipe: agent references wrong table name | In SQL recipes, use the actual database table name (e.g., `"PUBLIC"."PROJKEY_DATASET_NAME"`), not DSS dataset names. Check with `dku connection tables CONN -P PROJ` |

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

`dku dataset list -P PROJ` includes both local AND foreign/shared datasets by default — the `PROJECT` column shows the source. A row whose `PROJECT` differs from `-P` is a foreign dataset shared into this project. Reference foreign datasets in recipes as `PROJECT_KEY.DATASET_NAME`:

```bash
dku dataset list -P PRICING_ANALYTICS -o json | jq '.[] | select(.projectKey != "PRICING_ANALYTICS")'

dku recipe create compute_metrics -t python \
  -i EDP_GOLD_DATASETS.account_base \
  --output-ds account_metrics \
  --connection filesystem_managed \
  -P PROJ
```

Pass `--own-only` to `dku dataset list` to see only datasets owned by the project. This cross-project reference works in recipe inputs even when `dku dataset head PROJECT_KEY.DATASET_NAME` does not.

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

| Group | Key Verbs |
|---|---|
| `project` | list, inspect, create |
| `dataset` | list, schema, info, head, create, upload, build |
| `recipe` | list, get-definition, run, create, delete, create-join, create-group, create-stack |
| `job` | run, status, log |
| `scenario` | list, run, status, runs |
| `agent` | list, create, add-tool, set-llm, set-prompt, **list-versions**, **create-version**, **set-active-version** (mutators take `--new-version --activate`) |
| `knowledge` | list, create, build, search |
| `webapp` | list, create, start, stop, status, get-definition, set-definition |
| `insight` | list, create, validate |
| `llm` | list, completion, embeddings |
| `app-designer` | enable, set-section, add-tile, list-tiles, get |
| `app` | list, get, list-instances, create-instance |
| `admin` | logs, usage, instance-info, sanity-check, **license**, **sso**, **ldap**, **azure-ad**, **settings**, **users-sync**, **messaging** (list/create/delete/send-test), **infra**, **code-studio-template**, **llm-cost**, **disk-footprint** (global/project/all/unknown), **catalog-index** (--all/--connections), **assets** (list-collections/list-prompts), **audit-log** — writes require `--yes`; IAM writes also need `--i-understand-lockout-risk`. See `references/admin-safety.md`. |
| `code-env` (rebuild) | `jupyter ENV --enable/--disable`, `update ENV --force-rebuild --version X`, `update-images ENV` — all non-destructive; safe to re-run. |
| `user` (bulk) | `bulk-create --from @users.json` / `--from-csv @users.csv`, `bulk-edit --from @changes.json` — all require `--yes`. CSV groups separator is `;`. |
| `connection` (admin) | `update --params '{...}' --yes` (credential rotation), `set-definition -d @conn.json --yes` (full replace). Always `connection test CONN -P PROJ` after. |
| `api-key` (personal) | `list-personal` for admin audit of every user's personal keys before rotation/offboarding. |
| `govern` (GOVERN nodes only) | `instance-info`, `blueprint list/get/versions`, `artifact list/get/create/delete`, `signoff list/get/update-status/add-feedback/add-approval`, `role list/assignments`, `custom-page list`, `log list/get/custom-audit`, `uploaded-file upload/download/delete` |

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

### Deletion Commands (Safety Guards — exit 77)

**Guarded mode is default.** Destructive commands refuse to run without `--yes` and exit with code **77** + an `AGENT INSTRUCTION:` block on stderr. Read it, ask the user verbatim, then re-run.

| Tier | Examples | Required flags |
|---|---|---|
| 2 (delete) | `agent delete`, `agent-block remove`, `agent-hub remove-agent`, `agent-review delete`, `agent-tool delete`, `analysis delete`, `api-deployer delete-deployment`, `api-key delete`, `api-service delete-package`, `cluster delete`, `code-env delete`, `code-studio delete`, `dashboard delete`, `dataset clear`, `dataset delete`, `dq delete`, `evaluation-store delete`, `folder delete`, `folder delete-file`, `folder delete-files`, `git delete-branch`, `group delete`, `insight delete`, `knowledge delete`, `library delete`, `ml delete`, `model delete`, `model delete-version`, `model-comparison delete`, `model-comparison remove-model`, `notebook delete`, `notebook clear-outputs`, `plugin delete` (no `--force`), `project-deployer delete-deployment`, `project set-permissions`, `project set-variables`, `rag delete`, `recipe delete`, `recipe remove-step`, `scenario delete`, `scenario remove-trigger`, `semantic-model delete`, `streaming delete`, `user delete`, `wiki delete`, `workspace delete` | `--yes` |
| 2 (delete, govern) | `govern artifact delete`, `govern uploaded-file delete` | `--yes` |
| 3 (cascade) | `connection delete`, `project delete`, `plugin delete --force`, `git delete-branch --force` | `--yes` AND `--confirm-name <TARGET>` |
| 4 (admin) | — (reserved) | `--yes` + `--confirm-name` + `--i-know-what-im-doing`. Never bypassable. |

```bash
# Tier 2
dku dataset delete DS -P PROJ --yes
dku recipe delete RECIPE -P PROJ --yes
dku knowledge delete KB -P PROJ --yes
dku ml delete ANALYSIS MLTASK -P PROJ --yes

# Tier 3 — --confirm-name must match the target identifier
dku project delete MYPROJ --yes --confirm-name MYPROJ
dku plugin delete my-plugin --force --yes --confirm-name my-plugin

# Session-wide bypass (only if user explicitly authorises it)
export DKU_DANGEROUS=1
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
| `references/admin-safety.md` | Destructive `dku admin` ops, IAM lockout prevention, recovery |
| `references/govern.md` | `dku govern` commands — blueprints, artifacts, signoffs, roles |

> Also use `dataiku` skill for platform knowledge (recipes, agents, plugins, formulas).
