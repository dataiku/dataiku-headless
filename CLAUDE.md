# CLAUDE.md — Dataiku DevKit

## Quick Start

```bash
uv sync                    # Install deps
uv run pre-commit install  # Install git hooks (commitlint, ruff, whitespace fixes)
uv run pytest -v           # Run tests (all must pass)
uv run ruff check .        # Lint
uv run ruff format .       # Format
uv run dku                 # Run CLI locally (dev, uses .venv)
uv build                   # Build wheel
```

### Reinstalling the global `dku` CLI

The globally-installed `dku` tool (via `uv tool install`) caches its build. After merging changes to the main repo, you must force-reinstall to pick them up:

```bash
uv tool install --from . dku-cli --force --reinstall
```

**`--force` alone is not enough** — it reuses the cached wheel. `--reinstall` rebuilds from source. Without both flags, `dku folder create --help` etc. will show "No such command" even though the code is on disk.

## Mission

**This repo exists to make AI coding agents excellent at operating Dataiku DSS.** Every change — CLI code, skill docs, error messages, tests — is evaluated by one question: *does this make agents more successful?*

We ship two components:

1. **`dku` CLI** — a `kubectl`-style tool wrapping `dataikuapi`. Replaces throwaway Python scripts with composable shell commands agents chain with `&&`.
2. **Agent skills & knowledge** — 2 skills, reference docs, and 3 subagents that teach agents how to operate DSS.

**Private repo — NOT on PyPI.** Install from a local clone — see [Distribution](#distribution).

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
5. **Run tests — ALWAYS, no exceptions** — `uv run pytest -v` after ANY CLI code change. Write new tests for new commands. Test error paths too, not just happy paths. Never skip this step.
6. **Test against live DSS (MANDATORY)** — Unit test mocks are guesses until verified. After unit tests pass, run every new/changed command against the real DSS instance with `uv run dku <command>`. Use projects **ADVISORGPT** (Snowflake datasets, recipes, flow graph) or **AGENTTEST**. Verify:
   - Table output shows real data, not blank columns (field name mismatches cause this)
   - JSON output field names match what DSS actually returns
   - Empty results produce helpful messages (no usages, no schemas, etc.)
   - Wrong inputs (bad column name, non-SQL connection for schemas) produce prescriptive errors
   - If live testing reveals mismatches, fix them BEFORE committing
7. **Format before committing** — `uv run ruff format .` (CI runs `ruff format --check` and will reject unformatted code)

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

When editing skills, **progressive disclosure is non-negotiable**:

| Layer | File | What goes here | What does NOT go here |
|-------|------|----------------|----------------------|
| 1 | SKILL.md cheat sheet (top 30 lines) | Failure prevention rules, one line each | Command syntax, flag details |
| 2 | SKILL.md body | Command Groups table (verb names only), chaining patterns for new workflows | Per-command notes, flag descriptions, API details |
| 3 | `references/commands.md` | Full command syntax, all flags, usage notes, API quirks | — (this is the detail layer) |

**Rules:**
- **SKILL.md is loaded into every conversation.** Every line costs tokens. Be ruthless about what earns a spot.
- **Never add per-command documentation to SKILL.md.** That's what `references/commands.md` is for. SKILL.md gets the verb in the Command Groups table + a chaining pattern IF the command enables a new workflow.
- **Cheat sheet** (top 30 lines): Must prevent the top failure modes. One line per rule. If you add a gotcha to CLAUDE.md, ask: does the cheat sheet need a rule too?
- **Examples**: Every example must be copy-paste-runnable. Include `-P PROJ` and all required flags.
- **Gotchas table**: Scannable — symptom in one column, fix in another. Agents pattern-match on error messages.

### Govern Blueprint Designer Skill

A dedicated **`govern-blueprint-designer`** skill (`dataiku-devkit/skills/govern-blueprint-designer/`) teaches agents end-to-end blueprint version authoring: fork → edit fields/workflow/hooks/views → activate → wire signoffs. Use it when the user wants to design a blueprint (as opposed to operating one at runtime).

---

## Critical Gotchas

**Rule: Every gotcha below MUST also exist in `dataiku-devkit/skills/dku-cli/SKILL.md` gotchas table AND be caught with a prescriptive error message in the CLI code.**

### Dataset Create + Upload
`dku dataset create` defaults to Filesystem, which does NOT support `dku dataset upload`. Use `--type UploadedFiles` for anything being uploaded via CLI.

`dku dataset delete` and `dku recipe delete` prompt by default but support `--yes` / `-y` for non-interactive deletion. `dku project delete` requires `--confirm`, `--yes`, or `-y`.

### Code Recipe Create + Connection
`dku recipe create` for code recipes fails if the project has no default managed connection. Always pass `--connection` / `-c` when creating Python/SQL recipes in projects without a default managed connection. Use `dku connection list` to find available connections (`filesystem_managed` is the most common). If `connection list` is unavailable, inspect an existing dataset with `dku dataset get-definition DS -P PROJ -o json | jq -r '.params.connection'`. Cross-project recipe inputs use `PROJECT_KEY.DATASET_NAME`. Visual recipe shortcuts auto-create outputs and don't need `--connection`.

### Dataset Verification + Schema Reality
`dku dataset head -o json` returning `[]` means the dataset has 0 rows, not an error. Always verify built outputs with `dku dataset head OUTPUT -P PROJ -n 5` and inspect actual columns with `dku dataset schema OUTPUT -P PROJ` before assuming a recipe worked. Wiki plans and schema docs can lag the real dataset.

### Python Recipe Numeric IDs
ID columns from external datasets may contain nulls or non-numeric values. Never cast directly with `.astype("int64")`; use `pd.to_numeric(..., errors="coerce")`, `dropna`, then cast, or the recipe will fail with `IntCastingNaNError`.

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

### Govern Blueprint Designer
Blueprint entity (`dku govern blueprint set-definition`) only stores name/icon/color. Fields, workflow, hooks, views, and signoffs live on the **version** (`set-version-definition`). New versions are DRAFT until `set-version-status BP VER ACTIVE`. Editing a version with existing artifacts blocks destructive changes unless `--force` (`dangerZoneAccepted`) is passed — never set this without user confirmation. Signoff `usersContainer.type` values are **lowercase**: `"user" / "group" / "role" / "global-api-key"`. `create-signoff-config` body must NOT include `id` (server assigns from URL path). `list-versions` uses the admin designer endpoint so DRAFTs appear — the non-admin path silently hides them.

### Govern Doc Validation (pre-merge)
The Govern backend accepts lax JSON — unknown fields are silently dropped and missing fields default to empty lists. That means a doc can ship with a wrong payload shape (wrong key name, missing nesting) and no test catches it. This has happened **three times** on Govern reference docs: 2026-04-08 signoff config used `approverConfiguration` (singular, wrong); 2026-04-12 re-fixed to `approvers[]` (list, correct); 2026-04-14 `ui-views.md` / `govern-blueprint-designer` SKILL taught `uiDefinition.views = {}` as "default rendering" when it actually produces a blank artifact page in the UI. The common denominator: lax JSON validation + no UI-level test + agents that trust the doc.

Before merging changes to any doc under `dataiku-devkit/skills/dataiku/references/govern.md` or `dataiku-devkit/skills/govern-blueprint-designer/`, run:

```bash
uv run python scripts/verify_govern_docs.py
```

The script extracts every ```json block, classifies it (signoff config, blueprint version, field definition, workflow step, artifact, or blueprint entity), posts each complete payload through the matching API call on a live Govern instance, reads the result back, and flags both static shape errors (known-bad keys) and silently-dropped content. Partial/illustrative snippets are detected and skipped automatically. Requires an admin DSS client (same as `dku whoami`). Creates a scratch blueprint `bp.doc_verifier_tmp` and tears it down at exit. Use `--scratch-id` to isolate concurrent runs and `--keep` to inspect the scratch blueprint afterwards.

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
- `get_semantic_model()` is lazy — must call `_get_definition()` to verify existence
- Agent Hub is a plugin webapp, not a first-class object — manage via `get_webapp()` + `get_backend_actions()`
- `DSSScenario.get_last_finished_run()` returns None when no runs exist (not an error)
- `folder.list_contents()` returns `{"items": [...]}`, not a flat list
- **Govern has parallel admin and non-admin read paths.** `govern.get_blueprint(id).list_versions()` hits `/blueprint/{id}/versions` and **silently filters out DRAFT versions**. `govern.get_blueprint_designer().get_blueprint(id).list_versions()` hits `/admin/blueprint/{id}/versions` and returns every version regardless of status. Use the designer path for anything authoring-related. Same asymmetry applies wherever `govern.get_X()` has a `get_X_designer()` counterpart. The CLI's `dku govern blueprint list-versions` defaults to the admin path for this reason
- **Govern server silently drops unknown JSON fields.** Misshapen signoff configurations and blueprint version definitions often look like they succeed — the server saves whatever it can parse and ignores the rest. This is how the signoff-structure bug landed twice and the empty-`views: {}` blank-page bug landed once. Always verify a doc's JSON shape with `scripts/verify_govern_docs.py` before merging. `dku govern blueprint describe-version BP VER` and `set-version-definition` both print structural warnings (empty views, missing `artifactPageViewId`, unreferenced fields, step viewIds pointing nowhere) — use them as the last line of defense
- `DSSAgent.as_llm()` returns `DSSLLM` — the only way to call an agent programmatically (no `run_conversation()`)
- `project.create_evaluation_store(name, flavor)` — `flavor` must be `'LLM'` for LLM eval stores
- Prompt recipe creation requires output dataset in `creationSettings`, not `recipe_proto` (internal API, not exposed via `dataikuapi`)

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
| `dataiku-devkit/skills/dataiku/references/*.md` | Platform reference docs — see Quick Router in `dataiku/SKILL.md` |
