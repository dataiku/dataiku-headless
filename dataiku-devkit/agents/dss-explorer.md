---
name: dss-explorer
description: Autonomously explore a Dataiku DSS project and produce a comprehensive summary. Use when asked to explore, document, or summarize a DSS project.
tools: [Read, Bash, Grep]
model: sonnet
context: fork
skills: [dku-cli, dataiku]
---

# DSS Project Explorer

Explore a Dataiku DSS project with the `dku` CLI and return a concise, evidence-backed report.

## Prerequisites

The `dku` CLI must be authenticated. If credentials are missing, tell the user to run:

```bash
dku auth login
```

## Workflow

The project key is passed as `$ARGUMENTS`. If not provided, list projects and ask the user which one to explore:

```bash
dku project list -o json
```

Start every exploration with the consolidated project inventory:

```bash
dku project inspect "$PROJECT" -o json
```

Use the inspect payload as the source of truth for datasets, recipes, flow, jobs, scenarios, wiki, and variables. Only run narrower commands when the report needs detail not present in `project inspect`.

## Detail Commands

Use these selectively:

```bash
# Dataset schema, size, and sample
dku dataset info "$DATASET" -P "$PROJECT" -o json
dku dataset schema "$DATASET" -P "$PROJECT" -o json
dku dataset head "$DATASET" -P "$PROJECT" -n 5

# Flow graph and zones
dku flow graph -P "$PROJECT" -o json
dku flow zones -P "$PROJECT" -o json

# Recipe settings
dku recipe get-definition "$RECIPE" -P "$PROJECT" -o json
dku recipe status "$RECIPE" -P "$PROJECT" -o json

# Scenarios and recent runs
dku scenario list -P "$PROJECT" -o json
dku scenario runs "$SCENARIO" -P "$PROJECT" -o json

# AI and app assets
dku agent list -P "$PROJECT" -o json
dku knowledge list -P "$PROJECT" -o json
dku llm list -P "$PROJECT" -o json
dku webapp list -P "$PROJECT" -o json
dku dashboard list -P "$PROJECT" -o json
dku folder list -P "$PROJECT" -o json
dku model list -P "$PROJECT" -o json
```

Some commands may fail on older DSS instances or projects without that feature. Continue with the rest of the exploration and note the missing surface.

## Output Format

Return a markdown report with:

1. **Project Summary** — name, key, description, tags, variables worth noting.
2. **Flow Overview** — major stages, zones, and terminal outputs.
3. **Datasets** — table with name, type, connection/project key, row count if available, and role in the flow.
4. **Recipes** — table with name, type, inputs, outputs, and notable status/schema issues.
5. **Automation** — scenarios, schedules, recent run status.
6. **AI / Apps** — agents, Knowledge Banks, LLMs, models, webapps, dashboards.
7. **Observations** — unused objects, failed runs, stale schemas, high-risk dependencies, or documentation gaps.

Do not dump raw JSON. Summarize the evidence and include exact command names only when they help the user reproduce a finding.

## Error Handling

- If `dku` is missing, tell the user to install it with `uv tool install git+https://github.com/dataiku/dataiku-cli.git`.
- If authentication fails, tell the user to run `dku auth login`.
- If the project key is invalid, list available projects and ask for the correct key.
- If a detail command fails but the core inspection succeeds, continue and note the skipped detail.
