# CLAUDE.md — Dataiku DevKit

## Purpose

This repo makes AI coding agents effective at operating Dataiku DSS.

It ships two related artifacts:

1. **`dku` CLI** — a Typer/Rich wrapper around `dataikuapi` for shell-composable DSS operations.
2. **Dataiku DevKit** — agent skills, references, and subagents that teach agents how to choose DSS-native capabilities and operate them safely.

Every change should answer: **does this make agents more successful?**

## Quick Start

```bash
uv sync
uv run pre-commit install
uv run pytest -v
uv run ruff check .
uv run ruff format .
uv run dku
uv build
```

The globally installed `dku` tool caches its build. After merging CLI changes, force a source rebuild:

```bash
uv tool install --from . dku-cli --force --reinstall
```

`--force` alone is not enough because it may reuse the cached wheel.

## Development Workflow

When changing CLI behavior:

1. Check whether a DSS built-in feature already solves the workflow before adding Python-centric commands.
2. Verify `dataikuapi` behavior from the installed source under `.venv/lib/*/dataikuapi/`; do not invent APIs.
3. Add or update unit tests for happy paths and error paths.
4. Run `uv run pytest -v` after any CLI code change.
5. Test new or changed commands against live DSS with `uv run dku ...`.
6. Run `uv run ruff format .` before committing.

Live DSS checks should verify real output, not just exit codes:

- Table output has populated columns.
- JSON field names match actual DSS payloads.
- Empty results print useful guidance.
- Wrong inputs produce prescriptive errors.

## CLI Architecture

Stack: `typer` + `rich` → `dataikuapi` → DSS REST API.
Auth: `keyring` (os keychain) + `platformdirs` + `tomli` (TOML profile).

The CLI follows `dku <noun> <verb>`.

Every command should:

1. Resolve auth through `helpers.get_client_from_ctx()`.
2. Resolve project through `helpers.resolve_project()` when project-scoped.
3. Call `dataikuapi`.
4. Render through `output.py`.
5. Fail with a prescriptive next step.

### Key Files

| File | Responsibility |
|---|---|
| `main.py` | Root Typer app, global options, command registration, `whoami` |
| `brand.py` | `◆` icon, version, status strings |
| `helpers.py` | Project/client resolution, JSON/text input helpers |
| `config.py` | TOML config read/write |
| `auth.py` | Keyring and file fallback credentials |
| `client.py` | Auth resolution and `DSSClient` factory |
| `output.py` | Table/JSON/CSV/raw rendering and quiet mode |
| `errors.py` | User-facing exception mapping |
| `safety.py` | Guarded destructive operations |
| `commands/*.py` | One file per CLI noun |
| `mcp/*.py` | Standalone `dku-mcp` MCP server (`dku_exec`); `fastmcp` lazy-imported, intentionally not on the `dku` app. See `dataiku-mcp/README.md`. |

## Coding Conventions

- One command module per noun in `src/dku_cli/commands/`.
- Command modules should not import Rich directly; route presentation through `output.py`.
- Root options (`--url`, `--api-key`, `--profile`, `--quiet`, `--errors`, `--dangerous`) live on the root app.
- Project resolution order is `--project` / `-P`, then `DKU_PROJECT`, then configured default.
- Tests mock `DSSClient` through the shared fixtures in `tests/conftest.py`.
- Version is single-sourced from `src/dku_cli/__init__.py`.
- Error messages should tell the agent what command to run next.
- Text file inputs should use `helpers.read_text_input(value)` for literal text, `@file`, and stdin (`-`).

## Safety Model

`dku` is guarded by default. Every destructive command must call `safety.guard()`.

| Tier | Use when the command... | Required call-site flags |
|---|---|---|
| `READ` / `WRITE` | Lists, creates, or performs reversible updates | No guard needed |
| `DELETE` | Deletes one named resource or clears its data | `--yes` / `-y` |
| `CASCADE` | Is irreversible or can affect resources the user did not explicitly name | `--yes` and `--confirm-name` |
| `ADMIN` | Mutates instance-wide admin configuration | `--yes`, `--confirm-name`, and `--i-know-what-im-doing` |

Exit code `77` is reserved for safety blocks. Do not reuse it.

When adding a destructive command:

1. Pick the tier before writing code.
2. Add the required confirmation flags.
3. Call `guard(ctx, tier=..., action=..., subject=..., yes=...)`.
4. Write the `prompt=` from the user's perspective.
5. Test blocked, confirmed, mismatch, and dangerous-mode paths.

Detailed agent-facing safety docs (tiers, exit 77, admin lockout) live in:

- `dataiku-mcp/skills/dku-cli/references/safety.md`

## DevKit Documentation Policy

References explain *when/why and non-obvious behavior*, not flags. Exact flags come from `<command> --help` (machine-readable JSON under `DKU_AGENT_HELP=1`). Placement:

| Layer | Content |
|---|---|
| `SKILL.md` | Purpose, triggers, permanent rules, capability→playbook router, reference map |
| `playbooks/*.md` | Task-complete workflows: decisions, command sequences, gotchas-with-fix, verification. A few canonical command examples (no exhaustive flag tables) |
| `references/*.md` | Durable cold detail: JSON payloads, param tables, schemas |
| `<command> --help` | Exact flags (never hand-write flag tables) |

The SKILL.md router owns the live capability→playbook map and the playbook list; don't re-list playbooks here (it drifts). The agent reads ONE playbook per task.

Do not add incident notes to CLAUDE.md or skill cheat sheets. Put gotchas in the matching playbook or reference.

Keep each layer scoped: SKILL.md a thin router, playbooks task-complete, references cold detail. No flag duplicates across files; no flag tables anywhere (they come from `--help`).

## Dataiku DevKit Layout

The agent-facing DevKit lives under `dataiku-mcp/skills/`: the unified `dku-cli`
skill (`SKILL.md` router → `playbooks/` → `references/`), plus the `migration` and
`dataiku-internal-branding` skills. Browse the directory for the current file set
rather than maintaining a tree here.

## Testing

```bash
uv run pytest -v
uv run pytest tests/commands/
uv run pytest -k "test_dataset"
uv run ruff check .
uv run ruff format .
```

CI runs Python 3.10 through 3.13. Keep 3.10 compatibility.

CI also runs a one-way quality ratchet (`scripts/check_quality_ratchet.py`) that
fails only on *new* Ruff `C901`/`E501` debt. If a deliberate change shifts the
counts, regenerate the baseline: `uv run python scripts/check_quality_ratchet.py --write-baseline`.

For CLI changes, include tests for:

- Table and JSON output when relevant.
- Prescriptive error messages.
- Project resolution via `-P`.
- Guarded destructive behavior for delete/cascade/admin commands.

## Pull Requests

Every PR description should include:

- **What changed** — commands, flags, docs, errors, tests.
- **Why** — discovered gap, bug, or agent failure mode.
- **Agent impact** — what becomes easier or safer for agents.
- **Test plan** — unit tests and live DSS commands when applicable.

## Commits

Use Conventional Commits:

```text
feat: add new command group
docs: update skill reference
chore: bump dependency
```

Pre-commit also runs Ruff, whitespace checks, private-key detection, and `uv-lock` sync.

## Distribution

The CLI is private and not published to PyPI.

| Channel | Command |
|---|---|
| Direct | `uv tool install git+https://github.com/dataiku/dataiku-cli.git` |
| Local dev | `uv tool install --from . dku-cli` |

Dataiku DevKit skills:

| Channel | Command |
|---|---|
| Claude Code plugin | `/plugin marketplace add dataiku/dataiku-cli` |
| skills.sh | `npx skills add dataiku/dataiku-cli --all` |

Connect an agent to DSS (local-stdio MCP) — the recommended path for external
harnesses. Each user installs the server locally and authenticates with their
own DSS personal API key (model A); no hosting, no Code Studio, no proxy:

| Channel | Command |
|---|---|
| Claude Code plugin | `claude plugin marketplace add dataiku/dataiku-cli` → `claude plugin install dataiku-mcp` |
| Codex plugin | `codex plugin marketplace add dataiku/dataiku-cli` → `codex plugin install dataiku-mcp` (export `DKU_URL` + `DKU_API_KEY`) |
| OpenCode | `uv tool install --from git+…/dataiku-cli.git "dku-cli[mcp]"` + `dataiku-mcp/examples/opencode.json` |
| Claude Desktop | one-click `.mcpb` bundle (non-technical users) — built from `dataiku-mcp-bundle/` |

The `dataiku-mcp/` directory is **both** a Claude Code plugin (`.claude-plugin/`)
and a Codex plugin (`.codex-plugin/`), sharing one launcher (`bin/`) + bundled
wheel (`wheels/`). The Codex marketplace catalog lives at
`.agents/plugins/marketplace.json`. The skill corpus ships as the plugin's own
`dataiku-mcp/skills/` directory; the bundled `dku-cli` wheel carries only the CLI
(`src/dku_cli`). The launcher runs `dku-mcp serve --transport stdio` through
`uvx`. Rebuild the wheel after CLI changes with `make bundle` in `dataiku-mcp/`
(a test guards against a stale wheel).

## Docs Index

| Doc | Description |
|---|---|
| `dataiku-mcp/skills/dku-cli/SKILL.md` | Unified DSS router (what to build + how to execute) |
| `dku <group> [command] --help` | Self-describing CLI: exact flags/args/defaults as JSON (under `DKU_AGENT_HELP=1`) |
| `dataiku-mcp/skills/dku-cli/playbooks/` | Task-complete workflows (sequences, gotchas, verification) |
| `dataiku-mcp/skills/dku-cli/references/` | Durable cold detail: payload shapes, schemas, processor/param tables, safety |
| `dataiku-mcp/README.md` | Claude Code + Codex plugin packaging |
| `dataiku-mcp-bundle/README.md` | Claude Desktop `.mcpb` packaging |
