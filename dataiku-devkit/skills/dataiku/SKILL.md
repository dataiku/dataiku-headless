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

Comprehensive knowledge for building Dataiku plugins, webapps, agents, and automations.

> **Cheat Sheet (read this first)**
>
> 1. **Visual recipe > Python recipe.** Join, group, stack, filter, window, topN — use visual. Python ONLY for custom logic.
> 2. **Purpose-built processor > GREL.** Rename → `add-rename`, dates → `DateParser`, uppercase → `StringTransformer` (`mode: TO_UPPER`, not `UPPERCASE`). Full processor catalog in `references/prepare-processors.md`.
> 3. **Verify everything.** `dku dataset head OUTPUT -P PROJ -n 5`. Exit code 0 ≠ correct data. See `references/verification.md` for per-artifact verification (agents, KB, charts, scenarios) and cost risk table.
> 4. **Gauge before you grab.** `dku dataset info DS -P PROJ` BEFORE `head`. If >1M rows or >1GB, ask before building. Never trigger `RECURSIVE_BUILD` on Spark/BigQuery/Snowflake without asking.
> 5. **Join prefixing.** Join recipes prefix columns (customers_name, orders_amount). Plan downstream refs.
> 6. **LEFT join for enrichment.** Default is INNER. For lookups, use LEFT to keep source rows.
> 7. **Code env on Python 3.11:** Use `installCorePackages: false` + explicit `requirements.txt`. NOT `true`.
> 8. **Webapp backend ≠ Flask.** Import from `dataiku.customwebapp`, NOT `flask`. Folder is `webapps/`, not `custom-webapps/`.
> 9. **GREL log() = base-10.** No `ln()`, `exp()` is base-e. Formula cols default to STRING — run `apply-schema`.
> 10. **Agent tool input at input.get().** NOT root. Trace at `trace.attributes` NOT `set_attribute`.

> **Boundary:** This skill covers *development patterns*. For *live operations* via CLI (list, create, build), use `dku-cli`.

---

## Companion Skill: `dku-cli`

**This skill and `dku-cli` are a pair. Always use both.**

- **This skill** tells you *what* to build and *how* DSS works
- **`dku-cli`** tells you *how to execute* — create, configure, build, verify

**Typical workflow:**
1. Read this skill to understand the right DSS approach
2. Use `dku-cli` commands to create and verify
3. Verify every outcome — see cheat sheet rule #3

---

## Agent Type Selection

```
1. VISUAL AGENT (TOOLS_USING_AGENT, mode: SIMPLE)
   └─ Default. LLM + tools. 80% of use cases.

2. STRUCTURED VISUAL AGENT (TOOLS_USING_AGENT, mode: BLOCKS_GRAPH)
   └─ When you need deterministic control flow.

3. CODE AGENT (PYTHON_AGENT)
   └─ Last resort. Custom orchestration only.
```

### When to Use Each

| Agent Type | Use When |
|------------|----------|
| **Visual Agent** | Q&A, conversational, simple RAG, exploratory |
| **SVA** | Multi-step pipeline, guaranteed processing, conditional branching, audit trails |
| **Code Agent** | LangGraph, CrewAI, non-standard inference loops |

> For full SVA design (13 block types), see `references/structured-agents.md`.

---

## Quick Router

### Plugin Development

| Topic | Reference |
|-------|-----------|
| Plugin Structure | `references/plugin-structure.md` |
| Custom Recipes | `references/recipes.md` |
| Agent Tools | `references/llm-tools.md` |
| Webapps | `references/webapps.md` |
| Webapp Pitfalls | `references/webapp-pitfalls.md` |
| Parameters | `references/parameters.md` |
| Dataset Connectors | `references/datasets.md` |
| Macros | `references/macros.md` |
| Code Environments | `references/code-environments.md` |
| Testing | `references/testing.md` |
| Best Practices | `references/best-practices.md` |
| Plugin Workflow | `references/plugin-workflow.md` |
| Plugin Architecture | `references/plugin-architecture.md` |
| Visual Agent Blocks | `references/visual-agent-blocks.md` |
| Webapp Patterns | `references/webapp-patterns.md` |
| Agent Tool Patterns | `references/agent-tool-patterns.md` |
| Plugin Review | `references/plugin-review-checklist.md` |
| Scaffolding | `references/scaffolding.md` |
| Guardrails | `references/guardrails.md` |
| Dashboard & Charts | `references/dashboard-charts.md` |

### Platform Knowledge

| Topic | Reference |
|-------|-----------|
| Formulas | `references/formulas.md` |
| Prepare Processors | `references/prepare-processors.md` |
| Visual Recipe JSON | `references/visual-recipe-payloads.md` + `references/visual-conditions.md` |
| LLM Mesh | `references/llm-mesh.md` |
| Structured Visual Agents | `references/structured-agents.md` |
| Scenarios | `references/scenarios.md` |
| MLOps | `references/mlops.md` |
| Python API | `references/python-api.md` |
| Styling | `dataiku-internal-branding` skill |
| Geospatial | `references/geospatial.md` |
| Verification & Cost | `references/verification.md` |

---

## Cross-Cutting Patterns

Quick links for common combinations:

- **Scaffold plugin** → `scaffolding.md` + `plugin-structure.md`
- **Add agent tool** → `scaffolding.md` + `llm-tools.md`
- **Add recipe** → `scaffolding.md` + `recipes.md`
- **Add webapp** → `scaffolding.md` + `webapps.md`
- **Build RAG** → `llm-mesh.md`
- **Build SVA** → `structured-agents.md`
- **Style dashboard** → `dataiku-internal-branding` skill + `webapps.md`
- **Automate retraining** → `scenarios.md` + `mlops.md`
- **Deploy model** → `mlops.md` + `scenarios.md`
- **Set up guardrail** → `guardrails.md` + `scaffolding.md`

---

## Instructions

1. Identify topic(s) — check Quick Router above
2. Use `dku-cli` commands to execute
3. For scaffolding, read `references/scaffolding.md` first
4. For new plugins, read `references/plugin-architecture.md` first
5. Read relevant reference file(s)
6. Apply patterns
7. For webapps, also check `references/webapp-pitfalls.md`
8. **Verify every outcome** — run and check output

> For full documentation, see official Dataiku docs: https://developer.dataiku.com/
