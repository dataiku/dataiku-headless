---
name: dku-cli
description: Use the `dku` CLI to interact with Dataiku DSS from the terminal. Use when listing, inspecting, creating, updating, deleting, building, testing, or automating DSS projects, datasets, recipes, jobs, scenarios, folders, plugins, webapps, dashboards, agents, knowledge banks, LLMs, Govern objects, users, groups, connections, API services, code environments, and admin resources. Prefer this over direct Python API calls for shell-composable DSS operations.
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

# dku-cli

Use this skill for **how to execute** DSS operations with `dku`. Use the `dataiku` skill for **what DSS capability to choose**.

## Core Rules

1. Inspect before changing: `dku project inspect PROJ -o json` gives datasets, recipes, scenarios, flow, jobs, wiki, and variables in one call.
2. Use DSS-native operations first. For recipe selection, read `references/recipe-decision.md`.
3. Uploaded local files need `UploadedFiles`; managed recipe outputs are usually `Filesystem` or connection-backed datasets.
4. Gauge data before expensive reads or builds: `dku dataset info DS -P PROJ`; ask before large builds or LLM-heavy operations.
5. Sample and schema-check before transforming: `dku dataset head INPUT -P PROJ -n 5` and `dku dataset schema INPUT -P PROJ`.
6. Build with schema propagation when wiring a flow: `dku job run --target OUT -P PROJ --type RECURSIVE_BUILD --auto-update-schema --wait`.
7. Verify final outputs with real data checks; exit code 0 is not enough.
8. Use `&&` chains for related commands so setup, build, and verification stay atomic.
9. Put global flags before the noun: `dku --errors json recipe list`, not `dku recipe list --errors json`.
10. Respect guarded mode. On exit code 77, read the `AGENT INSTRUCTION` block and ask the user before re-running with confirmation.

## Canonical Command Flow

```bash
# 1. Inspect project shape
dku project inspect PROJ -o json

# 2. Gauge and sample inputs
dku dataset info INPUT -P PROJ && \
dku dataset schema INPUT -P PROJ && \
dku dataset head INPUT -P PROJ -n 5

# 3. Wire DSS-native operations
dku recipe create-join join_enriched -i INPUT -i LOOKUP \
  --output-ds ENRICHED --join-key id -P PROJ && \
dku recipe create-group summarize -i ENRICHED \
  --output-ds SUMMARY -k category --agg "amount:sum,avg" -P PROJ

# 4. Build and verify
dku job run --target SUMMARY -P PROJ \
  --type RECURSIVE_BUILD \
  --auto-update-schema \
  --wait && \
dku dataset head SUMMARY -P PROJ -n 5 && \
dku dataset info SUMMARY -P PROJ --recompute
```

Use this skeleton as the default shape; read `references/recipe-operations.md` for variants.

## Command Groups

| Group | Use for |
|---|---|
| `project` | Project lifecycle, metadata, variables, inspection |
| `dataset` | Dataset list/schema/info/head/create/upload/build/metadata |
| `recipe` | Recipe CRUD, visual recipe shortcuts, code, settings, Prepare steps |
| `job` | Builds, status, logs |
| `flow` | Graph, zones, consistency, schema propagation |
| `scenario` | Automation and scheduled runs |
| `folder` | Managed folders and FilesInFolder datasets |
| `knowledge` / `rag` | Knowledge Banks and retrieval |
| `llm` | LLM listing, completions, embeddings |
| `agent` / `agent-block` / `agent-tool` | Agents, versions, blocks, tools |
| `insight` / `dashboard` / `app-designer` | Charts, dashboards, apps |
| `plugin` / `library` / `webapp` | Plugin and project code assets |
| `ml` / `model` | Visual ML, saved models, scoring |
| `govern` | Govern blueprints, artifacts, signoffs, roles |
| `admin` / `user` / `group` / `connection` | Instance and identity operations |

Exact syntax belongs in `references/commands.md`.

## Reference Map

| Reference | Read when... |
|---|---|
| `references/commands.md` | You need the command reference entrypoint and global syntax rules |
| `references/commands-list.md` | You need a compact command-group index |
| `references/commands-core.md` | Auth, config, project, dataset, recipe, job, flow, and SQL commands |
| `references/commands-ai-apps.md` | LLM, ML, models, Knowledge Banks, agents, dashboards, webapps, and App Designer commands |
| `references/commands-admin-deploy.md` | Plugins, code envs, users/groups, connections, deployers, bundles, API services, admin, clusters, and keys |
| `references/commands-govern.md` | Govern command syntax |
| `references/setup.md` | Auth, profiles, CI/CD setup, environment variables |
| `references/recipe-decision.md` | Choosing visual recipe vs sync vs SQL vs Python |
| `references/recipe-operations.md` | Building, chaining, verification, and dataset upload workflows |
| `references/recipe-examples.md` | Detailed visual recipe examples |
| `references/common-gotchas.md` | Operational traps and recovery patterns |
| `references/safety.md` | Guarded mode, exit 77, destructive command confirmations |
| `references/admin-safety.md` | Admin writes, IAM lockout prevention, recovery |
| `references/sql-engines.md` | SQL landing, push-down, engine-specific behavior |
| `references/prepare-steps.md` | Prepare step commands and raw step JSON |
| `references/agent-patterns.md` | Agent creation, versions, tools, blocks |
| `references/genai-recipes.md` | Embedding, RAG, Knowledge Banks, GenAI recipes |
| `references/prompt-recipe-payload.md` | Prompt recipe payload schemas |
| `references/dashboard-patterns.md` | Charts, insights, dashboards |
| `references/flow-organization.md` | Zones, naming, project documentation |
| `references/workflow-templates.md` | Task-specific workflow templates after selecting the right operation reference |

## When To Use Python API Instead

Use `dku` for quick queries, CRUD, builds, shell scripts, and repeatable agent operations. Drop to `dataikuapi` only when no CLI verb exists and the workaround would be shorter and clearer than forcing the CLI. When you do, note the missing noun/verb so the CLI can be improved.

## Output And Error Handling

- Use `-o json` for scripting and pipe only stdout to `jq`; status messages go to stderr.
- Use `--errors json` before the noun for machine-readable failure handling.
- Treat empty JSON arrays as data, not necessarily success. Verify row counts and schemas when correctness matters.
- Do not paste raw connection, dataset, or webapp definitions into chat without redacting secrets.
