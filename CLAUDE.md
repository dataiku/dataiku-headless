# CLAUDE.md — Dataiku DevKit

## Mission

**This repo exists to make AI coding agents excellent at operating Dataiku DSS.** Every change — CLI code, skill docs, error messages, tests — is evaluated by one question: *does this make agents more successful?*

We ship two components that work together:

1. **`dku` CLI** — a `kubectl`-style tool (167 commands, 28 groups) wrapping `dataikuapi`. Replaces throwaway Python scripts with composable shell commands agents chain with `&&`.

2. **Agent skills & knowledge** — 2 skills, 28 reference docs, and 3 subagents that teach agents how to operate DSS. The skill (`SKILL.md`) is the first thing agents read — it must steer them right on the first pass.

**NOT on PyPI.** Install from GitHub source only — see [Distribution](#distribution).

---

## Strategy: How We Make Agents Better

### 1. Progressive Disclosure in Skills

The skill is what gets loaded when any agent is asked to do anything in Dataiku. It follows a strict progressive disclosure pattern:

```
SKILL.md cheat sheet (6 rules)        ← Agent reads this ALWAYS (first 30 lines)
  → SKILL.md full reference            ← Agent reads relevant sections on-demand
    → references/*.md (28 docs)        ← Deep platform knowledge, read when building plugins/recipes/etc.
```

**The cheat sheet is the most important text in this repo.** If an agent only reads 30 lines, those 30 lines must prevent the top 6 failure modes. Every benchmark failure should make you ask: "Could a cheat sheet rule have prevented this?"

### 2. CLI as Agent Co-Pilot

The CLI is the agent's hands. Every command must:

- **`--help` is documentation.** Agents read `--help` before docs. Descriptions must explain WHEN to use the command, not just WHAT it does. Include gotcha warnings directly in help text.
- **Error messages are instructions.** When a command fails, the error must tell the agent exactly what to do next — the correct command, the missing flag, the alternative approach. Never just "error occurred".
- **Suggest built-in alternatives.** If an agent is reaching for Python when a visual recipe exists, the CLI should say so. Error messages and help text actively steer toward DSS built-in features.
- **Idempotent where possible.** `--if-not-exists` on creation commands. Clear messages on conflicts. Safe to re-run.

### 3. Built-In Features First

DSS is a platform with 50+ visual recipes, AutoML, agents, knowledge banks, and more. **Python is the escape hatch, not the default.** The skill and CLI must steer agents toward built-in capabilities:

| Priority | Capability | Python instead? |
|----------|-----------|-----------------|
| 1 | Visual recipes (join, group, stack, filter, sort, distinct, window, topn) | NEVER |
| 2 | GenAI recipes (embed, embed-docs, extract, LLM eval, agent eval) | Only if recipe type doesn't exist |
| 3 | AutoML (visual ML, prediction, clustering) | Only for custom architectures |
| 4 | Agents & Knowledge Banks | Only for custom logic beyond tool-calling |
| 5 | Scenarios & automation | Only for complex conditional logic |
| 6 | SQL recipes | When SQL is cleaner than visual |
| 7 | Python/R recipes | **ONLY when nothing above fits** |

### 4. Gotchas in Three Places

Every production gotcha must be documented in ALL THREE:

1. **CLI error message** (`errors.py` / command `except` blocks) — agent sees this at failure time, must include the fix command
2. **Skill cheat sheet or gotchas table** (`skills/dku-cli/SKILL.md`) — agent sees this before attempting, prevents the failure
3. **CLAUDE.md Critical Gotchas** (below) — YOU see this when writing code, prevents introducing the bug

If a gotcha only exists in one place, it will be missed. The CLI error is for recovery. The skill is for prevention. CLAUDE.md is for development.

### 5. Benchmark-Driven Improvement

The 9-tier benchmark (192 scenarios) is how we measure agent success. Every code change should either:
- Fix a benchmark failure (most common)
- Prevent a class of failures (error handling, skill guidance)
- Enable a new capability (new commands, new recipe types)

See `benchmark/README.md` for architecture and tiers.

---

## Development Workflow

When you receive benchmark feedback:

1. **Capability check first** — For every Python recipe the agent wrote, ask: could a visual recipe, model, agent, or knowledge bank do this? If yes, the fix is in skill docs, not CLI code.
2. **Categorize**: built-in capability gap > CLI bug > skill doc gap > test gap > not actionable
3. **Fix in all three places** — CLI error message + skill doc + CLAUDE.md gotcha
4. **Verify against `dataikuapi`** — Never invent APIs. Read the source in `.venv/lib/*/dataikuapi/`.
5. **Run tests** — `uv run pytest -v` (523 tests, all must pass)
6. **Check `--help`** — `uv run dku <command> --help` must read well to an agent

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

**Branding:** Uses `◆` (black diamond) as icon. Must wrap in Rich markup (`[blue bold]◆[/blue bold]`) in Typer help strings or Typer strips it.

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
| `errors.py` | `dataikuapi` exception → user-friendly message + exit code. **Every error must tell the agent what to do next.** |
| `commands/*.py` | One file per noun. Never touches presentation directly — always uses `output.py` |

### Command Groups (31 + whoami)

| Group | File | Commands |
|---|---|---|
| `auth` | `auth_cmd.py` | login, logout, status, list, switch |
| `config` | `config_cmd.py` | set, get, list, path, variables, set-variables |
| `project` | `project.py` | list, get, export, create, delete, duplicate, set-metadata, variables, set-variables, permissions, set-permissions, tags |
| `dataset` | `dataset.py` | list, schema, head, build, create, upload, delete, clear, get-definition, set-definition, set-schema |
| `recipe` | `recipe.py` | list, get, run, create, delete, set-code, get-code, set-definition, add-input, add-output, check-schema, apply-schema, list-steps, add-step, remove-step, get-step, enable-step, disable-step, add-formula, add-rename, add-filter-rows, add-fill-empty, add-delete-columns, add-find-replace, create-join, create-group, create-stack, create-distinct, create-sort, create-filter, create-window, create-split, create-topn, create-embed, create-embed-docs, create-extract, create-llm-eval, create-agent-eval |
| `scenario` | `scenario.py` | list, run, abort, status, create, delete, get-definition, set-definition |
| `job` | `job.py` | list, run, status, log, abort, wait |
| `plugin` | `plugin.py` | list, push, settings |
| `code-env` | `codeenv.py` | list, get, create, delete, update |
| `connection` | `connection.py` | list, create, test |
| `model` | `model.py` | list, get, versions, set-active-version, metrics, delete-version |
| `ml` | `ml.py` | create-prediction, create-clustering, create-timeseries, create-causal, list, status, train, models, details, deploy, redeploy, settings, algorithms, set-algorithm, delete |
| `analysis` | `analysis.py` | list, create, get, delete, tasks |
| `evaluation-store` | `evaluation_store.py` | list, create, get, evaluations, latest, build, delete |
| `folder` | `folder.py` | list, ls, upload, download |
| `llm` | `llm.py` | list, completion, embeddings |
| `webapp` | `webapp.py` | list, start, stop, status, get-definition, set-definition |
| `dashboard` | `dashboard.py` | list, get, create, delete, get-definition, set-definition |
| `insight` | `insight.py` | list, get, create, delete, get-definition, set-definition |
| `macro` | `macro.py` | list, run |
| `user` | `user.py` | list, create |
| `flow` | `flow.py` | graph, zones, create-zone, move, propagate, check, sources, successors |
| `library` | `library.py` | list, read, write, delete, mkdir |
| `agent` | `agent.py` | list, create, get, delete, wake-up, shutdown, status, add-tool, set-prompt, set-llm |
| `agent-block` | `agent_block.py` | list, get, add, remove, connect, disconnect, set-start, set-mode, get-graph, set-graph |
| `agent-tool` | `agent_tool.py` | list, get, run, create, types, delete |
| `knowledge` | `knowledge.py` | list, create, get, build, search, delete |
| `bundle` | `bundle.py` | list, export, download, import, activate |
| `api-service` | `api_service.py` | list, create, get, create-package, list-packages |
| `wiki` | `wiki.py` | list, create, get, update, delete |
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
- **Error messages are prescriptive** — every `except` block must tell the agent the next command to run, not just what went wrong. Use `exit_with_error()` with `details=[]` for multi-line guidance.
- **Agent commands resolve by name or ID** — `helpers.resolve_agent()` tries `get_agent(ref)` first (by ID), falls back to `list_agents()` name match. All agent commands use this.
- **Text input helper** — `helpers.read_text_input(value)` reads from literal string, `@file.txt`, or stdin (`-`). Used by `set-prompt`, same pattern as `set-code`.

---

## DevKit: Skills, Agents & Plugin

The DevKit layer lives alongside the CLI source — skills, agents, and reference docs that any AI coding agent auto-discovers:

```
skills/                    # Skills (auto-discovered by Claude Code, Codex, Cursor, etc.)
├── dataiku/               # Platform knowledge router (28 reference docs incl. scaffolding)
│   ├── SKILL.md           # Routes to correct reference doc based on task
│   └── references/*.md    # Deep platform knowledge (progressive disclosure layer 3)
└── dku-cli/               # CLI operations and composability patterns
    ├── SKILL.md           # THE primary agent interface — cheat sheet + patterns + gotchas
    └── references/        # CLI command reference
agents/                    # Subagents for complex tasks
├── plugin-reviewer.md     # Deep plugin code review
├── dss-explorer.md        # Explore DSS projects via CLI
└── tool-designer.md       # Design agent tool schemas
.claude-plugin/            # Plugin manifest for Claude Code marketplace
```

### Skill Quality Standards

When editing `skills/dku-cli/SKILL.md`:

- **Cheat sheet** (top 30 lines): Must prevent the top failure modes. One line per rule. If you add a gotcha to CLAUDE.md, ask: does the cheat sheet need a rule too?
- **Examples**: Every example must be copy-paste-runnable. Include `-P PROJ` and all required flags.
- **Gotchas table**: Scannable — symptom in one column, fix in another. Agents pattern-match on error messages.
- **Reference docs**: Only for deep knowledge the agent doesn't need on every task. Don't bloat the skill with info that belongs in `references/`.

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
| `skills/dataiku/references/structured-agents.md` | SVA design guide: all 13 block types, graph patterns, state, CLI workflow |
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
| `skills/dataiku/references/scaffolding.md` | Plugin scaffolding, adding components, deploying, reviewing |
| `skills/dataiku/references/prepare-processors.md` | ~95 Prepare recipe processor types: type IDs, params, examples |

---

## Critical Gotchas

These are real production bugs that have caused hours of debugging. They're here so you never introduce them, and so you always handle them in CLI error messages AND skill docs.

**Rule: Every gotcha below MUST also exist in `skills/dku-cli/SKILL.md` gotchas table AND be caught with a prescriptive error message in the CLI code.**

### Dataset Create + Upload (CLI)

**`dku dataset create` defaults to Filesystem type, which does NOT support `dku dataset upload`.** You MUST specify `--type UploadedFiles` for datasets that will receive file uploads:

```bash
# WRONG — creates Filesystem dataset, upload will fail
dku dataset create my_data -P PROJ
dku dataset upload my_data data.csv -P PROJ   # ERROR: upload not supported

# RIGHT — UploadedFiles type supports upload
dku dataset create my_data --type UploadedFiles -P PROJ
dku dataset upload my_data data.csv -P PROJ   # Works
```

Use Filesystem (default) for recipe outputs that are built, not uploaded. Use UploadedFiles for anything you're uploading via CLI.

`dku dataset delete` and `dku project delete` do not have `--yes` or `-y` flags. For non-interactive deletion, pipe: `echo y | dku dataset delete NAME -P PROJ`.

### Code Recipe Create + Connection (CLI)

**`dku recipe create` for code recipes (python, sql, r, shell, pyspark) fails if the DSS project has no default managed connection.** The error is: `"Need to create output dataset or folder, but creationInfo params are suppressing it"`. Fix: add `--connection` / `-c` to specify where the output dataset is stored:

```bash
# WRONG — fails if no default managed connection on the project
dku recipe create my_step -t python -i input_ds --output-ds output_ds -P PROJ

# RIGHT — explicitly specify the connection
dku recipe create my_step -t python -i input_ds --output-ds output_ds -c filesystem_managed -P PROJ
```

Use `dku connection list` to find available connections. `filesystem_managed` is the most common default. Visual recipes (`create-join`, `create-group`, etc.) don't need `--connection` — they use `with_existing_output()` and require the output dataset to already exist.

**CLI handling:** `recipe.py` catches `is_connection_required_error()` and suggests the `--connection` flag with an example command.

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

### GREL Formula Quirks

- **`log()` = base-10 logarithm.** There is NO `ln()` function. Use `log(x) * 2.302585092994046` for natural log.
- **`exp()` IS base-e** (inconsistent with `log()`).
- **`numval()` / `val()` DO NOT WORK** for type conversion. Direct arithmetic auto-coerces: `"123" * 2` → `246`.
- **Prepare recipe formula columns default to STRING type.** Downstream SUM/AVG will produce corrupt results. Always run `apply-schema` after adding formula steps, or use `--auto-update-schema` on build.

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
| Block graph is inside `toolsUsingAgentSettings`, not separate type | `mode: "BLOCKS_GRAPH"` + `blocks: [...]` + `startingBlockId` |
| No public API for webapp creation or deletion | DSS UI only — but `get_settings()`/`save()` works for editing |
| Webapp code lives in `get_settings().get_raw()["params"]` | `webapp.py` — keys: `html`, `css`, `js`, `python` |
| `list_dashboards()` returns dicts | `dashboard.py` — accesses via `.get()` |
| `create_dashboard()` returns object with `.dashboard_id` | `dashboard.py` — NOT `.id` |
| `list_insights()` returns dicts | `insight.py` — accesses via `.get()` |
| `create_insight()` takes `creation_info` dict, not name string | `insight.py` — builds `{"type": T, "name": N}` |
| `DSSInsight` uses `.insight_id` not `.id` | `insight.py` — matches `DSSDashboard.dashboard_id` pattern |
| Insight `settings.save()` uses POST not PUT | `dataikuapi` handles internally — wraps as `{"insight": settings}` |
| Knowledge Bank access needs `.as_core_knowledge_bank()` | See `skills/dataiku/references/recipes.md` |
| No public eval recipe builder with eval-store output | `recipe.py` — uses `client._perform_json()` |
| `get_knowledge_bank().get_settings()` hides raw JSON | `knowledge.py` — uses `client._perform_http()` |
| `get_definition()`/`set_definition()` deprecated on Dataset, Scenario | CLI still uses them (works) — replacement: `get_settings()`/`save()` |
| `client.get_variables()`/`set_variables()` deprecated | CLI still uses them — replacement: `get_global_variables()` handle |
| `get_payload()`/`set_payload()` deprecated on CodeRecipeSettings | Replacement: `get_code()`/`set_code()` |
| `CodeRecipeCreator` has no `with_existing_output()` | `recipe.py` — uses `with_new_output_dataset(name, connection)` when `--connection` provided, `with_output(name)` otherwise |
| `PrepareRecipeSettings.raw_steps` raises KeyError on non-prepare | `recipe.py` — `_get_prepare_settings()` validates type before accessing |
| `obj_payload` may be None on fresh prepare recipes | `recipe.py` — `_ensure_steps_array()` defensively initializes `{"steps": []}` |
| `WindowRecipeSettings` has no helper methods (just `pass`) | `recipe.py` — manipulates `obj_payload` directly for `partitioningColumns` and `orders` |
| `DSSFlowZone.add_item()` accepts dataset/recipe/folder/model objects | `flow.py` — resolves via `proj.get_dataset(name)` etc. before passing to zone |
| `DSSAgent.status()` NOT `get_status()` | `agent.py` — uses `agent.status()`. Different from `DSSJob.get_status()` |
| `get_agent(id)` is lazy — no API call | `helpers.py` — `resolve_agent()` calls `get_settings()` to verify existence |
| `new_agent_tool()` returns builder, NOT tool | `agent_tool.py` — must call `.create()` on builder |
| `VectorStoreSearch` creator has `.with_knowledge_bank()` | `agent_tool.py` — only subclass with extra builder method |
| `systemPrompt` inside `toolsUsingAgentSettings` | `agent.py` — `set-prompt` writes to `ver_raw["toolsUsingAgentSettings"]["systemPrompt"]` |
| `create_prediction_ml_task()` blocks during guess (5-30s) | `ml.py` — `wait_guess_complete=True` is default, correct for CLI |
| `mltask.train()` blocks; `start_train()` is async | `ml.py` — `--wait` (default) uses `.train()`, `--no-wait` uses `.start_train()` |
| `DSSMLTask` stores `.analysis_id` and `.mltask_id` | `ml.py` — both needed for subsequent commands, returned by create-* |
| `deploy_to_flow()` returns dict `{savedModelId, trainRecipeName}` | `ml.py` — rendered directly |
| `set_active_version()` returns None (`_perform_empty`) | `model.py` — just output success message |
| `list_model_evaluation_stores()` returns objects (not dicts) | `evaluation_store.py` — accesses `.id` property |
| `DSSModelEvaluation` has `.evaluation_id` property | `evaluation_store.py` — not `.id` |
| `DSSEvaluationStore.build()` has `wait=True` default | `evaluation_store.py` — maps to `--wait/--no-wait` flag |

---

## Command → dataikuapi Mapping

See `docs/command-api-mapping.md` for the full table mapping every CLI command to its `dataikuapi` call.

---

## Testing

```bash
uv run pytest -v    # 523 tests
```

- Unit tests mock `DSSClient` via `conftest.py` fixtures (`mock_client`, `patch_client`)
- `patch_client` patches `dku_cli.client.get_client` AND `dku_cli.helpers.get_client`
- Use `typer.testing.CliRunner` for CLI invocation tests
- Pass `--project PROJ1` in tests instead of patching `resolve_project`
- Test both table and JSON output modes
- **Test error messages too** — verify agents get prescriptive guidance on failure
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
| **Direct** | `uv tool install git+https://github.com/dataiku/dataiku-cli.git` |
| **Local dev** | `uv tool install --from . dku-cli` |

**Dataiku DevKit (AI agent skills):**

| Channel | Command |
|---------|---------|
| **Claude Code Plugin** | `/plugin marketplace add dataiku/dataiku-cli` |
| **skills.sh (40+ agents)** | `npx skills add dataiku/dataiku-cli --all` |

---

## Docs Index

| Doc | Description |
|-----|-------------|
| `docs/command-api-mapping.md` | Full table mapping every CLI command to its `dataikuapi` call |
| `docs/block-graph-api.md` | Undocumented block graph API — all 13 block types, connection model, state/scratchpad |
| `benchmark/README.md` | Benchmark framework architecture, test tiers, how to run |
| `skills/dku-cli/references/commands.md` | Full CLI command reference with flags and examples |
| `skills/dataiku/references/*.md` | 29 platform reference docs — see [Dataiku Reference Docs](#dataiku-reference-docs) table above |
| `docs/prepare-recipe-audit.md` | Prepare recipe deep dive: dataikuapi API surface, processor catalog, CLI design |
