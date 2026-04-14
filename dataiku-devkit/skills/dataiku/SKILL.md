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
  - sas migration
  - migrate sas
  - convert sas
  - translate sas
  - .sas file
  - .egp file
  - .flw file
  - proc sql
  - data step
  - proc format
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

## Companion Skill: `dku-cli`

**This skill and `dku-cli` are a pair. Always use both.**

- **This skill** tells you *what* to build and *how* DSS works (recipes, agents, plugins, formulas, MLOps patterns)
- **`dku-cli`** tells you *how to execute* — create projects, upload data, wire recipes, build pipelines, deploy plugins

**Typical workflow:**
1. Read this skill to understand the right DSS approach (visual recipe? agent? plugin?)
2. Use `dku-cli` commands to create, configure, build, and verify everything
3. **Verify every outcome** — see [Verification Protocol](#verification-protocol) below

When this skill says "use a visual join recipe", the CLI skill shows the exact `dku recipe create-join` command. When this skill says "create a knowledge bank", the CLI skill shows `dku knowledge create`. Never read one without considering the other.

---

## Verification Protocol — Trust Nothing, Verify Everything

**Every artifact you create MUST be verified before you consider the task done.** DSS commands can succeed (exit 0) while producing empty datasets, broken schemas, or misconfigured recipes. Silent failures are the norm, not the exception.

### Mandatory Verification Steps

After creating and building any pipeline, agent, or plugin:

| What you built | How to verify | What to check |
|----------------|--------------|---------------|
| **Dataset upload** | `dku dataset head NAME -P PROJ -n 3` | Rows exist, columns correct, types not all string |
| **Recipe (any type)** | `dku dataset build OUTPUT --wait -P PROJ` then `dku dataset head OUTPUT -P PROJ -n 5` | Output has rows, schema matches expectations |
| **Full pipeline** | `dku job run --target LEAF -P PROJ --type RECURSIVE_BUILD --auto-update-schema --wait` then `dku dataset head LEAF -P PROJ` | Final output is populated, no schema mismatches |
| **Visual recipe config** | `dku recipe get-definition NAME -P PROJ -o json` | Verify join keys, aggregation columns, filter conditions are set |
| **Agent** | `dku agent status NAME -P PROJ` | Status is correct, LLM is assigned |
| **Agent tools** | `dku agent-tool list -P PROJ` | Tools are created AND attached to the agent |
| **Knowledge bank** | `dku knowledge search NAME --query "test" -P PROJ` | Returns results after build |
| **Plugin push** | `dku plugin get NAME -o json` | Version correct, code env assigned |
| **Dashboard/Chart** | `dku insight validate ID -P PROJ` | Column names exist in dataset |
| **Scenario** | `dku scenario run NAME -P PROJ --wait` then `dku scenario status NAME -P PROJ` | Completed successfully |
| **ML model** | `dku ml details AID TID MID -P PROJ` | Metrics exist, performance is reasonable |

### Verification Rules

1. **Never assume success from exit code alone.** A recipe can "build successfully" but produce 0 rows.
2. **Always `head` the final output.** This is the single most important verification — if the output looks right, the pipeline works.
3. **Check schemas after visual recipes.** Visual recipes auto-propagate schemas, but columns may be renamed (e.g., join prefixing) or dropped.
4. **Test agents end-to-end.** Creating an agent + tools is not enough. Verify the agent can actually call the tools and return useful output.
5. **Build before declaring done.** An unwired pipeline with 0 built datasets is not a working pipeline.

---

## Working with Existing Projects

When dropped into an established project, **understand before you act.** Existing projects may have large datasets (millions of rows, gigabytes of data), expensive compute connections (Spark, BigQuery, Snowflake), and LLM recipes that cost real money per run. Reckless builds can rack up significant bills.

### Exploration Protocol (always follow this order)

```bash
# Step 1: Understand structure — one call, no data movement
dku project inspect PROJ -o json

# Step 2: Gauge dataset sizes — check BEFORE pulling any data
dku dataset info SOURCE_DS1 -P PROJ && \
dku dataset info SOURCE_DS2 -P PROJ

# Step 3: Understand schemas
dku dataset schema KEY_DS -P PROJ

# Step 4: Sample actual data (small — never more than 20 rows initially)
dku dataset head KEY_DS -P PROJ -n 10

# Step 5: Understand the flow
dku flow visualize -P PROJ
```

**Rules for existing projects:**
- **Always `info` before `head`.** Know how big a dataset is before pulling rows. A 50GB SQL table looks the same as a 50KB CSV in `list`.
- **Never `head` with more than 20 rows initially.** Increase only after confirming the dataset is reasonably sized. For large datasets, use `--columns` to limit width too.
- **Never trigger a full recursive build without asking the user.** `RECURSIVE_BUILD` on a project with 50 datasets and Spark recipes can cost hundreds of dollars.
- **Check connection types.** SQL/Spark/BigQuery connections mean server-side compute that may be metered. `dku connection list` shows available connections; `dku dataset info DS -P PROJ` shows which connection a dataset uses.
- **Don't modify existing recipes without understanding them.** Run `dku recipe get-definition RECIPE -P PROJ -o json` before changing anything.

### Cost Consciousness — Be the User's Financial Guardian

You are the user's Dataiku companion. Act like a responsible colleague who thinks about cost implications before clicking "Run".

**Compute cost awareness:**

| Action | Cost risk | What to check first |
|--------|-----------|-------------------|
| `RECURSIVE_BUILD` on large flow | **High** — rebuilds everything upstream | `dku flow visualize` to see scope; ask user |
| Python recipe on large dataset | **Medium** — loads data into memory | `dku dataset info` for row count; suggest sampling |
| LLM recipe (prompt, classify, embed) | **High** — API cost per row | `dku dataset info` for row count; calculate: rows x tokens x $/token |
| Building a knowledge bank | **Medium** — embedding cost per chunk | Check source dataset size; estimate chunk count |
| Visual recipe (join, group, sort) | **Low** — DSS-optimized, uses engines | Usually safe; check if Spark connection |
| Agent test query | **Low** — single LLM call | Safe for testing |
| Training ML model (AutoML) | **Medium** — CPU/GPU time | Check dataset size and number of algorithms enabled |

**LLM cost optimization:**
- **Prefer visual recipes over LLM recipes.** A join recipe costs zero LLM tokens; a "use AI to combine datasets" costs tokens per row.
- **Sample before LLM processing.** If an LLM recipe must process 100K rows, first create a sampling recipe with 100 rows to validate the output format and quality. Only then run on full data — and tell the user the estimated cost.
- **Choose the right LLM.** Not every task needs GPT-4 / Claude Opus. Use `dku llm list -P PROJ` to see available models. Classification and extraction tasks often work fine with smaller, cheaper models.
- **Batch over streaming.** One `dku llm completion` call with a batch prompt is cheaper than N individual calls.

**When to escalate to the user:**
- Dataset has >1M rows and you're about to create an LLM recipe targeting it
- Recursive build touches >10 datasets or includes Spark/BigQuery recipes
- Knowledge bank source has >10K documents
- Any operation where you can estimate cost >$10
- You're unsure about the billing model of a connection type

**Template for cost escalation:**
> "This dataset has [X rows / Y GB]. The [operation] will [estimated impact]. Want me to proceed, or should I sample first / use a cheaper approach?"

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
| **Formulas** | Formula language, computed columns, Prepare recipe expressions, `if()`, `strval()`, `forEach()`, log/exp gotchas | `references/formulas.md` |
| **Prepare Processors** | ~95 processor types with selection guidance. **ALWAYS prefer purpose-built processors over GREL.** Decision table, shared param patterns, canonical JSON for 20 processors | `references/prepare-processors.md` |
| **Visual Recipe Payloads** | JSON payload structure for join, group, window, filter, topN recipes. Use when CLI flags don't cover your configuration need | `references/visual-recipe-payloads.md` |
| **Visual Conditions** | Shared `uiData.conditions[]` schema for filters, split conditions, VisualIfRule. Operator catalog, AND/OR groups, canonical examples | `references/visual-conditions.md` |
| **LLM Mesh** | GenAI apps, LLM connections, tools, guardrails, RAG, knowledge banks, LangChain integration | `references/llm-mesh.md` |
| **Structured Visual Agents** | SVA design guide: all 13 block types (when/why), graph patterns, state management, CLI workflow | `references/structured-agents.md` |
| **Scenarios** | Automation, triggers, steps, reporters, metrics/checks, pipeline orchestration | `references/scenarios.md` |
| **MLOps** | Model training, evaluation, MLflow, saved models, API Node, deployment, drift detection | `references/mlops.md` |
| **Python API** | `dataiku.Dataset`, `dataikuapi`, read/write data, managed folders, SQL, code recipes | `references/python-api.md` |
| **Styling** | Dataiku brand colors, typography, Tailwind config, UI components, design system | `references/styling.md` |

### SAS Migration

| Topic | When to use | Reference |
|-------|-------------|-----------|
| **SAS Migration — Plan** | Starting a SAS → Dataiku migration. 5-phase workflow, inventory extraction from `.sas`/`.egp`/`.flw`, non-migratable patterns, top gotchas | `references/sas-migration/plan.md` |
| **SAS Semantics** | Translating any DATA step, MERGE, RETAIN, or macro. SAS language rules that silently change values (missing, PDV, MERGE many-to-many, LAG trap, PROC UNIVARIATE defaults) | `references/sas-migration/semantics.md` |
| **SAS → Dataiku Translation** | Mapping DATA steps / PROCs / functions to Dataiku recipes. Canonical Join+Prepare patterns, PROC FORMAT, rounding parity, enterprise passthrough workflow, SAS→Postgres translations | `references/sas-migration/translation.md` |


## Instructions

1. Identify which topic(s) the user's task involves
2. **Use `dku-cli` commands to execute.** This skill tells you what to build; the CLI skill tells you how to run it. Always use both.
3. For scaffolding tasks (new plugin, add component, deploy, review), read `references/scaffolding.md`
4. For new plugins, read `references/plugin-architecture.md` first to pick the right tier
5. Read the relevant reference file(s) — for cross-cutting tasks, read multiple
6. Apply the patterns and examples from the references
7. For webapps, always also check `references/webapp-pitfalls.md`
8. For dependency or compatibility issues, check `references/code-environments.md`
9. For structured visual agents (SVAs), read `references/structured-agents.md` for design patterns and block selection, then `docs/block-graph-api.md` for JSON schemas
10. **When unsure about a pattern**, check the "Official Plugin Repos" section in `references/plugin-architecture.md` — it lists 40+ public repos at `github.com/dataiku` organized by component type. Browse the closest match to see real production code.
11. **Verify every outcome.** After building anything, run it and check the output. See [Verification Protocol](#verification-protocol--trust-nothing-verify-everything) above. Your job is done when you've proven the output is correct, not when commands exit 0.
12. **Prepare recipes: ALWAYS prefer purpose-built processors over GREL.** Before writing any prepare step, READ `references/prepare-processors.md` for the processor decision table and exact params. Use `CreateColumnWithGREL` / `add-formula` ONLY when no dedicated processor exists. There are ~95 processor types — date parsing, string transforms, if/then/else, filtering, binning, JSON flattening, and more all have dedicated processors that are faster and cleaner than GREL.
13. **Gauge before you touch.** Before pulling data or building anything, run `dku dataset info DS -P PROJ` to check row count and data size. Datasets can be millions of rows and gigabytes — a blind `head -n 1000` on a 50GB SQL table is fine, but building a Python recipe that `df.iterrows()` over 100M rows will fail or cost a fortune. **Ask the user before triggering expensive operations** (full builds on large datasets, LLM recipes on high-cardinality data, recursive builds touching many datasets).
14. **Sample data before transforming.** Before creating or configuring ANY recipe, inspect the input dataset with `dku dataset head INPUT -P PROJ -n 5` to verify column names, data formats, and value patterns. Don't assume date formats (`yyyy-MM-dd` vs `MM/dd/yyyy`), column cardinality, or value ranges from schema alone. For joins, verify both datasets have matching key column values.
15. **Visual recipe payloads.** When CLI flags don't cover your configuration need (custom join conditions, additional aggregations, post-filters), READ `references/visual-recipe-payloads.md` for payload schemas and `references/visual-conditions.md` for filter/condition JSON. Use `dku recipe get-settings` → edit → `dku recipe set-definition --payload`.

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
- **"Add prepare recipe steps"** -> `prepare-processors.md` (READ FIRST — processor selection + params) + `dku-cli` skill (CLI commands)
- **"Add a formula processor"** -> `prepare-processors.md` (check if a purpose-built processor exists first) + `formulas.md` (only if GREL is truly needed)
- **"Configure visual recipe beyond CLI flags"** -> `visual-recipe-payloads.md` (payload schemas) + `visual-conditions.md` (filter/condition JSON)
- **"Add filter/condition to a recipe"** -> `visual-conditions.md` (uiData operator catalog) + `visual-recipe-payloads.md` (where filters go in each recipe type)
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
- **"Migrate a SAS program / `.sas` / `.egp` / `.flw` to Dataiku"** -> `sas-migration/plan.md` (5-phase workflow) + `sas-migration/semantics.md` (before translating any DATA step) + `sas-migration/translation.md` (recipe / function / PROC mapping) + `dku-cli` skill's `references/sql-engines.md` (when target is a SQL connection)
- **"Translate a SAS `DATA` step / `MERGE` / `RETAIN` / `PROC SQL`"** -> `sas-migration/translation.md` + `sas-migration/semantics.md` (for value-changing rules)

## Additional References

If a topic is not covered by the reference files above, consult the official Dataiku documentation:

- **Developer docs**: https://developer.dataiku.com/
- **Product docs**: https://doc.dataiku.com/dss/latest/
- **Plugin docs**: https://developer.dataiku.com/latest/plugins/index.html
