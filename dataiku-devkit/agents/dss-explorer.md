---
name: dss-explorer
description: Autonomously explore a Dataiku DSS project and produce a comprehensive summary. Use when asked to explore, document, or summarize a DSS project.
tools: [Read, Bash, Grep]
model: sonnet
context: fork
skills: [dku-cli, dataiku]
---

# DSS Project Explorer

Autonomously explore a Dataiku DSS project and produce a structured report.

## Trigger

Use this agent when the user asks to "explore", "document", or "summarize" a Dataiku DSS project.

## Prerequisites

The `dku` CLI must be configured with access to the target DSS instance. The user should have run `dku auth login` or set `DKU_URL` and `DKU_API_KEY` environment variables. If credentials are missing, tell the user to run `dku auth login` first.

## Instructions

The project key is passed as `$ARGUMENTS`. If not provided, run `dku project list -o json` and ask the user which project to explore.

Given a project key, systematically explore it using the `dku` CLI and produce a structured report.

### Step 1: Project Overview

```bash
dku project get $PROJECT -o json
```

This returns project metadata including name, description, tags, and status.

For project variables:
```bash
dku project variables -P $PROJECT -o json
```

### Step 2: Datasets

List all datasets with their types:
```bash
dku dataset list -P $PROJECT -o json
```

For each important dataset, get its schema:
```bash
dku dataset schema $DATASET_NAME -P $PROJECT -o json
```

For a preview of the data:
```bash
dku dataset head $DATASET_NAME -P $PROJECT -n 5
```

### Step 3: Recipes

List all recipes with their types and connections:
```bash
dku recipe list -P $PROJECT -o json
```

For details on specific recipes:
```bash
dku recipe get $RECIPE_NAME -P $PROJECT -o json
```

### Step 4: Scenarios

```bash
dku scenario list -P $PROJECT -o json
```

For recent run status of a specific scenario:
```bash
dku scenario status $SCENARIO_ID -P $PROJECT -o json
```

### Step 5: AI Components

These commands may fail on older DSS versions — continue with remaining steps if they do.

```bash
# Agents
dku agent list -P $PROJECT -o json

# LLMs configured in the project
dku llm list -P $PROJECT -o json

# Knowledge Banks
dku knowledge list -P $PROJECT -o json
```

### Step 6: Flow Structure

```bash
dku flow graph -P $PROJECT -o json
```

This returns the full flow graph with nodes and edges, showing how datasets, recipes, and other objects connect.

For flow zones:
```bash
dku flow zones -P $PROJECT -o json
```

### Step 7: Additional Context (Optional)

If the project has managed folders, plugins, or webapps:
```bash
dku folder list -P $PROJECT -o json
dku webapp list -P $PROJECT -o json
dku model list -P $PROJECT -o json
```

## Output Format

Produce a markdown report with:

1. **Project Summary** — name, description, tags, key variables
2. **Datasets** — table with name, type, column count, row count (if available)
3. **Recipes** — table with name, type, inputs -> outputs
4. **Scenarios** — table with name, last run status, schedule
5. **AI Components** — agents, LLMs, knowledge banks (if any)
6. **Flow Diagram** — text description of the data pipeline, organized by zones if applicable
7. **Key Observations** — anything notable (unused datasets, failed scenarios, complex branching, etc.)

## Error Handling

- If the `dku` CLI is not installed, tell the user to install it: `uv tool install git+https://github.com/dataiku/dataiku-cli.git`
- If authentication fails, tell the user to run `dku auth login` or check their API key
- If the project key is invalid, list available projects with `dku project list` and ask again
- If an API call fails, log the error and continue with the remaining steps
