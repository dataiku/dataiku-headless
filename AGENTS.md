# AGENTS.md — dku-cli

## What This Is

`dku-cli` is a developer CLI for Dataiku DSS — a `kubectl`-style tool that wraps `dataikuapi` with auth management, output formatting, and discoverability. It replaces throwaway Python scripts with composable shell commands.

**Who it serves:** Developers, admins, field engineers, CI/CD pipelines — anyone who interacts with DSS programmatically.

**Branding:** Uses `◆` (black diamond) as icon, like Vercel's `▲`. Renders universally without Nerd Fonts. Must wrap in Rich markup (`[blue bold]◆[/blue bold]`) in Typer help strings or Typer strips it.

---

## Architecture

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
| `output.py` | All rendering: `render()` for table/json/csv, `success()`/`error()`/`warn()`/`info()` + quiet mode |
| `errors.py` | `dataikuapi` exception → user-friendly message + exit code |
| `commands/*.py` | One file per noun. Never touches presentation directly — always uses `output.py` |

### Command Groups (26 + whoami)

| Group | File | Commands |
|---|---|---|
| `auth` | `auth_cmd.py` | login, logout, status, list, switch |
| `config` | `config_cmd.py` | set, get, list, path, variables, set-variables |
| `project` | `project.py` | list, get, export, create, delete, duplicate, variables, set-variables, permissions, set-permissions, tags |
| `dataset` | `dataset.py` | list, schema, head, build, create, upload, delete, clear, get-definition, set-definition, set-schema |
| `recipe` | `recipe.py` | list, get, run, create, delete, set-code, get-code, set-definition, add-input, add-output |
| `scenario` | `scenario.py` | list, run, abort, status, create, delete, get-definition, set-definition |
| `job` | `job.py` | list, status, log, abort, wait |
| `plugin` | `plugin.py` | list, push, settings |
| `code-env` | `codeenv.py` | list, get, create, delete, update |
| `connection` | `connection.py` | list, create, test |
| `model` | `model.py` | list, get, versions |
| `folder` | `folder.py` | list, ls, upload, download |
| `llm` | `llm.py` | list, completion, embeddings |
| `webapp` | `webapp.py` | list, start, stop, status |
| `macro` | `macro.py` | list, run |
| `user` | `user.py` | list, create |
| `flow` | `flow.py` | graph, zones, create-zone, propagate, sources, successors |
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

## Dataiku Reference Docs (read on-demand)

Read the relevant doc BEFORE working on that topic. Don't read all of them.

### Plugin Development

| Document | Read when... |
|----------|--------------|
| `docs/dataiku-plugins/index.md` | Starting any plugin work, need the big picture |
| `docs/dataiku-plugins/plugin-structure.md` | Creating a new plugin, plugin.json anatomy |
| `docs/dataiku-plugins/recipes.md` | Building custom recipes, dataset operations |
| `docs/dataiku-plugins/webapps.md` | Building webapp dashboards (Flask/Vue/React) |
| `docs/dataiku-plugins/llm-tools.md` | Creating agent tools, custom agents |
| `docs/dataiku-plugins/parameters.md` | Defining plugin parameters (30+ types) |
| `docs/dataiku-plugins/code-environments.md` | Python dependency management, code env config |
| `docs/dataiku-plugins/datasets.md` | Building dataset connectors |
| `docs/dataiku-plugins/macros.md` | Building runnables/macros |
| `docs/dataiku-plugins/testing.md` | Unit/integration/E2E testing patterns |
| `docs/dataiku-plugins/best-practices.md` | Architecture, error handling, performance |

### Dataiku Platform

| Document | Read when... |
|----------|--------------|
| `docs/dataiku-reference.md` | Need quick reference for DSS concepts and operations |
| `docs/genai-features.md` | Working on LLM/GenAI commands, need to understand LLM Mesh/Knowledge Banks/Agents |

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

- **Trace API**: Use `trace.add_metadata(key, value)` — NOT `trace.set_attribute()` (that's OpenTelemetry, not DSS)
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
| `list_code_envs()` returns dicts | `codeenv.py` — accesses via `.get()` |
| `get_code_env()` requires `lang` + `name` | `codeenv.py` — defaults `--lang PYTHON` |
| `list_connections()` is admin-only | `connection.py` — catch 403 |
| `list_managed_folders()` returns dicts with `id` key | `folder.py` — accesses via `.get()` |
| LLM completion uses builder pattern | `llm.py` — `new_completion().with_message().execute()` |
| Project metadata requires separate `get_metadata()` call | `project.py` — fetches per project |
| Auth info via `get_auth_info()` returns dict | `auth_cmd.py`, `main.py` (whoami) |
| No public API for webapp creation | DSS UI only |
| `uploaded_add_file()` returns None | `dataset.py` — no result check |
| `project.list_webapps()` and `project.get_webapp()` exist, no create | `webapp.py` — list/start/stop only |
| Knowledge Bank access needs `.as_core_knowledge_bank()` | See `docs/dataiku-plugins/recipes.md` |

---

## Command → dataikuapi Mapping

| CLI Command | dataikuapi Call |
|---|---|
| `dku project list` | `client.list_project_keys()` + `get_project().get_metadata()` |
| `dku project get KEY` | `get_project(KEY).get_metadata()` + `.get_status()` |
| `dku project export KEY` | `get_project(KEY).export_to_file()` |
| `dku project create KEY` | `client.create_project(key, name, owner, description)` |
| `dku project delete KEY` | `get_project(KEY).delete()` |
| `dku project duplicate KEY` | `get_project(KEY).duplicate(target_project_key, target_project_name)` |
| `dku project variables` | `get_project(KEY).get_variables()` |
| `dku project set-variables` | `get_project(KEY).set_variables(obj)` |
| `dku project permissions` | `get_project(KEY).get_permissions()` |
| `dku project set-permissions` | `get_project(KEY).set_permissions(perms)` |
| `dku project tags` | `get_project(KEY).get_metadata()` → `.tags` |
| `dku dataset list` | `project.list_datasets()` |
| `dku dataset schema NAME` | `get_dataset(NAME).get_definition()` |
| `dku dataset head NAME` | `get_dataset(NAME).iter_rows()` |
| `dku dataset build NAME` | `get_dataset(NAME).build()` |
| `dku dataset create NAME` | `project.create_dataset(name, type, params)` |
| `dku dataset upload NAME FILE` | `get_dataset(NAME).uploaded_add_file(fp, filename)` |
| `dku dataset delete NAME` | `get_dataset(NAME).delete()` |
| `dku dataset clear NAME` | `get_dataset(NAME).clear()` |
| `dku dataset get-definition` | `get_dataset(NAME).get_definition()` |
| `dku dataset set-definition` | `get_dataset(NAME).set_definition(def)` |
| `dku dataset set-schema` | `get_dataset(NAME).get_definition()` → update schema → `set_definition()` |
| `dku recipe list` | `project.list_recipes()` |
| `dku recipe get NAME` | `get_recipe(NAME).get_settings().get_recipe_raw_definition()` |
| `dku recipe run NAME` | `get_recipe(NAME).run()` |
| `dku recipe create NAME` | `project.new_recipe(type, name).with_input().with_existing_output().build()` |
| `dku recipe delete NAME` | `get_recipe(NAME).delete()` |
| `dku recipe set-code NAME` | `get_recipe(NAME).get_settings().set_payload(code)` → `.save()` |
| `dku recipe get-code NAME` | `get_recipe(NAME).get_settings().get_payload()` |
| `dku recipe set-definition` | `get_recipe(NAME).get_settings().get_recipe_raw_definition().update()` → `.save()` |
| `dku recipe add-input NAME` | `get_recipe(NAME).get_settings().add_input(role, ref)` → `.save()` |
| `dku recipe add-output NAME` | `get_recipe(NAME).get_settings().add_output(role, ref)` → `.save()` |
| `dku scenario list` | `project.list_scenarios()` |
| `dku scenario run ID` | `get_scenario(ID).run()` |
| `dku scenario abort ID` | `get_scenario(ID).abort()` |
| `dku scenario status ID` | `get_scenario(ID).get_last_runs()` |
| `dku scenario create NAME` | `project.create_scenario(name, type, definition)` |
| `dku scenario delete ID` | `get_scenario(ID).delete()` |
| `dku scenario get-definition` | `get_scenario(ID).get_definition().get_raw()` |
| `dku scenario set-definition` | `get_scenario(ID).set_definition(def)` |
| `dku job list` | `project.list_jobs()` |
| `dku job status ID` | `get_job(ID).get_status()` |
| `dku job log ID` | `get_job(ID).get_log()` |
| `dku job abort ID` | `get_job(ID).abort()` |
| `dku job wait ID` | `get_job(ID).get_status()` (poll loop) |
| `dku plugin list` | `client.list_plugins()` |
| `dku plugin push ZIP` | `plugin.update_from_zip()` or `install_plugin_from_archive()` |
| `dku plugin settings ID` | `plugin.get_settings().get_raw()` |
| `dku code-env list` | `client.list_code_envs()` |
| `dku code-env get NAME` | `client.get_code_env(lang, name).get_definition()` |
| `dku code-env create NAME` | `client.create_code_env()` |
| `dku code-env delete NAME` | `get_code_env().delete()` |
| `dku code-env update NAME` | `get_code_env().update_packages()` |
| `dku connection list` | `client.list_connections()` |
| `dku connection create NAME` | `client.create_connection(name, type, params)` |
| `dku connection test NAME` | `get_connection(NAME).test()` |
| `dku model list` | `project.list_saved_models()` |
| `dku model get ID` | `get_saved_model(ID).get_status()` |
| `dku model versions ID` | `get_saved_model(ID).list_versions()` |
| `dku folder list` | `project.list_managed_folders()` |
| `dku folder ls ID` | `get_managed_folder(ID).list_contents()` |
| `dku folder upload ID FILE` | `get_managed_folder(ID).put_file()` |
| `dku folder download ID PATH` | `get_managed_folder(ID).get_file()` |
| `dku llm list` | `project.list_llms()` |
| `dku llm completion ID MSG` | `get_llm(ID).new_completion().with_message().execute()` |
| `dku llm embeddings ID` | `get_llm(ID).new_embeddings().with_text().execute()` |
| `dku webapp list` | `project.list_webapps()` |
| `dku webapp start ID` | `get_webapp(ID).start_or_restart_backend()` |
| `dku webapp stop ID` | `get_webapp(ID).stop_backend()` |
| `dku webapp status ID` | `get_webapp(ID).get_state()` |
| `dku macro list` | `project.list_macros()` |
| `dku macro run ID` | `get_macro(ID).run()` |
| `dku user list` | `client.list_users()` |
| `dku user create LOGIN` | `client.create_user(login, password, display_name, email, groups)` |
| `dku flow graph` | `get_flow().get_graph()` |
| `dku flow zones` | `get_flow().list_zones()` |
| `dku flow create-zone NAME` | `get_flow().create_zone(name)` |
| `dku flow propagate` | `get_flow().start_schema_propagation().start().wait_for_result()` |
| `dku flow sources` | `get_flow().get_graph()` → find nodes with no upstream |
| `dku flow successors NODE` | `get_flow().get_graph().get_successors(node)` |
| `dku library list` | `get_project().get_library().list_contents(path)` |
| `dku library read PATH` | `get_project().get_library().get_file(path)` |
| `dku library write PATH` | `get_project().get_library().put_file(path, data)` |
| `dku library delete PATH` | `get_project().get_library().delete_file(path)` |
| `dku library mkdir PATH` | `get_project().get_library().add_folder(path)` |
| `dku agent list` | `project.list_agents()` |
| `dku agent create NAME` | `project.create_agent(name)` |
| `dku agent get ID` | `get_agent(ID).get_settings().get_raw()` |
| `dku agent delete ID` | `get_agent(ID).delete()` |
| `dku agent wake-up ID` | `get_agent(ID).wake_up()` |
| `dku agent shutdown ID` | `get_agent(ID).shutdown()` |
| `dku agent status ID` | `get_agent(ID).get_status()` |
| `dku agent add-tool ID` | `get_agent(ID).get_settings()` → modify tools → `.save()` |
| `dku agent set-llm ID` | `get_agent(ID).get_settings()` → set llmId → `.save()` |
| `dku agent-tool list` | `project.list_agent_tools()` |
| `dku agent-tool get ID` | `get_agent_tool(ID).get_settings().get_raw()` |
| `dku agent-tool run ID` | `get_agent_tool(ID).run(input)` |
| `dku agent-tool delete ID` | `get_agent_tool(ID).delete()` |
| `dku knowledge list` | `project.list_knowledge_banks()` |
| `dku knowledge create NAME` | `project.create_knowledge_bank(name)` |
| `dku knowledge get ID` | `get_knowledge_bank(ID).get_settings().get_raw()` |
| `dku knowledge build ID` | `get_knowledge_bank(ID).build()` |
| `dku knowledge search ID` | `get_knowledge_bank(ID).search(query, max_documents)` |
| `dku knowledge delete ID` | `get_knowledge_bank(ID).delete()` |
| `dku bundle list` | `project.list_exported_bundles()` |
| `dku bundle export ID` | `project.export_bundle(id)` |
| `dku bundle download ID` | `project.download_exported_bundle_archive_to_file(id, path)` |
| `dku bundle import PATH` | `project.import_bundle_from_archive(f)` |
| `dku bundle activate ID` | `project.preload_bundle(id)` + `project.activate_bundle(id)` |
| `dku api-service list` | `project.list_api_services()` |
| `dku api-service create ID` | `project.create_api_service(id)` |
| `dku api-service get ID` | `get_api_service(ID).get_settings().get_raw()` |
| `dku api-service create-package` | `get_api_service(ID).create_package()` |
| `dku api-service list-packages` | `get_api_service(ID).list_packages()` |
| `dku wiki list` | `get_wiki().list_articles()` |
| `dku wiki create TITLE` | `get_wiki().create_article(title, body)` |
| `dku wiki get ID` | `get_wiki().get_article(id).get_data()` |
| `dku sql query SQL` | `client.sql_query(query, connection)` |
| `dku config set/get` | local config file |
| `dku config variables` | `client.get_variables()` |
| `dku config set-variables` | `client.set_variables(vars)` |
| `dku whoami` | `client.get_auth_info()` |

---

## Testing

```bash
uv run pytest -v    # 247 tests
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

| Channel | Command |
|---------|---------|
| **PyPI** | `pip install dku-cli` / `pipx install dku-cli` / `uv tool install dku-cli` |
| **One-liner** | `curl -fsSL .../install.sh \| bash` |
| **Local dev** | `uv tool install --from . dku-cli` |

Publishing: Create a GitHub Release → `.github/workflows/publish.yml` auto-publishes to PyPI via trusted publishing.
