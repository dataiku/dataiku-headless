# AGENTS.md — Dataiku DevKit

> This file follows the [AGENTS.md standard](https://agents.md) for AI coding agents.

## Project Overview

The **Dataiku DevKit** enables any AI coding agent to do anything in Dataiku DSS. It ships a `dku` CLI (139 commands, 25 groups) and 2 skills with 28 platform reference docs. Works with Claude Code, Codex, Cursor, and any agent that reads SKILL.md files.

## Quick Setup

```bash
# Install the CLI (from GitHub — not on PyPI)
uv tool install git+https://github.com/dataiku/dataiku-cli.git

# Authenticate
dku auth login

# Verify
dku whoami
```

## Build & Test

```bash
uv sync                    # Install dependencies
uv run dku --help          # Run locally
uv run pytest -v           # Run tests (all mocked, no DSS connection needed)
uv build                   # Build wheel
```

## Project Structure

```
src/dku_cli/               # Python CLI source
├── main.py                # Root Typer app, global options, whoami
├── helpers.py             # resolve_project(), get_client_from_ctx()
├── output.py              # All rendering (table/json/csv)
├── errors.py              # Exception handling
└── commands/              # One file per noun (25 command groups)

skills/                    # AI agent skills (Claude Code plugin + skills.sh)
├── dataiku/               # Platform knowledge (28 reference docs incl. scaffolding)
└── dku-cli/               # CLI operations and composability

agents/                    # Subagents for complex tasks
├── plugin-reviewer.md     # Deep plugin code review
├── dss-explorer.md        # Explore DSS project via CLI
└── tool-designer.md       # Design agent tool schemas

tests/                     # Unit tests (mock DSSClient, no real DSS)
benchmark/                 # 7-tier agent benchmark (160 scenarios, Claude vs Codex)
.claude-plugin/            # Claude Code plugin manifest
docs/                      # Detailed reference docs (extracted from CLAUDE.md)
```

## Code Conventions

- **One file per noun** in `commands/` (e.g., `dataset.py`, `recipe.py`)
- **All formatting through `output.py`** — commands never import `rich` directly
- **Project resolution**: `--project` flag > `DKU_PROJECT` env > config default
- **Client creation**: `helpers.get_client_from_ctx(ctx)`
- **Tests mock `DSSClient`** via `conftest.py` fixtures (`mock_client`, `patch_client`)
- **Version** single-sourced from `src/dku_cli/__init__.py`

## Commit Style

Conventional Commits: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`

## Key Patterns

- Every CLI command: `dku <noun> <verb> [ARGS] [OPTIONS]`
- Chain related commands with `&&` in single shell calls
- JSON output: `-o json` for piping to `jq`
- Global options: `--url`, `--api-key`, `--profile`, `--quiet`

## CI/CD

- `ci.yml` — runs tests on push/PR
- `publish.yml` — publishes on GitHub Release (not currently active — CLI not on PyPI)

## Security

- Credentials stored in OS keychain (macOS Keychain, GNOME Keyring, Windows Credential Manager)
- Fallback: `~/.config/dku/credentials.toml` with 0600 permissions
- Never commit `.env` files or API keys
