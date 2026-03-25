# Plugin Architecture Guide

> Master reference for building Dataiku DSS plugins — from simple utilities to platform-scale applications. Defines plugin tiers, patterns, anti-patterns, and cross-references with official documentation.

**Gold standard references:**
- `dss-plugin-agent-hub` (17.6k LOC, Tier 5 enterprise platform)
- [`dss-plugin-semantic-models-lab`](https://github.com/dataiku/dss-plugin-semantic-models-lab) (agentic tools with LangGraph orchestration, Vue 3 SPA)
- `dss-plugin-aws-bedrock-agentcore-resources` (dual-mode blocks + tools + agent connector)
- `field-specialist-plugins` (6-plugin monorepo: structured agents, deep agent, toolkit)
- `dss-plugin-visual-edit` (modern webapp: pyproject.toml, Playwright, custom-fields)

**40+ public plugin repos** at `github.com/dataiku` — see [Official Plugin Repos](#official-plugin-repos-pattern-references) for the full list by component type.

**Production codebases analyzed:** genai_insights_dashboard, honeywell-regression, opencode-agent-tool, dataiku-mcp-gateway, dss-plugin-agent-hub, dss-plugin-aws-bedrock-agentcore-resources, dss-plugin-google-search-tool, dss-plugin-sureguard, dss-plugin-graph-editor, dss-plugin-semantic-models-lab

---

## Plugin Tiers

Every Dataiku plugin falls into one of five tiers. Pick the tier that matches your complexity, then follow the patterns for that tier.

### Tier 1 — Utility Plugin

**Complexity:** Low | **Files:** 5-15 | **LOC:** 200-500
**Components:** 1-2 recipes or macros, no webapp

```
my-utility/
├── plugin.json
├── custom-recipes/my-recipe/
│   ├── recipe.json
│   └── recipe.py
├── python-lib/my_utility/
│   └── core.py                     # Pure business logic
├── code-env/python/
│   ├── desc.json
│   └── spec/requirements.txt
└── tests/python/unit/
    └── test_core.py
```

**Examples:** Data format converter, schema validator, SQL executor

**Key pattern:** Recipe is a thin wrapper. Core logic in `python-lib/` with zero Dataiku imports. Tests run without DSS.

---

### Tier 2 — Agent Tool Plugin

**Complexity:** Medium | **Files:** 8-20 | **LOC:** 300-1500
**Components:** 1-3 agent tools, shared library

```
my-agent-tools/
├── plugin.json                      # Plugin-level params (API keys as PASSWORD)
├── python-agent-tools/
│   ├── tool-a/
│   │   ├── tool.json                # Tool params (timeout, model, endpoint)
│   │   └── tool.py                  # BaseAgentTool subclass
│   └── tool-b/
│       ├── tool.json
│       └── tool.py
├── python-lib/my_tools/
│   ├── __init__.py
│   ├── config.py                    # Dataclass + __post_init__ validation
│   ├── runner.py                    # Business logic (subprocess, API calls)
│   └── validation.py               # Pure validation (zero Dataiku deps)
├── code-env/python/
│   ├── desc.json
│   └── spec/requirements.txt
└── tests/python/unit/
    ├── conftest.py
    ├── test_validation.py           # Tests pure functions directly
    └── test_runner.py
```

**Examples:** opencode-agent-tool, search tools, database query tools

**Key pattern:** Config dataclass with factory method merging plugin + tool params. Subprocess tools use safe env vars. Output parsing has fallback chain.

**See:** `references/agent-tool-patterns.md` for detailed patterns.

---

### Tier 2b — Agent Integration Plugin (Blocks + Tools + Connector)

**Complexity:** Medium-High | **Files:** 15-30 | **LOC:** 1k-5k
**Components:** Agent tools + visual agent blocks + Python agent connector, shared library

This is a new pattern (DSS 14.4+) where the same capability is offered through multiple component types — deterministic blocks for guaranteed execution, tools for LLM-driven reasoning, and agent connectors for external runtime delegation.

```
my-agent-integration/
├── plugin.json
├── python-agent-tools/
│   ├── capability-a-tool/              # LLM decides when to call
│   │   ├── tool.json
│   │   └── tool.py
│   └── capability-b-tool/
│       ├── tool.json
│       └── tool.py
├── python-blocks-graph-blocks/         # Always runs at graph position
│   ├── capability-a-block/
│   │   ├── block.json
│   │   └── dynamic_choices.py
│   └── capability-b-block/
│       ├── block.json
│       └── dynamic_choices.py
├── python-agents/                      # Wraps external agent as LLM
│   └── external-runtime/
│       ├── agent.json
│       └── agent.py                    # BaseLLM subclass
├── python-lib/my_plugin/
│   ├── __init__.py
│   ├── auth.py                         # Shared credential resolution
│   ├── namespaces.py                   # Identity + scoping logic
│   ├── blocks.py                       # BlockHandler subclasses
│   └── core.py                         # Shared business logic (DRY)
├── resource/
│   └── dynamic_choices.py              # Shared dropdown population
├── code-env/python/
│   ├── desc.json
│   └── spec/requirements.txt
└── skills/
    └── dev-guide/SKILL.md              # Development guide
```

**Examples:** dss-plugin-aws-bedrock-agentcore-resources (memory + code interpreter + browser)

**Key patterns:**
- **Dual-mode:** Same capability as block (deterministic) AND tool (LLM-driven)
- **Shared infrastructure:** Auth, identity, namespaces in python-lib used by all components
- **Dynamic choices:** `getChoicesFromPython: true` with `triggerParameters` for cascading dropdowns
- **Identity resolution:** 3 sources — DSS login session, context variable, override (testing)
- **Namespace scoping:** Per-app isolation vs cross-app shared memory

**See:** `references/visual-agent-blocks.md` for detailed patterns.

---

### Tier 2c — Agentic Tool Plugin (Internal Agent Loop)

**Complexity:** Medium-High | **Files:** 20-50 | **LOC:** 3k-15k
**Components:** Agent tools with internal LangGraph orchestration, webapp, shared service layer

This tier represents tools that run multi-step reasoning loops internally. The tool receives a question and orchestrates multiple LLM calls + internal tool executions via LangGraph before returning a final answer.

```
my-agentic-plugin/
├── plugin.json
├── python-agent-tools/
│   ├── lite-tool/                       # Auto-spec mode (ease-of-use)
│   │   ├── tool.json
│   │   └── tool.py                      # BaseAgentTool → run_agent()
│   └── full-tool/                       # Explicit model mode (power users)
│       ├── tool.json
│       └── tool.py                      # BaseAgentTool → run_agent()
├── webapps/my-editor/
│   ├── webapp.json
│   ├── backend.py                       # One-liner: setup_app(app)
│   └── meta.json
├── python-lib/my_plugin/
│   ├── __init__.py
│   ├── setup.py                         # Flask app factory (DSS + local dev)
│   ├── config.py                        # AppConfig + ContextVar override
│   ├── exceptions.py                    # Custom exception hierarchy
│   ├── logging_utils.py                 # Request context + redaction
│   ├── agent/
│   │   ├── query_runner/                # LangGraph agent loop
│   │   │   └── core.py                  # build_agent_graph(), run_agent_core()
│   │   └── tools/                       # Internal tools (@tool decorator)
│   │       ├── schema_tools.py          # list_entities, get_attributes
│   │       ├── sql_tools.py             # generate_sql, execute_sql
│   │       └── resolution_tools.py      # resolve_values, get_glossary
│   ├── services/
│   │   ├── factory.py                   # get_service(client=)
│   │   ├── client.py                    # DSS API adapter (normalizes quirks)
│   │   └── service.py                   # Business logic (zero DSS imports)
│   ├── routes/                          # Flask Blueprints
│   │   ├── __init__.py                  # register_all_routes(app)
│   │   ├── common.py                    # Global error handler
│   │   └── *.py                         # Domain-specific route files
│   ├── prompts/                         # LLM prompt builders
│   ├── resolution/                      # Fuzzy + semantic matching
│   └── utils/
├── resource/
│   ├── params_helper.py                 # Dynamic param resolution via service
│   └── frontend/                        # Vue 3 / React SPA
│       ├── src/
│       └── vite.config.ts
├── code-env/python/
│   ├── desc.json                        # PYTHON310/311/312
│   └── spec/requirements.txt            # langgraph, langchain-core, dataiku-api-client
├── wsgi.py                              # Local dev entry point
├── Makefile                             # setup, backend-dev, frontend-dev, check-all
└── tests/
```

**Example:** [`dss-plugin-semantic-models-lab`](https://github.com/dataiku/dss-plugin-semantic-models-lab)

**Key patterns:**
- **Dual-mode tools:** Lite (auto-spec) and Full (explicit model) share same LangGraph agent loop
- **LangGraph orchestration:** `StateGraph` with internal `@tool` functions (NOT `BaseAgentTool`)
- **Service factory:** `get_service(client=)` with `LocalClient` abstracting DSS API
- **ContextVar config:** Thread-safe config serving both webapp and agent tool contexts
- **One-liner backend.py:** `setup_app(app)` delegates to `python-lib/`
- **Flask Blueprints:** Route organization via `register_all_routes(app)`
- **Local dev mode:** `wsgi.py` + `LOCAL_DEV=true` + CORS + `.env` + Makefile
- **Production logging:** Request context injection, sensitive data redaction, timing hooks
- **End-user security:** `enduser_sql_execution` param for row-level security delegation

**See:** `references/agent-tool-patterns.md` (Agentic Tool Pattern section) for detailed patterns.

---

### Tier 3 — Dashboard Plugin

**Complexity:** Medium-High | **Files:** 10-30 | **LOC:** 1k-8k
**Components:** 1 webapp (Flask backend + JS/React frontend), optional recipes for data prep

Two sub-variants:

#### Tier 3a — Vanilla JS Dashboard

No build step. Frontend lives in DSS tab editor (HTML/CSS/JS tabs).

```
my-dashboard/
├── plugin.json
├── webapps/my-dash/
│   ├── webapp.json                  # hasBackend, noJSSecurity, DATASET params
│   ├── backend.py                   # Flask routes (DSS-injected app)
│   ├── body.html                    # HTML tab (structure only)
│   ├── app.js                       # JS tab (state, fetch, render)
│   └── style.css                    # CSS tab (raw rules)
├── python-lib/my_dashboard/
│   └── aggregations.py              # Data transformation logic
└── code-env/python/spec/requirements.txt
```

**Examples:** genai_insights_dashboard (5k LOC backend, 5.5k LOC JS, Chart.js)

#### Tier 3b — React/Vue SPA Dashboard

Build step required. Frontend compiled to `resource/dist/`.

```
my-dashboard/
├── plugin.json
├── webapps/my-dash/
│   ├── webapp.json
│   └── backend.py
├── resource/
│   ├── frontend/                    # Source (gitignored dist/)
│   │   ├── src/
│   │   │   ├── App.tsx
│   │   │   ├── api.ts               # getWebAppBackendUrl wrapper
│   │   │   ├── types.ts             # Mirrors backend JSON
│   │   │   └── components/
│   │   ├── vite.config.ts           # Single bundle output
│   │   ├── tsconfig.json            # Strict mode
│   │   └── package.json
│   └── dist/                        # Build output (index.html, assets/)
├── python-lib/
└── code-env/python/spec/requirements.txt
```

**Examples:** honeywell-regression (React + Recharts + Tailwind)

**Key pattern:** Vite single-bundle config. TypeScript interfaces mirror backend response. `window.getWebAppBackendUrl` with DSS context check.

**See:** `references/webapp-patterns.md` for detailed patterns.

---

### Tier 4 — Full-Stack Plugin

**Complexity:** High | **Files:** 30-80 | **LOC:** 5k-20k
**Components:** Webapp + recipes + tools + macros, shared library, database optional

```
my-platform/
├── plugin.json
├── webapps/my-app/
│   ├── webapp.json                  # Storage params, logging, dynamic params
│   ├── backend.py                   # DSS entry point (thin: setup + migrations)
│   └── meta.json
├── resource/
│   ├── frontend/                    # Vue/React SPA
│   ├── params_helper.py             # Dynamic param generation
│   └── dist/
├── python-lib/backend/
│   ├── setup.py                     # Flask app factory
│   ├── config.py                    # Layered config (webapp params + DB + env)
│   ├── routes/                      # Flask blueprints (1 per resource)
│   ├── services/                    # Business logic layer
│   ├── database/
│   │   ├── models.py                # SQLAlchemy ORM
│   │   ├── crud/                    # Data access (1 per entity)
│   │   └── base.py                  # Flask-SQLAlchemy init
│   ├── utils/                       # Logging, auth, helpers
│   └── agents/                      # LLM orchestration (if applicable)
├── custom-recipes/
├── python-agent-tools/
├── python-runnables/
├── alembic/                         # Database migrations
│   ├── env.py                       # Multi-DB support + backup/recovery
│   └── versions/
├── code-env/python/
│   ├── desc.json
│   └── spec/
│       ├── requirements.txt
│       └── requirements.dev.txt
├── tests/
│   ├── unit/
│   └── migration/
├── Makefile
└── pyproject.toml                   # ruff, mypy config
```

**Examples:** dss-plugin-agent-hub (17.6k LOC), dataiku-mcp-gateway

**See:** Detailed patterns below.

---

### Tier 5 — Enterprise Platform Plugin

**Complexity:** Very High | **Files:** 80+ | **LOC:** 20k+
**Components:** Everything in Tier 4 + multi-tenant DB, real-time WebSocket, background workers, publishing workflows, analytics dashboard

The agent-hub is the only known Tier 5 plugin. It adds on top of Tier 4:
- SQLAlchemy + Alembic with 4 database backends (SQLite, PostgreSQL, MySQL, Snowflake)
- Flask-SocketIO for real-time streaming
- Background monitor threads (publishing, indexing)
- User-scoped CRUD with sharing/permissions
- Optimistic locking (etags) for admin config
- Pydantic v2 schemas with camelCase alias generation
- 50+ REST endpoints across 10 blueprint groups
- Vue 3 + Pinia + ECharts frontend (324 files)
- Alembic migrations with backup/recovery
- Structured logging with secret redaction

---

## Patterns (Do This)

### P1: Zero Dataiku Imports in Core Logic

**Tier:** All

```
python-lib/my_plugin/
├── core/               # ZERO Dataiku imports — trivially testable
│   ├── processors.py
│   └── validators.py
└── adapters/           # Dataiku integration wrappers
    └── datasets.py
```

Component files (`recipe.py`, `tool.py`, `backend.py`) are thin wrappers: read config → call core → format output. Tests import from core directly without mocking DSS.

### P2: Layered Configuration (Tier 3+)

DSS plugins have four config sources with clear ownership:

```
webapp.json params     → Storage type, DB connection (DSS admin sets at install)
    ↓
AdminSettings DB table → LLM config, agents, features (runtime-mutable via admin UI)
    ↓
Environment variables  → DB_SCHEMA, TABLES_PREFIX (deployment-specific)
    ↓
local_config.json      → Dev overrides (LOCAL execution only)
```

### P3: Dynamic Webapp Parameters

Populate SELECTs from live DSS state. `triggerParameters` re-fetches when dependencies change.

```json
{ "name": "db_connection", "type": "SELECT", "getChoicesFromPython": true, "triggerParameters": ["storage_type"] }
```

```python
# resource/params_helper.py
def do(payload, config, plugin_config, inputs):
    if payload.get("parameterName") == "db_connection":
        return {"choices": [{"value": c, "label": c} for c in dataiku.api_client().list_connections()]}
```

### P4: Database URL from DSS Connection (Tier 4+)

Resolve DB URL from DSS connection config instead of hardcoding credentials:

```python
conn = dataiku.api_client().get_connection(config["db_connection"])
params = conn.get_definition()["params"]
# Build URL per DB type
```

Use `TABLES_PREFIX` env var for multi-tenant isolation: `f"{prefix}conversations"`.
Run Alembic migrations as subprocess on startup to avoid circular imports.

---

## Anti-Patterns (Don't Do This)

### AP1: Creating Flask App

```python
# WRONG — breaks /__ping health check, webapp never starts
app = Flask(__name__)

# RIGHT — DSS injects app globally, just use it
@app.route("/api/data")
def get_data():
    ...
```

**Impact:** Webapp appears to deploy but never responds. Health check fails silently. Hours of debugging.

### AP2: Importing from Wrong Module

```python
# WRONG
from dataiku.webapp import get_webapp_config

# RIGHT
from dataiku.customwebapp import get_webapp_config
```

**Impact:** ImportError at runtime. Confusing because both modules exist.

### AP3: installCorePackages on Python 3.11+

```json
// WRONG — installs pandas 0.23.4, fails on Python 3.11
{ "installCorePackages": true, "corePackagesSet": "LEGACY_PANDAS023" }

// ALSO WRONG — PANDAS1 also fails on 3.11
{ "installCorePackages": true, "corePackagesSet": "PANDAS1" }

// RIGHT — explicit deps, always works
{ "installCorePackages": false }
```

With `requirements.txt`:
```
pandas>=2.0,<3
numpy>=1.22,<3
python-dateutil>=2.8,<3
requests>=2.28,<3
```

**Impact:** Code env creation fails. Broken env persists — must delete before retry.

### AP4: Hardcoded Dataset Names

```python
# WRONG
df = dataiku.Dataset("my_accounts_enriched").get_dataframe()

# RIGHT — configurable via webapp.json params
config = get_webapp_config()
df = dataiku.Dataset(config["accounts_dataset"]).get_dataframe()
```

**Impact:** Plugin not reusable. Different projects have different dataset names.

### AP5: Loading Datasets at Import Time

```python
# WRONG — fails if dataset doesn't exist yet
import dataiku
df = dataiku.Dataset("accounts").get_dataframe()  # Module-level!

@app.route("/api/data")
def get_data():
    return jsonify(df.to_dict())
```

```python
# RIGHT — lazy load on first request
_df = None

@app.before_request
def ensure_loaded():
    global _df
    if _df is None:
        _df = dataiku.Dataset(config["accounts_dataset"]).get_dataframe()
```

**Impact:** Backend crashes on startup if dataset hasn't been built yet. No error recovery.

### AP6: trace.set_attribute() in Agent Tools

```python
# WRONG — OpenTelemetry API, not DSS
trace.set_attribute("key", "value")

# RIGHT — DSS trace API (dict assignment)
trace.attributes["key"] = "value"
```

**Impact:** Silently fails. Metadata never appears in DSS trace UI.

### AP7: Tool Input at Root Level

```python
# WRONG — args are not at root
def invoke(self, input, trace):
    query = input.get("query", "")  # Always empty!

# RIGHT — DSS nests args under "input" key
def invoke(self, input, trace):
    args = input.get("input", {})
    query = args.get("query", "")
```

**Impact:** Tool always receives empty input. LLM retries, gives up, hallucinates.

### AP8: Subprocess Without Safety Flags

```python
# WRONG — blocks on stdin, ANSI garbage in output, no timeout
result = subprocess.run(["mytool", "--task", task], capture_output=True, text=True)

# RIGHT — safe subprocess
result = subprocess.run(
    ["mytool", "--task", task],
    stdin=subprocess.DEVNULL,           # MUST: prevent stdin blocking
    capture_output=True,
    text=True,
    timeout=120,                        # MUST: prevent infinite hangs
    env={**os.environ, "CI": "true", "TERM": "dumb", "NO_COLOR": "1"},
)
```

**Impact:** Tool server hangs. Stale process persists between Quick Test invocations. DSS must be restarted.

### AP9: Mutable Plugin Params

```python
# WRONG — plugin params are READ-ONLY at runtime
# Trying to save config back to plugin.json doesn't work

# RIGHT — use project variables for mutable config
def save_config(config):
    project = dataiku.api_client().get_default_project()
    variables = project.get_variables()
    variables.setdefault("standard", {})["my_config"] = config
    project.set_variables(variables)
```

**Impact:** Config changes lost on plugin update/restart. Silent failure.

### AP10: Webapps Folder Typo

```
# WRONG
custom-webapps/my-webapp/

# RIGHT
webapps/my-webapp/
```

**Impact:** DSS doesn't discover the webapp component. No error message.

### AP11: Vite Code Splitting for DSS

```typescript
// WRONG — unpredictable chunk filenames break DSS resource loading
export default defineConfig({
    build: {
        rollupOptions: {
            output: {
                // Default code splitting
            },
        },
    },
});

// RIGHT — single bundle
export default defineConfig({
    build: {
        rollupOptions: {
            output: {
                entryFileNames: "assets/index.js",
                chunkFileNames: "assets/[name].js",
                assetFileNames: "assets/index.[ext]",
            },
        },
    },
});
```

**Impact:** Frontend loads partially or not at all. Random 404s on chunk files.

---

## Official Docs Comparison

### What Official Docs Cover Well
- Plugin.json manifest structure and field reference
- Parameter types (30+ types with detailed options)
- Recipe input/output roles and arity
- Webapp security model (impersonation, run-as-user)
- Code environment managed vs non-managed distinction

### What Official Docs Miss (Our Docs Fill)

| Gap | Impact | Our Reference |
|-----|--------|---------------|
| Flask app injection behavior | #1 webapp bug | `webapp-pitfalls.md` |
| `noJSSecurity`, `enableJavascriptModules` flags | React/Vue apps don't load | `webapps.md` |
| Agent tool input nesting (`input.get("input", {})`) | Tools receive empty input | `llm-tools.md`, `agent-tool-patterns.md` |
| `trace.attributes[key] = value` vs `trace.set_attribute` | Trace data lost | `llm-tools.md` |
| Python 3.11 core packages failure | Code env creation fails | `CLAUDE.md` gotchas |
| Subprocess safety in tools | Tool server hangs | `agent-tool-patterns.md` |
| Knowledge Bank role acceptance | Recipes can't use KBs | `recipes.md` |
| Complete testing patterns | No official test guide | `testing.md` |
| Multi-database webapp patterns | No official guidance | `webapp-patterns.md` |
| Real-time streaming patterns | No official guidance | `webapp-patterns.md` |

### What Official Docs Have That We Should Add

| Gap in Our Docs | Where to Add |
|-----------------|--------------|
| `CREDENTIAL_REQUEST` parameter type (OAuth2 flow) | `parameters.md` |
| `KEY_VALUE_LIST` return format `[{from, to}]` | `parameters.md` |
| `allowedColumnTypes` constraint on COLUMN params | `parameters.md` |
| `triggerParameters` + `disableAutoReload` on dynamic selects | `parameters.md` |
| `API_SERVICE_VERSION` + `ML_TASK` linked params | `parameters.md` |
| `corePackagesSet` values (`AUTO`, `LEGACY_PANDAS023`, `PANDAS1`, `PANDAS10`) | `code-environments.md` |
| `WebappImpersonationContext()` security pattern | `webapps.md` |
| `desc.json` `corePackagesSet: "AUTO"` as default | `code-environments.md` |

---

## Agent-Hub: Gold Standard Patterns

These patterns from agent-hub represent the highest tier of Dataiku plugin engineering:

### Architecture Layers

```
webapp.json params → backend.py (thin entry) → setup.py (app factory)
    ↓                                              ↓
Alembic migrations ← database/models.py ← database/crud/* ← database/user_store.py
    ↓                                              ↓
routes/* (blueprints) → services/* (business logic) → agents/* (LLM orchestration)
    ↓                                              ↓
schemas/* (Pydantic v2) → utils/* (logging, auth, helpers)
    ↓
resource/frontend/ (Vue 3 + Pinia + ECharts)
    ↓
resource/dist/ (compiled SPA)
```

### Database Strategy

| Aspect | Pattern |
|--------|---------|
| **Multi-backend** | SQLite (dev), PostgreSQL, MySQL, Snowflake via `app_paths.py` URL resolution |
| **Multi-tenant** | `TABLES_PREFIX` env var prepended to all table names |
| **Schema isolation** | `DB_SCHEMA` env var for PostgreSQL/Snowflake |
| **Migrations** | Alembic with backup before, recovery guidance after failure |
| **Custom types** | `JsonEncoded(TypeDecorator)` for JSON columns in any DB |
| **Compression** | zlib for artifacts/trace (5-10x reduction) |
| **Snowflake OAuth** | Custom `creator()` pool factory for fresh token on each connection |
| **FK prefix** | `f"{DB_SCHEMA}.{TABLES_PREFIX}"` in ForeignKey definitions |

### Real-Time Streaming

| Aspect | Pattern |
|--------|---------|
| **Transport** | Flask-SocketIO on `/stream` namespace, compression enabled |
| **Events** | 24 event types (`EventKind` enum) from agent lifecycle |
| **Normalization** | `normalise_stream_event()` converts raw LLM chunks → standardized events |
| **Deduplication** | `_stream_started` set tracks which streams emitted `ANSWER_STREAM_START` |
| **Artifact sizing** | Check `get_artifacts_size_mb()` before emit; preview if oversized |
| **HITL** | `TOOL_VALIDATION_REQUESTS` event → pause → resume with memory fragment |

### Publishing Workflow

```
Draft (owner only)
    ↓ start_publish(agent_id)
PUBLISHING status → background thread monitors DSS job
    ↓ job completes
PUBLISHED → snapshot created (tools, LLM, prompt, KB details)
    ↓ shared users see published_version only
    ↓ owner sees both draft + published
```

**Retry:** Max 3 attempts with 10s delay. Timeout: 30 minutes per job.

### Config System

```
get_webapp_config()          → Storage type, DB connection (set by DSS admin)
get_config_v2()              → AdminSettings from DB (runtime-mutable via admin UI)
get_config()                 → Legacy v1 compat wrapper around v2
get_ui_config()              → Merged view for frontend (agents + LLMs + features)
load_local_config()          → Dev overrides from local_config.json
```

**Caching:** `@cache.memoize()` on expensive lookups (project keys, agent details).

### Security

| Layer | Pattern |
|-------|---------|
| **Auth** | `g.authIdentifier` from DSS session, `WebappImpersonationContext()` |
| **Data access** | `UserStore(user_id, groups)` scopes all queries |
| **Agent sharing** | `AgentShare` table with USER/GROUP principal types |
| **Logging** | `RedactSensitiveDataFilter` strips passwords, tokens, API keys |
| **Credential sanitizing** | DB URLs + OAuth tokens sanitized in log output |
| **Request logging** | `@log_http_request` decorator with req_id, user, timing |

---

## Official Plugin Repos (Pattern References)

All plugins below are public at `github.com/dataiku`. When building a plugin, clone or browse the most relevant repo to see real production patterns. **Bias towards repos updated in 2025-2026** — older patterns may use deprecated APIs.

### Agent Tools & Agents (Tier 2)

| Repo | Updated | What to learn |
|------|---------|---------------|
| [`dss-plugin-semantic-models-lab`](https://github.com/dataiku/dss-plugin-semantic-models-lab) | 2026-03 | **State-of-the-art agentic plugin (Tier 2c)** — LangGraph internal agent loop, `DKUChatModel`, dual-mode tools, service factory, Flask Blueprints, Vue 3 SPA, local dev mode, production logging |
| `dss-plugin-google-search-tool` | 2025-11 | **Cleanest single agent tool** — minimal `python-agent-tools/`, parameter-sets |
| `dss-plugin-sql-question-answering-tool` | 2026-02 | Agent tool + eval-tool + python-lib + tests |
| `dss-plugin-agent-optimization-tool` | 2026-02 | Agent optimization patterns |
| `dss-plugin-a2a-agents` | 2025-11 | **A2A protocol** — `python-agents/a2a` implementation |
| `dss-plugin-aws-bedrock-agents` | 2026-02 | AWS Bedrock agent integration |
| `dss-plugin-vertex-ai-agents` | 2026-02 | Vertex AI agent integration |
| `dss-plugin-microsoft-copilot-agents` | 2026-01 | Microsoft Copilot agent integration |
| `field-specialist-plugins` | 2026-03 | **Monorepo with 6 plugins**: structured agent patterns (`bs-agent-architectures`), deep research agent (`deep-agent`), field toolkit (tools + guardrails + recipes) |

### Guardrails

| Repo | Updated | What to learn |
|------|---------|---------------|
| `dss-plugin-sample-guardrail-rewrite-answer` | 2025-02 | **Simplest guardrail structure** — `python-guardrails/` rewrite example |
| `dss-plugin-guardrail-bias-detector` | 2025-12 | Bias detection guardrail |

### Webapps (Tier 3-5)

| Repo | Updated | What to learn |
|------|---------|---------------|
| `dss-plugin-agent-hub` | 2026-03 | **Gold standard (Tier 5)** — 17.6k LOC, Vue 3 + Flask + SQLAlchemy + Alembic + SocketIO |
| `dss-plugin-visual-edit` | 2026-03 | **Most modern build**: `pyproject.toml`, Makefile, Playwright tests, custom-fields |
| `dss-plugin-graph-editor` | 2026-03 | **Multi-component exemplar**: 2 webapps, 5 recipes, agent tools, parameter-sets, JS build |
| `dss-plugin-document-question-answering` | 2026-03 | Complex webapp + GenAI, OpenAPI spec, JS build, Playwright tests |
| `dss-plugin-sureguard` | 2026-03 | LLM evaluation webapp ("unified-dashboard"), recipes, python-lib. Has its own CLAUDE.md |
| `dss-plugin-traces-explorer` | 2026-03 | LLM trace visualization webapp, has AGENTS.md |
| `dss-agents-portal` | 2026-03 | **Agent Connect UI** — multi-agent chat, modern JS, Playwright tests |

### Recipes (Tier 1)

| Repo | Updated | What to learn |
|------|---------|---------------|
| `dss-plugin-nlp-preparation` | 2026-01 | **Most starred plugin** (22 stars) — language detection, spellcheck, text cleaning |
| `dss-plugin-timeseries-forecast` | 2025-12 | Deep learning + statistical forecasting, well-structured tests |
| `dss-plugin-nlp-named-entity-recognition` | 2026-02 | NER with multiple backends |
| `dss-plugin-synthetic-data-generation` | 2026-02 | Synthetic data generation |

### Connectors

| Repo | Updated | What to learn |
|------|---------|---------------|
| `dss-plugin-sharepoint-online` | 2026-02 | **Best connector example** — connectors + FS providers + recipes + parameter-sets |
| `dss-plugin-servicenow` | 2026-03 | ServiceNow connector (recent) |
| `dss-plugin-googledrive` | 2026-01 | Google Drive + Sheets connector |
| `dss-plugin-neo4j` | 2025-10 | Graph DB connector |

### LLM Plugins

| Repo | Updated | What to learn |
|------|---------|---------------|
| `plugins-llm` | 2026-01 | **21 custom LLM connection plugins** (Bedrock, Azure APIM, NVIDIA NIM, HuggingFace, customer-specific) |
| `dss-plugin-graphrag` | 2026-02 | GraphRAG implementation |
| `dss-plugin-rag-optimization` | 2026-02 | RAG optimization tooling |

### RAG & Knowledge Banks

| Repo | Updated | What to learn |
|------|---------|---------------|
| `dss-plugin-nlp-embedding` | 2026-01 | Vector embedding extraction |
| `dss-plugin-prompt-optimization` | 2026-02 | Prompt optimization |

### Tooling & Libraries

| Repo | Updated | What to learn |
|------|---------|---------------|
| `dss-plugin-template` | 2025-09 | **Canonical starting point** — minimal plugin scaffold |
| `greffon-cli` | 2026-03 | Dataiku's internal CLI for plugin/solution builds (uv, justfile) |
| `dataiku-plugin-tests-utils` | 2025-07 | Official testing utilities for plugins |
| `dss-plugin-dkulib` | 2026-03 | Reusable shared Python code for plugins |
| `dataiku-api-client-python` | 2026-03 | **`dataikuapi` source** (41 stars) — verify API quirks against real code |

### How to Use These Repos

When building a new plugin:
1. Pick the closest match by component type from the tables above
2. Browse on GitHub (`github.com/dataiku/<repo-name>`) or clone locally
3. Study the `plugin.json`, component JSON configs, and code patterns
4. Pay attention to: folder structure, parameter types, code-env setup, test patterns
5. **Prefer repos updated 2025+** — older repos may use deprecated patterns (`get_definition()`, `installCorePackages: true`, etc.)

---

## Quick Reference: Which Tier Am I?

| If you need... | Tier | Start with |
|----------------|------|------------|
| Transform data between datasets | 1 - Utility | Recipe + python-lib |
| Give LLM a new capability | 2 - Agent Tool | BaseAgentTool + config dataclass |
| Visualize data in DSS | 3a - Vanilla Dashboard | Flask + Chart.js/D3 |
| Build a typed, component-based UI | 3b - SPA Dashboard | Flask + React/Vue + Vite |
| Build a product with persistence | 4 - Full-Stack | Flask + SQLAlchemy + SPA |
| Build an enterprise platform | 5 - Enterprise | Everything above + WebSocket + migrations |
