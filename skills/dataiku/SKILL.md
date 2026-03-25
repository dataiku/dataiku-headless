---
name: dataiku
description: Dataiku DSS platform knowledge — plugin development, formulas, LLM Mesh, agents, webapps, scenarios, MLOps, Python API, and styling. Use when building FOR Dataiku (plugins, recipes, tools, webapps, guardrails, automations) or when understanding DSS platform concepts. For querying a live DSS instance via shell commands, use the `dku-cli` skill instead.
triggers:
  - dataiku plugin
  - dss plugin
  - dataiku webapp
  - dataiku recipe
  - agent tool
  - agent block
  - visual agent
  - guardrail
  - llm mesh
  - knowledge bank
  - dataiku scenario
  - dataiku formula
  - dataiku macro
  - dataset connector
  - dataiku styling
  - plugin review
globs:
  - "**/plugin.json"
  - "**/tool.json"
  - "**/recipe.json"
  - "**/guardrail.json"
  - "**/webapp.json"
  - "**/block.json"
metadata:
  author: dataiku
  version: "1.0.0"
  tags: dataiku, dss, plugins, genai, mlops, webapps, agents, recipes
---

# Dataiku Platform Reference

Comprehensive knowledge base for building Dataiku plugins, webapps, agents, and automations. Consult the routing table below, then read the relevant reference file(s).

> **Boundary**: This skill covers *development patterns* — plugin code, API usage, component design, platform concepts. For *live DSS operations* via shell commands (list projects, manage datasets, run jobs), use the `dku-cli` skill.

## Quick Router

### Plugin Development

| Topic | When to use | Reference |
|-------|-------------|-----------|
| **Plugin Structure** | Creating a new plugin, plugin.json anatomy, folder layout, packaging | `references/plugin-structure.md` |
| **Custom Recipes** | Building recipe components, input/output roles, dataset operations | `references/recipes.md` |
| **Agent Tools** | Building LLM agent tools, tool.json/tool.py, invoke() pattern, custom agents | `references/llm-tools.md` |
| **Webapps** | Interactive dashboards (Flask backend, Vue/React/Bokeh/Dash frontend) | `references/webapps.md` |
| **Webapp Pitfalls** | `Unexpected token '<'` errors, 404 routing, critical webapp mistakes | `references/webapp-pitfalls.md` |
| **Parameters** | Plugin parameter types (30+), STRING/SELECT/DATASET/COLUMN/PRESET, visibility conditions | `references/parameters.md` |
| **Dataset Connectors** | Building custom dataset connectors, read/write schema, HTTP patterns | `references/datasets.md` |
| **Macros / Runnables** | One-click utilities, result types (HTML/TABLE/FILE), macro roles | `references/macros.md` |
| **Code Environments** | Python dependency management, requirements.txt, desc.json, version pinning | `references/code-environments.md` |
| **Testing** | Unit tests (mocked), integration tests (DSS), E2E tests (Playwright), fixtures | `references/testing.md` |
| **Best Practices** | Separation of concerns, error handling, retry logic, performance, security | `references/best-practices.md` |
| **Plugin Workflow** | Git integration, semantic versioning, CI/CD, distribution, code quality | `references/plugin-workflow.md` |
| **Plugin Architecture** | Plugin tiers (1-5), patterns, anti-patterns, official docs comparison, agent-hub gold standard | `references/plugin-architecture.md` |
| **Visual Agent Blocks** | BlockHandler, block.json, dynamic_choices, dual-mode (block+tool), agent connectors (DSS 14.4+) | `references/visual-agent-blocks.md` |
| **Webapp Patterns** | Advanced: multi-tab dashboards, filter pipelines, caching, React+Vite SPA, Chart.js, SQLAlchemy | `references/webapp-patterns.md` |
| **Agent Tool Patterns** | Advanced: subprocess tools, MCP gateway, multi-agent orchestration, OAuth, HITL | `references/agent-tool-patterns.md` |
| **Plugin Review** | Reviewing plugins, code review criteria, scoring rubric | `references/plugin-review-checklist.md` |

### Platform Knowledge

| Topic | When to use | Reference |
|-------|-------------|-----------|
| **Formulas** | Formula language, computed columns, Prepare recipe expressions, `if()`, `strval()`, `forEach()` | `references/formulas.md` |
| **LLM Mesh** | GenAI apps, LLM connections, tools, guardrails, RAG, knowledge banks, LangChain integration | `references/llm-mesh.md` |
| **Structured Agents** | Deterministic blocks (DSS 14.4+), For Each loops, ReAct, HITL, state management | `references/structured-agents.md` |
| **Scenarios** | Automation, triggers, steps, reporters, metrics/checks, pipeline orchestration | `references/scenarios.md` |
| **MLOps** | Model training, evaluation, MLflow, saved models, API Node, deployment, drift detection | `references/mlops.md` |
| **Python API** | `dataiku.Dataset`, `dataikuapi`, read/write data, managed folders, SQL, code recipes | `references/python-api.md` |
| **GenAI Features** | LLM Mesh overview, Knowledge Banks, LLM recipes, agent architecture, use cases | `references/genai-features.md` |
| **DSS Quick Reference** | Key concepts (Projects, Flow, Recipes), common operations, API reference | `references/dataiku-reference.md` |
| **Styling** | Dataiku brand colors, typography, Tailwind config, UI components, design system | `references/styling.md` |

## Instructions

1. Identify which topic(s) the user's task involves
2. For new plugins, read `references/plugin-architecture.md` first to pick the right tier
3. Read the relevant reference file(s) — for cross-cutting tasks, read multiple
4. Apply the patterns and examples from the references
5. For webapps, always also check `references/webapp-pitfalls.md`
6. For dependency or compatibility issues, check `references/code-environments.md`
7. For visual agent blocks, also check `references/structured-agents.md` for graph patterns

## Cross-Cutting Patterns

Common task combinations that span multiple references:

- **"Build a Dataiku plugin"** -> `plugin-structure.md` + `code-environments.md` + `best-practices.md`
- **"Build a plugin webapp"** -> `plugin-architecture.md` (pick tier) + `webapps.md` + `webapp-pitfalls.md` + `styling.md`
- **"Build a production analytics dashboard"** -> `plugin-architecture.md` (Tier 3) + `webapp-patterns.md` + `webapp-pitfalls.md`
- **"Create a plugin with an LLM agent tool"** -> `plugin-architecture.md` (Tier 2) + `llm-tools.md` + `agent-tool-patterns.md`
- **"Build a subprocess agent tool"** -> `agent-tool-patterns.md` + `llm-tools.md`
- **"Build an MCP gateway or OAuth webapp"** -> `plugin-architecture.md` (Tier 4) + `agent-tool-patterns.md` + `webapp-patterns.md`
- **"Build a full-stack plugin with database"** -> `plugin-architecture.md` (Tier 4-5) + `webapp-patterns.md`
- **"Build visual agent blocks"** -> `visual-agent-blocks.md` + `plugin-architecture.md` (Tier 2b) + `structured-agents.md`
- **"Integrate external agent runtime"** -> `visual-agent-blocks.md` (agent connector section) + `llm-mesh.md`
- **"Build a structured agent"** -> `structured-agents.md` + `llm-mesh.md`
- **"Add a formula processor"** -> `formulas.md` + `recipes.md`
- **"Style a Dataiku dashboard"** -> `styling.md` + `webapps.md`
- **"Automate model retraining"** -> `scenarios.md` + `mlops.md`
- **"Read data and write to a folder"** -> `python-api.md`
- **"Deploy a model to production"** -> `mlops.md` + `scenarios.md`
- **"Test a plugin thoroughly"** -> `testing.md` + `best-practices.md`
- **"Set up a RAG pipeline"** -> `llm-mesh.md` + `genai-features.md`
- **"Build a scoring pipeline with checks"** -> `scenarios.md` + `python-api.md` + `mlops.md`
- **"Review a plugin"** -> `plugin-review-checklist.md` + `best-practices.md`
- **"Build a guardrail"** -> `llm-mesh.md` (guardrails section)
- **"Build a dataset connector"** -> `datasets.md` + `plugin-structure.md`
- **"Build a macro/runnable"** -> `macros.md` + `plugin-structure.md`
- **"Optimize plugin performance"** -> `best-practices.md` + `webapp-patterns.md` (if webapp)

## Additional References

If a topic is not covered by the reference files above, consult the official Dataiku documentation:

- **Developer docs**: https://developer.dataiku.com/
- **Product docs**: https://doc.dataiku.com/dss/latest/
- **Plugin docs**: https://developer.dataiku.com/latest/plugins/index.html
