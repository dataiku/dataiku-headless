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
5. Test new or changed commands against live DSS with `uv run dku ...` using `ADVISORGPT` or `AGENTTEST`.
6. Run `uv run ruff format .` before committing.

Live DSS checks should verify real output, not just exit codes:

- Table output has populated columns.
- JSON field names match actual DSS payloads.
- Empty results print useful guidance.
- Wrong inputs produce prescriptive errors.

## CLI Architecture

```text
typer
  ├─ rich
  ├─ dataikuapi
  ├─ keyring
  ├─ platformdirs
  └─ tomli / tomllib
```

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

Detailed agent-facing safety docs live in:

- `dataiku-devkit/skills/dku-cli/references/safety.md`
- `dataiku-devkit/skills/dku-cli/references/admin-safety.md`

## DevKit Documentation Policy

Always-loaded skill files must stay small and directional.

| Layer | File | Belongs there |
|---|---|---|
| 1 | `SKILL.md` | Purpose, boundary, high-impact rules, reference map |
| 2 | `references/*.md` | Command syntax, payloads, workflow templates, gotchas |
| 3 | CLI errors / `--help` | Recovery instructions at the failure point |

Do not add incident notes directly to `CLAUDE.md` or to a skill cheat sheet by default. Promote a gotcha to `SKILL.md` only when it is common, severe, and prevents a wrong strategic choice. Otherwise put it in the narrowest canonical reference:

- CLI syntax: `dataiku-devkit/skills/dku-cli/references/commands.md`
- CLI operational traps: `dataiku-devkit/skills/dku-cli/references/common-gotchas.md`
- Recipe build/verification flow: `dataiku-devkit/skills/dku-cli/references/recipe-operations.md`
- General safety guards: `dataiku-devkit/skills/dku-cli/references/safety.md`
- Admin lockout risks: `dataiku-devkit/skills/dku-cli/references/admin-safety.md`
- Platform behavior and JSON payloads: `dataiku-devkit/skills/dataiku/references/*.md`

When editing skills:

- Keep `SKILL.md` under roughly 150 lines unless there is a strong reason.
- Avoid command matrices and long examples in `SKILL.md`.
- Link every important reference directly from `SKILL.md`.
- Do not duplicate the same rule across multiple always-loaded files.

## Dataiku DevKit Layout

```text
dataiku-devkit/
├── skills/
│   ├── dataiku/                 # Platform capability router
│   ├── dku-cli/                 # CLI execution router
│   ├── migration/               # SAS / Alteryx / Excel migration workflows
│   ├── dataiku-internal-branding/
│   └── cli-meta-analysis/
└── agents/
    ├── dss-explorer.md
    ├── plugin-reviewer.md
    └── tool-designer.md
```

## Testing

```bash
uv run pytest -v
uv run pytest tests/commands/
uv run pytest -k "test_dataset"
uv run ruff check .
uv run ruff format .
```

CI runs Python 3.10 through 3.13. Keep 3.10 compatibility.

For CLI changes, include tests for:

- Table and JSON output when relevant.
- Prescriptive error messages.
- Project resolution via `-P`.
- Guarded destructive behavior for delete/cascade/admin commands.

## Pull Requests

Every PR description should include:

- **What changed** — commands, flags, docs, errors, tests.
- **Why** — benchmark feedback, discovered gap, bug, or agent failure mode.
- **Agent impact** — what becomes easier or safer for agents.
- **Test plan** — unit tests and live DSS commands when applicable.

## Commits

Use Conventional Commits:

```text
feat: add new command group
fix: handle empty dataset schema
docs: update skill reference
test: add recipe creation tests
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

## Docs Index

| Doc | Description |
|---|---|
| `benchmark/README.md` | Benchmark framework |
| `dataiku-devkit/skills/dku-cli/SKILL.md` | CLI execution router |
| `dataiku-devkit/skills/dataiku/SKILL.md` | DSS platform router |
| `dataiku-devkit/skills/dku-cli/references/commands.md` | Full command syntax |
| `dataiku-devkit/skills/dku-cli/references/common-gotchas.md` | Operational gotchas |
| `dataiku-devkit/skills/dataiku/references/` | Platform design and payload references |
