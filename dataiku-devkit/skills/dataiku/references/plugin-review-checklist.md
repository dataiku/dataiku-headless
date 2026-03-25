# Plugin Review Checklist

Canonical checklist for reviewing Dataiku DSS plugins. Used by the `plugin-reviewer` agent and the `dataiku` skill's scaffolding workflow.

## Structure
- [ ] `plugin.json` is valid JSON with id, version, meta
- [ ] All component directories follow naming conventions (kebab-case)
- [ ] Each tool has both `tool.py` and `tool.json`
- [ ] Each recipe has both `recipe.py` and `recipe.json`
- [ ] Each guardrail has both `guardrail.py` and `guardrail.json`
- [ ] `python-lib/` exists for shared code
- [ ] Tests exist in `tests/unit/` and/or `tests/integration/`

Reference: `plugin-structure.md`

## Agent Tools
- [ ] Extends `BaseAgentTool` from `dataiku.llm.agent_tools`
- [ ] `get_descriptor()` returns proper schema with description and inputSchema
- [ ] `set_config()` handles config and plugin_config
- [ ] `invoke()` validates inputs before processing
- [ ] `invoke()` returns `{"output": "..."}` format
- [ ] Inputs accessed via `input.get("input", {})` (NOT at root of input dict)
- [ ] `tool.json` schema matches what `get_descriptor()` returns
- [ ] Tool description is clear and helps the LLM use it correctly
- [ ] Error handling returns user-friendly messages
- [ ] `load_sample_query()` provides Quick Test defaults (if applicable)
- [ ] If tool runs SQL: `enduser_sql_execution` param for security delegation

### Agentic Tools (Internal Agent Loop)
- [ ] Internal tools use `@tool` decorator (NOT `BaseAgentTool`)
- [ ] LangGraph `recursion_limit` is configurable
- [ ] `RuntimeContext` dataclass carries state (not global variables)
- [ ] Caches prevent redundant API calls during agent loop
- [ ] `LangchainToDKUTracer` bridges callbacks → DSS trace
- [ ] `langgraph` + `langchain-core` in `requirements.txt`

Reference: `llm-tools.md`, `agent-tool-patterns.md`

## Recipes
- [ ] Uses `get_recipe_config()`, `get_input_names_for_role()`, `get_output_names_for_role()`
- [ ] `recipe.json` roles match what `recipe.py` expects
- [ ] Handles empty datasets gracefully
- [ ] Writes output with `write_with_schema()`

Reference: `recipes.md`

## Guardrails
- [ ] Extends `BaseGuardrail` from `dataiku.llm.guardrails`
- [ ] Uses trace subspans for observability (`trace.subspan()`)
- [ ] Uses `trace.attributes[key] = value` (NOT `trace.set_attribute()`)
- [ ] Handles both query and response checking
- [ ] Fails safely (blocks on error for security guardrails)

## Webapps
- [ ] NEVER creates `app = Flask(__name__)` — uses DSS-provided `app`
- [ ] Imports from `dataiku.customwebapp` (NOT `dataiku.webapp`)
- [ ] `webapp.json` has `hasBackend: true` and `noJSSecurity: true` if backend is used
- [ ] Webapp folder is `webapps/` (NOT `custom-webapps/`)
- [ ] Frontend uses `window.getWebAppBackendUrl()` for backend calls

Reference: `webapps.md`, `webapp-pitfalls.md`

## Code Environment
- [ ] `desc.json` uses `"installCorePackages": false` (NEVER `true`)
- [ ] `requirements.txt` includes base deps: pandas, numpy, python-dateutil, requests
- [ ] Python interpreter matches target DSS version

Reference: `code-environments.md`

## Code Quality
- [ ] Proper logging with `[Component Name]` prefix
- [ ] No hardcoded credentials or URLs
- [ ] Imports are clean (no unused imports)
- [ ] Consistent error handling patterns
- [ ] Tests cover key paths

## Severity Definitions

| Severity | Meaning |
|----------|---------|
| **critical** | Will cause runtime errors, security issues, or data loss |
| **warning** | Will cause confusion, maintenance burden, or subtle bugs |
| **info** | Style, naming, or minor improvements |

## Scoring Rubric

| Score | Meaning |
|-------|---------|
| 9-10 | Production-ready, no issues |
| 7-8 | Good, minor improvements needed |
| 5-6 | Functional but has significant quality gaps |
| 3-4 | Multiple critical issues |
| 1-2 | Fundamentally broken |
