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
  - structured visual agent
  - SVA
  - block graph
  - blocks graph
  - code agent
  - python agent
  - build agent
  - create agent
  - agent type
  - guardrail
  - llm mesh
  - knowledge bank
  - dataiku scenario
  - dataiku formula
  - dataiku macro
  - dataset connector
  - dataiku styling
  - plugin review
  - new plugin
  - scaffold plugin
  - create plugin
  - add tool
  - add recipe
  - add webapp
  - add guardrail
  - deploy plugin
  - push plugin
  - review plugin
  - mlops
  - model deployment
  - model scoring
  - model retraining
  - scoring pipeline
  - prepare recipe
  - computed column
  - dataiku formula
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

---

## Why Visual Matters — Dataiku's Core Value

Dataiku exists to **democratize data science and AI**. Its power is that business analysts, data engineers, and data scientists all work in the same visual environment — no code required for most tasks. Every decision you make should reinforce this principle:

**Always prefer visual over code. Always prefer configurable over hardcoded. Always prefer the platform over custom scripts.**

When building agents, recipes, or workflows in DSS, the question is never "can I write code for this?" — it's "can the platform do this visually?" If yes, use the visual approach. It's more maintainable, more accessible to the wider team, auditable, and benefits from DSS's built-in governance, versioning, and monitoring.

Code is the escape hatch, not the default.

---

## Agent Type Selection — Visual Agent > SVA > Code Agent

When building agents in Dataiku, **always start with the simplest agent type that meets the requirements.** Escalate only when the simpler type genuinely can't do the job.

### Priority Order

```
1. VISUAL AGENT (TOOLS_USING_AGENT, mode: SIMPLE)
   └─ Default choice. LLM + tools. Handles 80% of use cases.

2. STRUCTURED VISUAL AGENT (TOOLS_USING_AGENT, mode: BLOCKS_GRAPH)
   └─ When you need deterministic control flow on top of agentic reasoning.

3. CODE AGENT (PYTHON_AGENT)
   └─ Last resort. Only when the platform can't express your logic.
```

### When to Use Each

| Agent Type | Use When | Examples |
|------------|----------|---------|
| **Visual Agent** | Single-turn Q&A, conversational, LLM decides tool order, simple RAG, exploratory tasks | Customer support chatbot, document Q&A, data exploration assistant |
| **SVA** | Multi-step pipeline, guaranteed item processing, conditional branching, parallel data gathering, compliance/audit workflows, report generation | Regulatory impact analysis, document processing pipeline, multi-source data enrichment, approval workflows |
| **Code Agent** | Custom LLM orchestration (LangGraph, CrewAI), external agent runtimes, logic that truly can't be expressed visually | Custom multi-agent systems, non-standard inference loops, integration with external agent frameworks |

### Decision Framework

```
Can the LLM just pick tools and answer?
  └─ YES → Visual Agent (SIMPLE mode)

Do you need ANY of these?
  • Guaranteed processing of every item in a list
  • Conditional branching based on data (not LLM judgment)
  • Parallel execution of independent tasks
  • Document/report generation at the end
  • Deterministic tool calls (known args, guaranteed execution)
  • Audit trail with explicit block-by-block state
  └─ YES → SVA (BLOCKS_GRAPH mode)

Does the workflow require custom Python orchestration
that can't be expressed as blocks?
  └─ YES → Code Agent (PYTHON_AGENT)
```

### Why SVAs Are Powerful

SVAs combine the best of both worlds — **deterministic system design** with **agentic intelligence**:

- **Deterministic blocks** (ROUTING, MANUAL_TOOL_CALL, FOR_EACH, PARALLEL) guarantee execution order, data flow, and coverage
- **Agentic blocks** (STANDARD_REACT, LLM_REQUEST, MANDATORY_TOOL_CALL) bring LLM reasoning where it's needed — query formulation, analysis, summarization
- **The graph is the contract** — every step is visible, auditable, and modifiable without touching code
- **Event-based flow** — blocks trigger based on data conditions (CEL expressions), not LLM whims

A well-designed SVA is a deterministic pipeline with intelligence injected at specific points, not an unconstrained LLM that might skip steps.

### Why NOT Code Agents

Code agents (`PYTHON_AGENT`) are powerful but come with costs:

- **Not visual** — other team members can't understand or modify the workflow without reading Python
- **Not governed** — DSS can't enforce guardrails, audit steps, or manage state at the block level
- **Not composable** — can't drag-and-drop new blocks or rewire connections in the UI
- **Not reusable** — custom orchestration code is harder to share across projects

Use code agents ONLY when you need a framework like LangGraph or CrewAI, or when the block types genuinely can't express your logic. If you're tempted to write a code agent "because it's easier" — reconsider. The SVA may take more upfront design but pays off in maintainability, governance, and team accessibility.

> **Design guide:** See `references/structured-agents.md` for the complete SVA design guide — all 13 block types, when/why, graph patterns, state management, and CLI workflow.

---

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
| **Scaffolding & Lifecycle** | Creating new plugins, adding components (tool/recipe/webapp/guardrail), deploying, reviewing | `references/scaffolding.md` |
| **Guardrails** | Building plugin guardrails, BaseGuardrail, blocking vs filtering, PII detection, LLM judge, trace API | `references/guardrails.md` |
| **Dashboard & Charts** | Chart JSON anatomy, insight definitions, dashboard tiles, chart types, end-to-end examples | `references/dashboard-charts.md` |

### Platform Knowledge

| Topic | When to use | Reference |
|-------|-------------|-----------|
| **Formulas** | Formula language, computed columns, Prepare recipe expressions, `if()`, `strval()`, `forEach()` | `references/formulas.md` |
| **LLM Mesh** | GenAI apps, LLM connections, tools, guardrails, RAG, knowledge banks, LangChain integration | `references/llm-mesh.md` |
| **Structured Visual Agents** | SVA design guide: all 13 block types (when/why), graph patterns, state management, CLI workflow | `references/structured-agents.md` |
| **Scenarios** | Automation, triggers, steps, reporters, metrics/checks, pipeline orchestration | `references/scenarios.md` |
| **MLOps** | Model training, evaluation, MLflow, saved models, API Node, deployment, drift detection | `references/mlops.md` |
| **Python API** | `dataiku.Dataset`, `dataikuapi`, read/write data, managed folders, SQL, code recipes | `references/python-api.md` |
| **Styling** | Dataiku brand colors, typography, Tailwind config, UI components, design system | `references/styling.md` |
| **Geospatial** | Geo data types (geopoint/geometry), geo join recipe, fuzzy join, prepare processors, GREL geo formulas | `references/geospatial.md` |

## Instructions

1. Identify which topic(s) the user's task involves
2. For scaffolding tasks (new plugin, add component, deploy, review), read `references/scaffolding.md`
3. For new plugins, read `references/plugin-architecture.md` first to pick the right tier
4. Read the relevant reference file(s) — for cross-cutting tasks, read multiple
5. Apply the patterns and examples from the references
6. For webapps, always also check `references/webapp-pitfalls.md`
7. For dependency or compatibility issues, check `references/code-environments.md`
8. For structured visual agents (SVAs), read `references/structured-agents.md` for design patterns, block selection, and JSON schemas
9. **When unsure about a pattern**, check the "Official Plugin Repos" section in `references/plugin-architecture.md` — it lists 40+ public repos at `github.com/dataiku` organized by component type. Browse the closest match to see real production code.

## Cross-Cutting Patterns

Common task combinations that span multiple references:

- **"Scaffold a new plugin"** -> `scaffolding.md` (Section 1) + `plugin-structure.md` + `code-environments.md`
- **"Add an agent tool to a plugin"** -> `scaffolding.md` (Section 2.1) + `llm-tools.md`
- **"Add a recipe to a plugin"** -> `scaffolding.md` (Section 2.2) + `recipes.md`
- **"Add a webapp to a plugin"** -> `scaffolding.md` (Section 2.3) + `webapps.md` + `webapp-pitfalls.md`
- **"Add a guardrail to a plugin"** -> `scaffolding.md` (Section 2.4) + `guardrails.md`
- **"Deploy a plugin to DSS"** -> `scaffolding.md` (Section 3)
- **"Review a plugin"** -> `scaffolding.md` (Section 4) + `plugin-review-checklist.md`, or spawn `plugin-reviewer` agent
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
- **"Build an agent" / "What type of agent?"** -> Read Agent Type Selection section above first, then `structured-agents.md` (SVA) or `llm-mesh.md` (Visual) or `python-api.md` (Code)
- **"Add a formula processor"** -> `formulas.md` + `recipes.md`
- **"Style a Dataiku dashboard"** -> `styling.md` + `webapps.md`
- **"Automate model retraining"** -> `scenarios.md` + `mlops.md`
- **"Read data and write to a folder"** -> `python-api.md`
- **"Deploy a model to production"** -> `mlops.md` + `scenarios.md`
- **"Test a plugin thoroughly"** -> `testing.md` + `best-practices.md`
- **"Set up a RAG pipeline"** -> `llm-mesh.md`
- **"Build a scoring pipeline with checks"** -> `scenarios.md` + `python-api.md` + `mlops.md`
- **"Build a guardrail"** -> `guardrails.md` + `scaffolding.md` (Section 2.4)
- **"Build a dataset connector"** -> `datasets.md` + `plugin-structure.md`
- **"Build a macro/runnable"** -> `macros.md` + `plugin-structure.md`
- **"Optimize plugin performance"** -> `best-practices.md` + `webapp-patterns.md` (if webapp)

## Additional References

If a topic is not covered by the reference files above, consult the official Dataiku documentation:

- **Developer docs**: https://developer.dataiku.com/
- **Product docs**: https://doc.dataiku.com/dss/latest/
- **Plugin docs**: https://developer.dataiku.com/latest/plugins/index.html
