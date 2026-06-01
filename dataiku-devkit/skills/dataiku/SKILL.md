---
name: dataiku
description: Dataiku DSS platform knowledge for choosing the right built-in capability and designing plugins, recipes, agents, webapps, Govern assets, LLM Mesh flows, scenarios, MLOps workflows, formulas, and dashboards. Use when building for Dataiku or reasoning about DSS concepts. For live DSS operations through shell commands, use the `dku-cli` skill.
triggers:
  - dataiku plugin
  - dss plugin
  - dataiku webapp
  - dataiku recipe
  - dataiku formula
  - prepare recipe
  - visual recipe
  - agent tool
  - visual agent
  - structured visual agent
  - SVA
  - llm mesh
  - knowledge bank
  - guardrail
  - dataiku scenario
  - semantic model
  - text-to-sql
  - dataiku govern
  - dataiku app designer
  - mlops
globs:
  - "**/plugin.json"
  - "**/recipe.json"
  - "**/tool.json"
  - "**/guardrail.json"
  - "**/webapp.json"
  - "**/block.json"
metadata:
  author: dataiku
  version: "1.0.0"
  tags: dataiku, dss, plugins, genai, mlops, webapps, agents, recipes
---

# Dataiku Platform Router

Use this skill to decide **what DSS capability to use** and which platform reference to read. Use `dku-cli` for **how to execute** the decision against a live DSS instance.

## Operating Principles

1. Prefer DSS-native features over custom code: visual recipes, GenAI recipes, AutoML, Knowledge Banks, agents, scenarios, and dashboards.
2. Use Python only when the built-in recipe or platform feature cannot express the logic cleanly.
3. Prefer purpose-built Prepare processors over raw GREL when a processor exists.
4. Verify outcomes through `dku-cli`; a successful API call does not prove the artifact is correct.
5. Keep platform design separate from command syntax. This skill routes to DSS concepts; `../dku-cli/references/commands.md` owns command flags.

## Boundary With `dku-cli`

| Need | Use |
|---|---|
| Choose between visual recipe, SQL, Python, AutoML, agent, KB, or scenario | `dataiku` |
| Create/list/update/build/test DSS objects from shell | `dku-cli` |
| Understand plugin structure, payload JSON, processor schemas, DSS behavior | `dataiku` |
| Find exact command flags, chaining, safety, or CLI gotchas | `dku-cli` |

## Task Router

| Task | Read |
|---|---|
| Plugin architecture or folder structure | `references/plugin-architecture.md`, `references/plugin-structure.md`, `references/plugin-production-patterns.md` |
| Plugin lifecycle and production quality | `references/plugin-workflow.md`, `references/best-practices.md`, `references/plugin-production-patterns.md` |
| Scaffold plugin components | `references/scaffolding.md` |
| Custom recipes | `references/recipes.md` |
| Agent tools | `references/llm-tools.md`, `references/agent-tool-patterns.md` |
| Webapps | `references/webapps.md`, `references/webapp-backends.md`, `references/webapp-frontends.md`, `references/webapp-local-dev-deploy.md`, `references/webapp-patterns.md`, `references/webapp-pitfalls.md` |
| Parameters and forms | `references/parameters.md`, `references/parameters-types.md`, `references/parameters-dynamic.md`, `references/parameters-access.md` |
| Dataset connectors | `references/datasets.md` |
| Share datasets/folders/models/KBs across projects | `references/cross-project-sharing.md` |
| Macros and runnables | `references/macros.md` |
| Code environments | `references/code-environments.md` |
| Plugin tests and review | `references/testing.md`, `references/plugin-review-checklist.md` |
| Prepare processor overview | `references/prepare-processors.md` (selection guide + catalog), then open per-processor ref from `references/processors/<Processor>.md` |
| GREL formulas | `references/formulas.md` |
| Visual recipe payloads | `references/visual-recipe-payloads.md`, `references/visual-conditions.md` |
| LLM Mesh and Knowledge Banks | `references/llm-mesh.md` |
| Structured Visual Agents | `references/structured-agents.md`, `references/visual-agent-blocks.md` |
| Guardrails | `references/guardrails.md` |
| Scenarios | `references/scenarios.md` |
| Data Quality rules | `references/data-quality-rules.md` | 10 rule families: record-count, size, numeric-range, emptiness, uniqueness, allowed-values, top-mode, meaning, schema, metric-compare |
| MLOps | `references/mlops.md` |
| Python API usage | `references/python-api.md` |
| Dashboard and charts | `references/dashboard-charts.md` |
| App Designer | `references/app-designer.md` |
| Semantic models / text-to-SQL | `references/semantic-models.md` |
| Govern runtime/admin | `references/govern.md` |
| Govern blueprint authoring | `references/govern-blueprint-designer.md`, `references/govern-field-types.md`, `references/govern-workflow-and-signoffs.md`, `references/govern-ui-views.md` |
| Govern custom pages | `references/govern-custom-pages.md` |
| Geospatial | `references/geospatial.md` |
| Verification patterns | `references/verification.md` |

## Capability Selection

| User intent | Default DSS capability |
|---|---|
| Join, group, filter, sort, stack, distinct, window, top N, pivot | Visual recipe |
| Rename, parse dates, format dates, fill, split, normalize strings | Prepare recipe processor |
| Classification, regression, clustering, forecasting | Visual ML / `dku ml` |
| RAG over documents | Knowledge Bank + embed recipe |
| LLM transformation over rows | GenAI recipe |
| Conversational tool use | Visual agent |
| Deterministic multi-step agent flow | Structured Visual Agent |
| Scheduled or conditional rebuild | Scenario |
| Reusable packaged capability | Plugin |
| Instance governance workflow | Govern |

## Workflow

1. Identify the DSS capability family from the task.
2. Read the narrow reference file listed above.
3. Use `dku-cli` to inspect existing objects and execute changes.
4. Verify the artifact using the verification reference or the relevant `dku-cli` workflow.

## Reference Ownership

Platform references own DSS behavior, payload shapes, schemas, and design patterns. CLI references own exact commands, flags, guarded mode, shell chaining, and operational gotchas. If a detail is both a DSS behavior and a CLI recovery pattern, keep the full explanation in one reference and link to it from the other.
