# CLAUDE.md — Dataiku DevKit

## Quick Start

```bash
uv sync                    # Install deps
uv run pre-commit install  # Install git hooks (commitlint, ruff, whitespace fixes)
uv run pytest -v           # Run tests (all must pass)
uv run ruff check .        # Lint
uv run ruff format .       # Format
uv run dku                 # Run CLI locally
uv build                   # Build wheel
```

## Mission

**This repo exists to make AI coding agents excellent at operating Dataiku DSS.** Every change — CLI code, skill docs, error messages, tests — is evaluated by one question: *does this make agents more successful?*

We ship two components:

1. **`dku` CLI** — a `kubectl`-style tool (~244 commands, 32 groups) wrapping `dataikuapi`. Replaces throwaway Python scripts with composable shell commands agents chain with `&&`.
2. **Agent skills & knowledge** — 2 skills, reference docs, and 3 subagents that teach agents how to operate DSS.

**NOT on PyPI.** Install from GitHub source only — see [Distribution](#distribution).

---

## Strategy

Five levers make agents better:

1. **Progressive disclosure in skills** — Cheat sheet (top 30 lines, always loaded) → full SKILL.md → `references/*.md`. The cheat sheet must prevent the top 6 failure modes.
2. **CLI as agent co-pilot** — `--help` is documentation; error messages are instructions with the fix command; idempotent where possible.
3. **Built-in features first** — Visual recipes > GenAI recipes > AutoML > Agents/Knowledge Banks > Scenarios > SQL > Python. Python is the escape hatch, not the default.
4. **Gotchas in three places** — CLI error message (recovery) + SKILL.md cheat sheet (prevention) + CLAUDE.md below (development). All three or it will be missed.
5. **Benchmark-driven** — 9-tier benchmark (192 scenarios) measures agent success. See `benchmark/README.md`.

---

## Development Workflow

When you receive benchmark feedback:

1. **Capability check first** — Could a visual recipe, model, agent, or knowledge bank replace the Python recipe the agent wrote?
2. **Categorize**: built-in capability gap > CLI bug > skill doc gap > test gap > not actionable
3. **Fix in all three places** — CLI error message + skill doc + CLAUDE.md gotcha
4. **Verify against `dataikuapi`** — Never invent APIs. Read the source in `.venv/lib/*/dataikuapi/`.
5. **Run tests** — `uv run pytest -v`

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

**31 command groups** — see `skills/dku-cli/references/commands.md` for full reference.

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

```
dataiku-devkit/
├── skills/
│   ├── dataiku/               # Platform knowledge router
│   │   ├── SKILL.md           # Routes to correct reference doc based on task
│   │   └── references/*.md    # Deep platform knowledge (progressive disclosure layer 3)
│   └── dku-cli/               # CLI operations and composability patterns
│       ├── SKILL.md           # THE primary agent interface — cheat sheet + patterns + gotchas
│       └── references/        # CLI command reference
└── agents/                    # Subagents for complex tasks
    ├── plugin-reviewer.md
    ├── dss-explorer.md
    └── tool-designer.md
.claude-plugin/            # Plugin manifest for Claude Code marketplace
```

### Skill Quality Standards

When editing `dataiku-devkit/skills/dku-cli/SKILL.md`:

- **Cheat sheet** (top 30 lines): Must prevent the top failure modes. One line per rule. If you add a gotcha to CLAUDE.md, ask: does the cheat sheet need a rule too?
- **Examples**: Every example must be copy-paste-runnable. Include `-P PROJ` and all required flags.
- **Gotchas table**: Scannable — symptom in one column, fix in another. Agents pattern-match on error messages.

### Dataiku Reference Docs

Platform knowledge lives in `dataiku-devkit/skills/dataiku/references/`. Read the relevant doc BEFORE working on that topic.

| Document | Read when... |
|----------|--------------|
| `plugin-structure.md` | Creating a new plugin, plugin.json anatomy |
| `recipes.md` | Building custom recipes, dataset operations |
| `webapps.md` | Building webapp dashboards (Flask/Vue/React) |
| `webapp-pitfalls.md` | Debugging webapp errors, critical mistakes |
| `llm-tools.md` | Creating agent tools, custom agents |
| `parameters.md` | Defining plugin parameters (30+ types) |
| `code-environments.md` | Python dependency management, code env config |
| `datasets.md` | Building dataset connectors |
| `macros.md` | Building runnables/macros |
| `testing.md` | Unit/integration/E2E testing patterns |
| `best-practices.md` | Architecture, error handling, performance |
| `plugin-workflow.md` | Git integration, versioning, CI/CD, distribution |
| `formulas.md` | Formula language, Prepare recipe expressions |
| `llm-mesh.md` | LLM connections, guardrails, RAG, knowledge banks |
| `structured-agents.md` | SVA design guide: all 13 block types, graph patterns, state, CLI workflow |
| `python-api.md` | dataiku/dataikuapi packages, dataset I/O, SQL |
| `scenarios.md` | Automation, triggers, steps, reporters |
| `mlops.md` | Model lifecycle, drift detection, API Node |
| `guardrails.md` | LLM guardrails: blocking, filtering, PII, LLM judge, trace API |
| `styling.md` | Dataiku brand colors, typography, components |
| `plugin-architecture.md` | Plugin tiers (1-5), patterns/anti-patterns, official docs gaps |
| `visual-agent-blocks.md` | BlockHandler, block.json, dual-mode components, agent connectors |
| `webapp-patterns.md` | Advanced: multi-tab dashboards, filters, caching, React+Vite, Chart.js |
| `agent-tool-patterns.md` | Advanced: subprocess tools, MCP gateway, OAuth, multi-agent, HITL |
| `plugin-review-checklist.md` | Reviewing plugins, code review criteria, scoring rubric |
| `scaffolding.md` | Plugin scaffolding, adding components, deploying, reviewing |
| `prepare-processors.md` | ~95 Prepare recipe processor types: type IDs, params, examples |
| `dashboard-charts.md` | Chart JSON anatomy, insight definitions, dashboard tiles, chart types |
| `geospatial.md` | Geospatial data handling, projections, spatial joins |

---

## Critical Gotchas

**Rule: Every gotcha below MUST also exist in `dataiku-devkit/skills/dku-cli/SKILL.md` gotchas table AND be caught with a prescriptive error message in the CLI code.**

### Dataset Create + Upload
`dku dataset create` defaults to Filesystem, which does NOT support `dku dataset upload`. Use `--type UploadedFiles` for anything being uploaded via CLI.

`dku dataset delete` / `dku project delete` have no `--yes` flag. For non-interactive deletion: `echo y | dku dataset delete NAME -P PROJ`.

### Code Recipe Create + Connection
`dku recipe create` for code recipes fails if the project has no default managed connection. Always pass `--connection` / `-c`. Use `dku connection list` to find available connections (`filesystem_managed` is the most common). Visual recipes don't need `--connection`.

### Plugin Webapp Backend
DSS injects `app` (Flask) globally into `backend.py`. NEVER create your own `app = Flask(__name__)` — it breaks `/__ping`. Import from `dataiku.customwebapp`, not `dataiku.webapp`. Folder is `webapps/`, not `custom-webapps/`. `webapp.json` needs `hasBackend: true`, `noJSSecurity: true`.

### Code Environments on Python 3.11
NEVER use `installCorePackages: true` — installs `pandas==0.23.4` which fails on Python 3.11. Use `installCorePackages: false` + explicit `requirements.txt`: `pandas>=2.0,<3`, `numpy>=1.22,<3`, `python-dateutil>=2.8,<3`, `requests>=2.28,<3`. Include all four even if not used directly. If `create_code_env()` fails, the broken env persists — delete it before retrying.

### GREL Formula Quirks
`log()` = base-10 (no `ln()`). `exp()` IS base-e (inconsistent). `numval()`/`val()` don't work — use direct arithmetic. Formula columns default to STRING — always run `apply-schema` after adding formula steps.

### Agent Tool Patterns
Trace API: `trace.attributes[key] = value` — NOT `set_attribute()` or `add_metadata()`. `invoke()` input is at `input.get("input", {})`, not root. Subprocess tools MUST set `stdin=subprocess.DEVNULL` + `env["CI"] = "true"` + `env["NO_COLOR"] = "1"`.

### Chart Column Names
Not validated server-side — wrong column names save but render blank charts. Verify with `dku dataset schema DS -P PROJ` first. Dashboard tiles at `pages[i].grid.tiles`, not `pages[i].tiles`.

### Plugin Deployment via API
`install_plugin_from_archive()` / `update_from_zip()` return None (use async variants for futures). ZIP must have `plugin.json` at root. Plugin must NOT be in `plugins/dev/` when installing via API.

### Plugin Structure
`python-agent-tools/`, `webapps/`, `custom-recipes/`, `python-runnables/`, `python-connectors/`, `python-lib/`, `code-env/`. See `skills/dataiku/references/plugin-structure.md`.

---

## dataikuapi Quirks

Quirks are annotated inline in each `commands/*.py` file. Key patterns:

- `list_*()` usually returns dicts, not objects — access via `.get()`
- `create_*()` returns objects with non-standard id fields (e.g. `.dashboard_id`, `.insight_id`)
- Async operations return `DSSFuture` — call `.wait_for_result()`
- `get_agent(id)` is lazy — call `get_settings()` to verify existence
- `create_managed_folder()` returns `DSSManagedFolder` with `.id` (8-char hash)
- `plugin.list_files()` returns nested dict tree — dev plugins only
- Plugin recipe types not registered until JVM restart after API install

---

## Pull Request Descriptions

Every PR description must answer: *does this make agents more successful?*

- **What changed** — CLI commands, flags, skill docs, error messages, tests (be specific)
- **Why** — benchmark feedback / discovered gotcha / PR review finding / skill gap
- **Agent impact** — what failure mode this prevents or what new capability it unlocks
- **Test plan** — `uv run pytest -v` + any manual `dku` commands to verify the behavior

---

## Commit Conventions

Uses [Conventional Commits](https://www.conventionalcommits.org/) — enforced by commitlint pre-commit hook on `commit-msg` stage:

```
feat: add new command group
fix: handle empty dataset schema
docs: update skill reference
test: add recipe creation tests
chore: bump dependency versions
```

Hook pipeline also runs: `ruff-check --fix`, `ruff-format`, `uv-lock` sync, trailing-whitespace, detect-private-key.

---

## Testing

```bash
uv run pytest -v                # All tests (must all pass)
uv run pytest tests/commands/   # Command tests only
uv run pytest -k "test_dataset" # Filter by name
```

CI matrix: Python 3.10, 3.11, 3.12, 3.13 — use 3.10 as minimum baseline.

- Unit tests mock `DSSClient` via `conftest.py` fixtures (`mock_client`, `patch_client`)
- `patch_client` patches `dku_cli.client.get_client` AND `dku_cli.helpers.get_client`
- Use `typer.testing.CliRunner` for CLI invocation tests
- Pass `--project PROJ1` in tests instead of patching `resolve_project`
- Test both table and JSON output modes
- **Test error messages too** — verify agents get prescriptive guidance on failure

---

## Distribution

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
| `benchmark/README.md` | Benchmark framework architecture, test tiers, how to run |
| `dataiku-devkit/skills/dku-cli/references/commands.md` | Full CLI command reference with flags and examples |
| `dataiku-devkit/skills/dataiku/references/*.md` | Platform reference docs — see table above |
