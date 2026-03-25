# CLAUDE.md — Dataiku DevKit

## What This Is

The **Dataiku DevKit** enables any AI coding agent to do anything in Dataiku DSS. It ships two components:

1. **`dku` CLI** — a `kubectl`-style tool (139 commands, 25 groups) wrapping `dataikuapi` with auth management, output formatting, and composability. Replaces throwaway Python scripts with shell commands that agents chain with `&&`.

2. **Agent skills & knowledge** — 9 skills, 26 platform reference docs, and 3 subagents that teach agents how to build plugins, manage projects, and operate DSS. Works with Claude Code, Codex, Cursor, and any agent that reads SKILL.md files.

**Who it serves:** AI coding agents first, then developers, admins, field engineers, and CI/CD pipelines.

**NOT on PyPI.** Install from GitHub source only — see [Distribution](#distribution).

**Branding:** Uses `◆` (black diamond) as icon, like Vercel's `▲`. Renders universally without Nerd Fonts. Must wrap in Rich markup (`[blue bold]◆[/blue bold]`) in Typer help strings or Typer strips it.

---

## CLI Architecture

```
typer (CLI framework)
  └─ rich (terminal formatting)
  └─ dataikuapi (DSS API client)
  └─ keyring (credential storage)
  └─ platformdirs (config file locations)
  └─ tomli/tomllib (TOML parsing)
```

### Pattern: `dku <noun> <verb>`

Every command follows the same flow:
1. Resolve auth (flags → env → keychain → file) via `helpers.get_client_from_ctx()`
2. Resolve project (flag → env → config) via `helpers.resolve_project()`
3. Call `dataikuapi` methods
4. Format output via `output.py`

### File Layout

| File | Responsibility |
|---|---|
| `main.py` | Root Typer app, global options (`--url`, `--api-key`, `--profile`, `--quiet`), sub-command registration, `whoami` |
| `brand.py` | `◆` icon, `version_string()`, `welcome()`, `status_ok()`/`status_err()` |
| `helpers.py` | `resolve_project()`, `get_client_from_ctx()`, `read_json_input()` — eliminates duplication |
| `config.py` | TOML config read/write via `platformdirs` |
| `auth.py` | Keyring + file fallback credential storage |
| `client.py` | Auth resolution → `DSSClient` factory |
| `output.py` | All rendering: `render()` for table/json/csv, `render_raw()` for single dict/list, `success()`/`error()`/`warn()`/`info()` + quiet mode |
| `errors.py` | `dataikuapi` exception → user-friendly message + exit code |
| `commands/*.py` | One file per noun. Never touches presentation directly — always uses `output.py` |

### Command Groups (25 + whoami)

| Group | File | Commands |
|---|---|---|
| `auth` | `auth_cmd.py` | login, logout, status, list, switch |
| `config` | `config_cmd.py` | set, get, list, path, variables, set-variables |
| `project` | `project.py` | list, get, export, create, delete, duplicate, variables, set-variables, permissions, set-permissions, tags |
| `dataset` | `dataset.py` | list, schema, head, build, create, upload, delete, clear, get-definition, set-definition, set-schema |
| `recipe` | `recipe.py` | list, get, run, create, delete, set-code, get-code, set-definition, add-input, add-output, check-schema, apply-schema, create-embed, create-embed-docs, create-extract, create-llm-eval, create-agent-eval |
| `scenario` | `scenario.py` | list, run, abort, status, create, delete, get-definition, set-definition |
| `job` | `job.py` | list, run, status, log, abort, wait |
| `plugin` | `plugin.py` | list, push, settings |
| `code-env` | `codeenv.py` | list, get, create, delete, update |
| `connection` | `connection.py` | list, create, test |
| `model` | `model.py` | list, get, versions |
| `folder` | `folder.py` | list, ls, upload, download |
| `llm` | `llm.py` | list, completion, embeddings |
| `webapp` | `webapp.py` | list, start, stop, status |
| `macro` | `macro.py` | list, run |
| `user` | `user.py` | list, create |
| `flow` | `flow.py` | graph, zones, create-zone, propagate, check, sources, successors |
| `library` | `library.py` | list, read, write, delete, mkdir |
| `agent` | `agent.py` | list, create, get, delete, wake-up, shutdown, status, add-tool, set-llm |
| `agent-tool` | `agent_tool.py` | list, get, run, delete |
| `knowledge` | `knowledge.py` | list, create, get, build, search, delete |
| `bundle` | `bundle.py` | list, export, download, import, activate |
| `api-service` | `api_service.py` | list, create, get, create-package, list-packages |
| `wiki` | `wiki.py` | list, create, get |
| `sql` | `sql.py` | query |
| (root) | `main.py` | whoami |

---

## Development Conventions

- **One file per noun** in `commands/`. File named `{noun}.py` (except `auth_cmd.py` and `config_cmd.py` to avoid stdlib collisions).
- **All formatting through `output.py`** — command modules never import `rich` directly.
- **Project resolution** via `helpers.resolve_project()`: `--project` flag → `DKU_PROJECT` env → `config.toml` default → error.
- **Client creation** via `helpers.get_client_from_ctx(ctx)` — extracts global opts from `ctx.obj`.
- **Global options** (`--url`, `--api-key`, `--profile`, `--quiet`) are on the root app and passed via `ctx.obj`.
- **Tests mock `DSSClient`** — no real DSS connection in unit tests. Use `patch_client` fixture.
- **Version** is single-sourced from `src/dku_cli/__init__.py` via `[tool.hatch.version]` in `pyproject.toml`.

---

## DevKit: Skills, Agents & Plugin

The DevKit layer lives alongside the CLI source — skills, agents, and reference docs that any AI coding agent auto-discovers:

```
skills/                    # Skills (auto-discovered by Claude Code, Codex, Cursor, etc.)
├── dataiku/               # Platform knowledge router (26 reference docs)
├── dku-cli/               # CLI operations and composability patterns
├── new-plugin/            # /new-plugin — scaffold a Dataiku plugin
├── new-tool/              # /new-tool — add agent tool to plugin
├── new-recipe/            # /new-recipe — add custom recipe
├── new-webapp/            # /new-webapp — add webapp component
├── new-guardrail/         # /new-guardrail — add LLM guardrail
├── deploy-plugin/         # /deploy-plugin — build + push to DSS
└── review-plugin/         # /review-plugin — code review checklist
agents/                    # Subagents for complex tasks
├── plugin-reviewer.md     # Deep plugin code review
├── dss-explorer.md        # Explore DSS projects via CLI
└── tool-designer.md       # Design agent tool schemas
.claude-plugin/            # Plugin manifest for Claude Code marketplace
```

### Dataiku Reference Docs

Platform knowledge lives in `skills/dataiku/references/`. Read the relevant doc BEFORE working on that topic.

| Document | Read when... |
|----------|--------------|
| `skills/dataiku/references/plugin-structure.md` | Creating a new plugin, plugin.json anatomy |
| `skills/dataiku/references/recipes.md` | Building custom recipes, dataset operations |
| `skills/dataiku/references/webapps.md` | Building webapp dashboards (Flask/Vue/React) |
| `skills/dataiku/references/webapp-pitfalls.md` | Debugging webapp errors, critical mistakes |
| `skills/dataiku/references/llm-tools.md` | Creating agent tools, custom agents |
| `skills/dataiku/references/parameters.md` | Defining plugin parameters (30+ types) |
| `skills/dataiku/references/code-environments.md` | Python dependency management, code env config |
| `skills/dataiku/references/datasets.md` | Building dataset connectors |
| `skills/dataiku/references/macros.md` | Building runnables/macros |
| `skills/dataiku/references/testing.md` | Unit/integration/E2E testing patterns |
| `skills/dataiku/references/best-practices.md` | Architecture, error handling, performance |
| `skills/dataiku/references/plugin-workflow.md` | Git integration, versioning, CI/CD, distribution |
| `skills/dataiku/references/formulas.md` | Formula language, Prepare recipe expressions |
| `skills/dataiku/references/llm-mesh.md` | LLM connections, guardrails, RAG, knowledge banks |
| `skills/dataiku/references/structured-agents.md` | Deterministic blocks, state management, HITL |
| `skills/dataiku/references/python-api.md` | dataiku/dataikuapi packages, dataset I/O, SQL |
| `skills/dataiku/references/scenarios.md` | Automation, triggers, steps, reporters |
| `skills/dataiku/references/mlops.md` | Model lifecycle, drift detection, API Node |
| `skills/dataiku/references/genai-features.md` | LLM Mesh overview, Knowledge Banks, agents |
| `skills/dataiku/references/dataiku-reference.md` | Quick reference for DSS concepts |
| `skills/dataiku/references/styling.md` | Dataiku brand colors, typography, components |
| `skills/dataiku/references/plugin-architecture.md` | Plugin tiers (1-5), patterns/anti-patterns, official docs gaps |
| `skills/dataiku/references/visual-agent-blocks.md` | BlockHandler, block.json, dual-mode components, agent connectors |
| `skills/dataiku/references/webapp-patterns.md` | Advanced: multi-tab dashboards, filters, caching, React+Vite, Chart.js |
| `skills/dataiku/references/agent-tool-patterns.md` | Advanced: subprocess tools, MCP gateway, OAuth, multi-agent, HITL |
| `skills/dataiku/references/plugin-review-checklist.md` | Reviewing plugins, code review criteria, scoring rubric |

---

## Critical Gotchas

These are real production bugs that have caused hours of debugging. They're here so they never happen again.

### Plugin Webapp Backend

**DSS injects `app` (Flask) into `backend.py` globally. NEVER create your own:**

```python
# WRONG — breaks /__ping health check, webapp never starts
app = Flask(__name__)

# RIGHT — just use the DSS-provided app directly
from dataiku.customwebapp import get_webapp_config
from flask import jsonify

@app.route("/api/data")
def get_data():
    config = get_webapp_config()
    ...
```

- Import `from dataiku.customwebapp import get_webapp_config` (NOT `dataiku.webapp`)
- Plugin webapp folder: `webapps/` (NOT `custom-webapps/`)
- `webapp.json` needs: `hasBackend: true`, `noJSSecurity: true`
- Frontend calls backend via: `window.getWebAppBackendUrl!("/api/path")`

### Code Environments on Python 3.11

**NEVER use `installCorePackages: true`** — the `LEGACY_PANDAS023` core set installs `pandas==0.23.4` which fails on Python 3.11. `PANDAS1` also fails.

Working pattern: `installCorePackages: false` + explicit deps in `requirements.txt`:
```
pandas>=2.0,<3
numpy>=1.22,<3
python-dateutil>=2.8,<3
requests>=2.28,<3
```

The `dataiku` runtime imports numpy/pandas/dateutil at module load — you MUST include them even if your plugin doesn't use them directly.

When `create_code_env()` fails, the broken env persists. Delete it before retrying: `ce.delete()` then `plugin.create_code_env()`.

### Agent Tool Patterns

- **Trace API**: Use `trace.attributes[key] = value` (dict assignment) — NOT `trace.set_attribute()` (OpenTelemetry) or `trace.add_metadata()` (undocumented)
- **invoke() input**: Args are at `input.get("input", {})`, not at root of input dict
- **Subprocess tools**: When spawning CLI tools from agent tools, MUST set:
  - `stdin=subprocess.DEVNULL` — prevents blocking on stdin
  - `env["CI"] = "true"` — skips interactive prompts
  - `env["TERM"] = "dumb"` / `env["NO_COLOR"] = "1"` — disables terminal formatting
- DSS runs tools as `dssuser_dataiku` (not `dataiku`). HOME is `/data/home/dssuser_dataiku`
- Tool server processes persist between Quick Test invocations. Stale processes can block new ones

### Plugin Deployment via API

```python
import dataikuapi
client = dataikuapi.DSSClient(DSS_URL, api_key=API_KEY)

# Install new plugin
with open("plugin.zip", "rb") as f:
    client.install_plugin_from_archive(f)

# Update existing plugin
plugin = client.get_plugin("plugin-id")
with open("plugin.zip", "rb") as f:
    plugin.update_from_zip(f)

# Create code env
future = plugin.create_code_env()
result = future.wait_for_result()
```

- `install_plugin_from_archive` fails if plugin dir already exists in `plugins/dev/` — remove it first
- Plugin must NOT be in `plugins/dev/` when installing via API (API puts it in `plugins/installed/`)
- Both `update_from_zip()` and `install_plugin_from_archive()` return None (not a future)
- Async alternatives exist: `start_install_plugin_from_archive()` and `start_update_from_zip()` return `DSSFuture`
- `DSSPlugin.update_code_env()` also returns `DSSFuture` (useful for non-blocking code env rebuilds)
- ZIP must have `plugin.json` at root level (don't zip a wrapper folder)

### Plugin Structure

```
my-plugin-id/
├── plugin.json                          # ID, version, meta, params
├── python-lib/my_plugin_id/             # Core logic (no Dataiku imports)
├── code-env/python/spec/requirements.txt
├── custom-recipes/my-recipe/            # recipe.json + recipe.py
├── python-agent-tools/my-tool/          # tool.json + tool.py
├── webapps/my-webapp/                   # webapp.json + backend.py + resource/
├── python-runnables/my-macro/           # runnable.json + runnable.py
├── python-connectors/my-connector/      # connector.json + connector.py
└── tests/
```

---

## dataikuapi Quirks (Baked Into CLI)

| Quirk | Where Handled |
|---|---|
| `list_plugins()` returns dicts, not objects | `plugin.py` — accesses `p["id"]` |
| `update_from_zip()` returns None | `plugin.py` — no result check |
| `install_plugin_from_archive()` returns None | `plugin.py` — no result check |
| `uploaded_add_file()` returns None | `dataset.py` — no result check |
| `list_code_envs()` returns dicts | `codeenv.py` — accesses via `.get()` |
| `get_code_env()` requires `lang` + `name` | `codeenv.py` — defaults `--lang PYTHON` |
| `list_connections()` is admin-only | `connection.py` — catch 403 |
| `list_managed_folders()` returns dicts with `id` key | `folder.py` — accesses via `.get()` |
| LLM completion uses builder pattern | `llm.py` — `new_completion().with_message().execute()` |
| Project metadata requires separate `get_metadata()` call | `project.py` — fetches per project |
| Auth info via `get_auth_info()` returns dict | `auth_cmd.py`, `main.py` (whoami) |
| Prompt/Classify/Summarize recipes are UI-only | No dataikuapi builder — use UI then `set-definition` |
| `"embed_dataset"` is alias for `"nlp_llm_rag_embedding"` | `recipe.py` — uses canonical name |
| Eval recipe payload config is post-build | `recipe.py` — `build()` first, then `settings.obj_payload[key] = val` + `save()` |
| `with_output_knowledge_bank()` accepts str/DSSLLM/DSSLLMListItem | `recipe.py` — passes LLM ID string directly |
| No public API for webapp creation | DSS UI only |
| `project.list_webapps()` and `project.get_webapp()` exist, no create | `webapp.py` — list/start/stop only |
| Knowledge Bank access needs `.as_core_knowledge_bank()` | See `skills/dataiku/references/recipes.md` |
| No public eval recipe builder with eval-store output | `recipe.py` — uses `client._perform_json()` |
| `get_knowledge_bank().get_settings()` hides raw JSON | `knowledge.py` — uses `client._perform_http()` |
| `get_definition()`/`set_definition()` deprecated on Dataset, Scenario | CLI still uses them (works) — replacement: `get_settings()`/`save()` |
| `client.get_variables()`/`set_variables()` deprecated | CLI still uses them — replacement: `get_global_variables()` handle |
| `get_payload()`/`set_payload()` deprecated on CodeRecipeSettings | Replacement: `get_code()`/`set_code()` |

---

## Command → dataikuapi Mapping

See `docs/command-api-mapping.md` for the full table mapping every CLI command to its `dataikuapi` call.

---

## Testing

```bash
uv run pytest -v    # 298 tests
```

- Unit tests mock `DSSClient` via `conftest.py` fixtures (`mock_client`, `patch_client`)
- `patch_client` patches `dku_cli.client.get_client` AND `dku_cli.helpers.get_client`
- Use `typer.testing.CliRunner` for CLI invocation tests
- Pass `--project PROJ1` in tests instead of patching `resolve_project`
- Test both table and JSON output modes
- No real DSS connection required

---

## Build, Install & Publish

```bash
uv sync                    # Install deps
uv run dku                 # Run locally
uv build                   # Build wheel
uv run pytest -v           # Run tests
```

### Distribution

**CLI (Python package) — NOT on PyPI. Install from GitHub source:**

| Channel | Command |
|---------|---------|
| **One-liner** | `curl -fsSL .../install.sh \| bash` |
| **Direct** | `uv tool install git+https://github.com/dataiku/dataiku-cli.git` |
| **Local dev** | `uv tool install --from . dku-cli` |

> **Note:** `dku-cli` is not published to PyPI and won't be in the near term. The `install.sh` script and all references install directly from GitHub.

---

## Agent Benchmark

7-tier testing framework (160 scenarios) that evaluates how well AI coding agents use the CLI and DevKit skills against a real DSS sandbox. Head-to-head: Claude Code (Opus) vs Codex (gpt-5.4 xhigh). See `benchmark/README.md` for architecture, test tiers, and how to run.

---

**Dataiku DevKit (AI agent skills):**

| Channel | Command |
|---------|---------|
| **Claude Code Plugin** | `/plugin marketplace add dataiku/dataiku-cli` |
| **skills.sh (40+ agents)** | `npx skills add dataiku/dataiku-cli --all` |
| **Curl installer** | `curl -fsSL .../install-plugin.sh \| bash` |

---

## Docs Index

| Doc | Description |
|-----|-------------|
| `docs/command-api-mapping.md` | Full table mapping every CLI command to its `dataikuapi` call |
| `benchmark/README.md` | Benchmark framework architecture, test tiers, how to run |
| `skills/dku-cli/references/commands.md` | Full CLI command reference with flags and examples |
| `skills/dataiku/references/*.md` | 26 platform reference docs — see [Dataiku Reference Docs](#dataiku-reference-docs) table above |
