# CLAUDE.md — Dataiku DevKit

## What This Is

The **Dataiku DevKit** enables any AI coding agent to do anything in Dataiku DSS. It ships two components:

1. **`dku` CLI** — a `kubectl`-style tool (163 commands, 28 groups) wrapping `dataikuapi` with auth management, output formatting, and composability. Replaces throwaway Python scripts with shell commands that agents chain with `&&`.

2. **Agent skills & knowledge** — 2 skills, 27 platform reference docs, and 3 subagents that teach agents how to build plugins, manage projects, and operate DSS. Works with Claude Code, Codex, Cursor, and any agent that reads SKILL.md files.

**Who it serves:** AI coding agents first, then developers, admins, field engineers, and CI/CD pipelines.

**Branding:** Uses `◆` (black diamond) as icon, like Vercel's `▲`. Renders universally without Nerd Fonts. Must wrap in Rich markup (`[blue bold]◆[/blue bold]`) in Typer help strings or Typer strips it.

---

## CLI Architecture

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

### Command Groups

25 groups + `whoami`. Full reference with examples: `docs/commands.md`.

---

## Workflow

Work in three phases — do not skip ahead.

1. **Research** — explore codebase, ask clarifying questions, surface assumptions. No code changes.
2. **Plan** — write a `plan.md` together. Stop and wait for explicit approval before proceeding.
3. **Implement** — only once the plan is approved. One task at a time; wait for feedback before the next.

When asked to debug or investigate, stay in analysis-only mode. Phrases like "look into this" or "what's going on" are not permission to edit files.

Before any code modification: propose the change in plain language, show a minimal diff, then stop and wait for approval.

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

The DevKit layer lives in `dataiku-devkit/` — skills, agents, and reference docs that any AI coding agent auto-discovers:

```
dataiku-devkit/
├── skills/                    # Skills (auto-discovered by Claude Code, Codex, Cursor, etc.)
│   ├── dataiku/               # Platform knowledge router (27 reference docs incl. scaffolding)
│   └── dku-cli/               # CLI operations and composability patterns
├── agents/                    # Subagents for complex tasks
│   ├── plugin-reviewer.md     # Deep plugin code review
│   ├── dss-explorer.md        # Explore DSS projects via CLI
│   └── tool-designer.md       # Design agent tool schemas
└── .claude-plugin/            # Plugin manifest for Claude Code marketplace
```

### Dataiku Reference Docs

27 platform reference docs in `dataiku-devkit/skills/dataiku/references/`. They are auto-loaded by the DevKit skill — read the relevant one before working on any Dataiku topic.

---

## Critical Gotchas (CLI)

**`dku dataset create` defaults to Filesystem type — use `--type UploadedFiles` for datasets you'll upload to:**

```bash
dku dataset create my_data --type UploadedFiles -P PROJ
dku dataset upload my_data data.csv -P PROJ
```

**No `--yes` flag on destructive commands.** For non-interactive deletion: `echo y | dku dataset delete NAME -P PROJ`.

For Dataiku platform gotchas (webapps, code envs, agent tools, plugin deployment), read the relevant doc in `dataiku-devkit/skills/dataiku/references/`.

---

## Command → dataikuapi Mapping

See `docs/command-api-mapping.md` — full table including dataikuapi quirks baked into each command.

---

## Testing

```bash
uv run pytest -v    # 362 tests
```

- Unit tests mock `DSSClient` via `conftest.py` fixtures (`mock_client`, `patch_client`)
- `patch_client` patches `dku_cli.client.get_client` AND `dku_cli.helpers.get_client`
- Use `typer.testing.CliRunner` for CLI invocation tests
- Pass `--project PROJ1` in tests instead of patching `resolve_project`
- Test both table and JSON output modes
- No real DSS connection required

---

## Code Quality

```bash
uv run ruff check             # Lint
uv run ruff check --fix       # Lint + auto-fix
uv run ruff format            # Format
uv run ruff format --check    # Format check (CI)
```

Pre-commit hooks run automatically on `git commit` — enforces ruff, commitlint, and file hygiene. To run manually:

```bash
uv run pre-commit run --all-files
```

Commits must follow **Conventional Commits**: `type(scope): subject`

Valid types: `feat | fix | docs | style | refactor | perf | test | build | ci | chore | revert`

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

---

## Agent Benchmark

See `benchmark/README.md`.

---

## DevKit Installation

| Channel | Command |
|---------|---------|
| **Claude Code Plugin** | `/plugin marketplace add dataiku/dataiku-cli` |
| **skills.sh (40+ agents)** | `npx skills add dataiku/dataiku-cli --all` |

---

## Docs Index

| Doc | Description |
|-----|-------------|
| `docs/command-api-mapping.md` | Full table mapping every CLI command to its `dataikuapi` call |
| `docs/commands.md` | Generated CLI command reference |
| `benchmark/README.md` | Benchmark framework architecture, test tiers, how to run |
| `dataiku-devkit/skills/dku-cli/references/commands.md` | Full CLI command reference with flags and examples |
| `dataiku-devkit/skills/dataiku/references/` | 27 platform reference docs (auto-loaded by DevKit skill) |
