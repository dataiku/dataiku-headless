# Reference: Plugins

Durable plugin detail: component structure, parameter wiring, production patterns, testing.
Sequencing and CLI deploy commands live in `playbooks/extensions-admin.md`.

- [Anatomy](#anatomy) / [Tiers](#tiers-pick-before-coding)
- [In-DSS runtime API](#in-dss-runtime-api-recipeswebappstools)
- [Component templates](#component-templates-essentials)
- [Parameter wiring](#parameter-wiring)
- [Production patterns](#production-patterns) / [Anti-patterns](#anti-patterns-fix)
- [Testing](#testing) / [Review checklist](#review-checklist-canonical)

## Anatomy

A plugin is a directory (or ZIP with `plugin.json` **at root**) of self-contained components.

```
my-plugin/
├── plugin.json                 # manifest (required)
├── python-lib/my_plugin/       # shared code (zero-DSS core — see Production patterns)
├── code-env/python/
│   ├── desc.json               # acceptedPythonInterpreters, forceConda, installCorePackages
│   └── spec/requirements.txt   # MUST list pandas, numpy, python-dateutil, requests
│                               # (the dataiku runtime imports them at load even if you don't)
└── resource/                   # dynamic SELECT choice scripts + {dist,icons}/ (built webapp assets, icons)
```

`plugin.json` keys: `id` (A-Za-z0-9_-, **immutable after first release**), `version`
(semver), `meta` (`label`, `description`, `icon` = FontAwesome 3.2.1 class, optional
`iconColor`, `tags`, `recipesCategory` ∈ visual/code/genai/other), optional `params`
(plugin-level config), optional `permissions.requiredPermission`.

### Component dirs → files

| Component | Folder | Config + code | Base class / entry |
|---|---|---|---|
| Recipe | `custom-recipes/<n>/` | `recipe.json` + `recipe.py` | `get_recipe_config()`, role helpers |
| Connector | `python-connectors/<n>/` | `connector.json` + `connector.py` | `Connector` |
| Webapp | `webapps/<n>/` | `webapp.json` + `backend.py` (+`app.js`,`body.html`) | DSS-injected `app` |
| Macro | `python-runnables/<n>/` | `runnable.json` + `runnable.py` | — |
| Agent tool | `python-agent-tools/<n>/` | `tool.json` + `tool.py` | `BaseAgentTool` |
| Custom agent | `python-agents/<n>/` | `agent.json` + `agent.py` | `BaseLLM` |
| Guardrail | `python-guardrails/<n>/` | `guardrail.json` + `guardrail.py` | `BaseGuardrail` |
| Visual agent block | `python-structured-agent-blocks/<n>/` | `block.json` + `block.py` | `BlockHandler` |
| Prep step | `custom-steps/<n>/` | `processor.json` + `processor.py` | — |
| File format | `python-formats/<n>/` | `format.json` + `format.py` | custom file extractor/exporter |
| FS provider | `python-fs-providers/<n>/` | `fsprovider.json` + `fsprovider.py` | custom storage backend |
| Metric probe | `python-probes/<n>/` | `probe.json` + `probe.py` | custom dataset/model metrics |
| Check | `python-checks/<n>/` | `check.json` + `check.py` | data-quality checks |
| Scenario step | `python-steps/<n>/` | `step.json` + `step.py` | custom automation step |
| Scenario trigger | `python-triggers/<n>/` | `trigger.json` + `trigger.py` | custom automation trigger |
| Parameter set | `parameter-sets/<n>/` | `parameterset.json` (no code) | reusable param group reused by other components |

DSS recipe type = `CustomCode_<recipeDir>` (plugin id NOT included). Folder names
are fixed conventions — DSS discovers a component only under its exact dir.

## Tiers (pick before coding)

| Tier | LOC | Shape |
|---|---|---|
| 1 Utility | 200–500 | 1–2 recipes/macros, core logic in `python-lib/`, unit tests no DSS |
| 2 Agent tools | 300–1500 | `BaseAgentTool` + config dataclass merging plugin+tool params |
| 2b Agent integration | 1k–5k | same capability as block (deterministic) + tool (LLM-driven) + agent connector; shared auth/identity in `python-lib/` |
| 2c Agentic tool | 3k–15k | internal LangGraph loop (`@tool` funcs, NOT `BaseAgentTool`), service factory, webapp |
| 3 Dashboard | 1k–8k | webapp: 3a vanilla JS (no build) or 3b React/Vue SPA → `resource/dist/` |
| 4 Full-stack | 5k–20k | webapp + recipes + tools, blueprints, SQLAlchemy/Alembic, services layer |
| 5 Enterprise | 20k+ | multi-tenant DB, Socket.IO, background workers, publishing (agent-hub) |

**Reference plugins** (public, github.com/dataiku — clone the closest match; bias to 2025+,
older = deprecated APIs): `dss-plugin-template` (canonical scaffold) · `dss-plugin-google-search-tool`
(minimal agent tool) · `dss-plugin-semantic-models-lab` (Tier-2c agentic: LangGraph loop + service
factory + Vue SPA) · `dss-plugin-agent-hub` (Tier-5 platform) · `field-specialist-plugins` (6-plugin
monorepo) · `plugins-llm` (21 custom LLM-connection plugins) · `dataiku-plugin-tests-utils` (test harness).

## In-DSS runtime API (recipes/webapps/tools)

Call families with unguessable names (the `dataiku` package, inside DSS only):

- **SQL** — `import dataiku` then `dataiku.sql.SQLExecutor2(connection="conn")` or
  `SQLExecutor2(dataset=ds)`. `query_to_df(sql, params=[...])` with `%s` binding runs queries
  AND statements (e.g. `TRUNCATE`). SQL can reference a dataset's physical table via
  `${DKU_DST_<dataset_name>}`.
- **Folder** — `dataiku.Folder(name)`: `list_paths_in_partition()`,
  `get_download_stream(path)`, `upload_stream(path, fileobj)`, `get_path()` (local-FS only).
- **KnowledgeBank** — `dataiku.KnowledgeBank(name)` (recipe must declare the
  `acceptsKnowledgeBank` input role — see Component templates).
- **Variables** — `dataiku.get_custom_variables(typed=True)` for typed project variables
  (untyped returns all-strings).

## Component templates (essentials)

**Agent tool** (arg nesting and trace API: see Anti-patterns):
```python
class MyTool(BaseAgentTool):
    def get_descriptor(self, tool):
        return {"description": TOOL_DESCRIPTION, "inputSchema": {"type": "object", "properties": {}, "required": []}}
    def set_config(self, config, plugin_config):
        self.config, self.plugin_config = config, plugin_config
    def invoke(self, input, trace):
        args = input.get("input", {})
        return {"output": "..."}
```

**Recipe** — thin wrapper: read config + roles → call `python-lib` core → write.
```python
from dataiku.customrecipe import get_recipe_config, get_input_names_for_role, get_output_names_for_role
df = dataiku.Dataset(get_input_names_for_role("input")[0]).get_dataframe()
dataiku.Dataset(get_output_names_for_role("output")[0]).write_with_schema(result_df)
```
`recipe.json` declares `inputRoles`/`outputRoles` (`arity` UNARY/NARY, `acceptsDataset`)
and must match what `recipe.py` reads. Roles also accept `acceptsManagedFolder: true` and
`acceptsKnowledgeBank: true` (DSS 14.1+) alongside `acceptsDataset` — a KB-input recipe
(custom retrieval/re-index) declares `acceptsKnowledgeBank`, then reads it via
`dataiku.KnowledgeBank(name)` in code.

**Guardrail** — `process(self, input, trace)`; read `input["completionQuery"]["messages"]`
and/or `input["completionResponse"]["text"]`; raise to block, mutate to rewrite, return
`input`. Security guardrails fail closed (block on error).

## Parameter wiring

Static params live in `recipe.json`/`tool.json`/`webapp.json` `params[]`. Full type
catalog, per-type extra fields, and the dynamic-SELECT contract (`do()` signature,
choices shape, `triggerParameters` cascade): `references/plugin-params.md`.
The dynamic-SELECT script location differs
by component: `paramsPythonSetup` for recipes, `resource/params_helper.py` for webapps.

Read plugin/tool config at runtime: recipes `get_plugin_config()`; connectors via
`__init__(config, plugin_config)`; webapps `get_webapp_config()`.

## Production patterns

- **P1 Zero-DSS core.** `python-lib/<pkg>/core/` has no dataiku imports; `adapters/` wrap
  dataset/LLM I/O. Components stay thin. Tests import core directly.
- **Config dataclass** with `from_recipe_config(cls, dict)` + `validate()` (fail loud on bad
  values). For webapp+tool dual contexts use a `ContextVar` override for thread-safety.
- **Service factory** `get_service(client=...)` injecting a `LocalClient` that normalizes
  DSS API quirks → business logic stays testable.
- **Streaming large datasets:** set schema from the first chunk, then a **single** persistent
  writer; never mix `write_with_schema()` (truncates) with a separate `get_writer()`.
- **Parallelism:** `ThreadPoolExecutor` + thread-local LLM cache; preserve input order.
- **Error handling:** graceful degradation (primary→fallback LLM, error-result rows),
  `retry_with_backoff` decorator, a `PluginError` base carrying `context`/`cause`.
- **Logging:** `RequestContextFilter` injecting `request_id`/`user` (Flask + tool via
  `log_context()`); redact `password`/`token`/`api_key`/`secret` keys before logging.
- **Mutable config:** plugin params are READ-ONLY at runtime → persist changing config in
  **project variables** (`project.get_variables()` → `setdefault("standard",{})` → set).

## Anti-patterns (fix)

| Wrong | Right |
|---|---|
| `app = Flask(__name__)` in plugin webapp | use DSS-injected `app` (breaks `/__ping`) |
| `from dataiku.webapp import …` | `from dataiku.customwebapp import …` |
| `input.get("query")` in a tool | `input.get("input", {}).get("query")` |
| `trace.set_attribute(k,v)` | `trace.attributes[k]=v` |
| hardcoded dataset / LLM id | read from config (`DATASET`/`LLM` param) |
| load dataset at import time | lazy-load in `@app.before_request` |
| `subprocess.run(...)` no guards | add `stdin=DEVNULL`, `timeout=`, `env CI/TERM=dumb/NO_COLOR` |
| `custom-webapps/` | `webapps/` (DSS won't discover otherwise) |
| Vite default code-splitting | single-bundle output (predictable filenames) |

Deprecated python-client calls → use: `DSSDataset`/`DSSScenario` `get_definition`/
`set_definition` (and `DSSRecipe.get_definition_and_payload`) → `get_settings()` +
`.save()`; code-recipe script access via raw `get_payload`/`set_payload` →
`CodeRecipeSettings.get_code`/`set_code`.

## Testing

Pyramid: unit (fast, mock at DSS boundary) → integration (live DSS via
`dataiku-plugin-tests-utils`) → E2E (Playwright for webapps).

- **Unit:** mock `dataiku` module in `conftest.py` (`patch.dict(sys.modules, {"dataiku": MagicMock()})`);
  fixtures for mock dataset (`get_dataframe`/`read_schema`), mock LLM (`new_completion().execute()`),
  mock api_client. Test business logic in `python-lib` directly; test recipes by patching
  `get_recipe_config`/role helpers/`dataiku.Dataset`. Test tools: `set_config()` then
  `invoke({"input": {...}}, trace)`; assert `{"output": ...}` and missing-param handling.
- **Integration:** session-scoped `dss_client` + `test_project` fixtures from env vars
  (`DSS_HOST`/`DSS_API_KEY`); create recipe via `new_recipe("plugin_recipe")`, run, assert
  `job.get_status() == "DONE"` and non-empty output.
- **CI:** lint (`ruff`) + unit on every PR; integration on main only; package on tags.
- **Debug in DSS:** log to `sys.stderr` (DSS captures it); write intermediate results to a
  debug dataset/folder. Reload (code) vs rebuild code-env (deps) vs reinstall (structure).

## Review checklist (canonical)

Check every anti-pattern row above against each component, plus:

- **Structure:** component dirs kebab-case; each component has BOTH its `*.json` and
  `*.py`; tests in `tests/unit/` and/or `tests/integration/`.
- **Agent tools:** `tool.json` schema matches `get_descriptor()`; description is
  LLM-clear; SQL-executing tools carry `enduser_sql_execution` for identity delegation.
  *Agentic (internal-loop) tools:* `@tool` (NOT `BaseAgentTool`), configurable
  `recursion_limit`, state in a dataclass not globals, `LangchainToDKUTracer` bridges
  callbacks→trace, `langgraph`+`langchain-core` pinned.
- **Recipes:** `recipe.json` roles match `recipe.py`; empty-dataset safe.
- **Guardrails:** `trace.subspan()` per check; checks query AND response.
- **Webapps:** review against `references/webapps.md` (backend rule, `webapp.json`
  keys, pitfalls table).
- **Code env:** `desc.json` interpreter matches target DSS.
- **Code quality:** `[Component]` log prefix; no hardcoded creds/URLs/ids; clean
  imports; consistent error handling; tests cover key paths.

**Severity:** `critical` = runtime error / security / data loss; `warning` = confusion /
maintenance burden / subtle bug; `info` = style/naming/minor.

**Score /10:** 9–10 production-ready · 7–8 minor fixes · 5–6 significant gaps · 3–4
multiple critical issues · 1–2 fundamentally broken.
