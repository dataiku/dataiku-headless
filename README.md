# ◆ dku-cli

```
               ......       ...........                 ...               ...  ...
              .......       ...    ......               ...               ...  ...
            ........        ...       ....   ........ .......  ........   ...  ...   .... ..      ..
           .........        ...        ...  ...   ....  ...   ....  ....  ...  ... .....  ...     ..
         ...........        ...        ...  ..   .....  ...   ...   ....  ...  .......    ...     ..
        ...........         ...        ...  ..........  ...    .........  ...  ......     ...     ..
      ............          ...       ...  ....    ...  ...   ...    ...  ...  .......    ...    ...
    ...... ..........       ............   ....  .....  ..... ...  .....  ...  ...  ....  ..........
   ...     ..........       ..........      ....... ..   ....  ...... ..  ...  ...    ...  .........
 ...
..
```

[![CI](https://github.com/dataiku/dataiku-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/dataiku/dataiku-cli/actions/workflows/ci.yml)
[![License](https://img.shields.io/github/license/dataiku/dataiku-cli)](LICENSE)

**Dataiku DevKit** — enables any AI coding agent to do anything in Dataiku DSS.

Ships two components:
- **`dku` CLI** — A `kubectl`-style tool for terminal use, CI/CD pipelines, and agent shell commands.
- **Dataiku DevKit** — 2 skills, reference docs, and 3 subagents that teach AI coding agents how to build plugins, manage projects, and operate DSS.

> **Private repo** — not on PyPI or any public registry. Install from a local clone.

```bash
# Clone and install
git clone https://github.com/dataiku/dataiku-cli.git
cd dataiku-cli

# Install CLI globally
uv tool install --from . dku-cli

# Install DevKit (skills + agents) — see DevKit Installation section below
```

---

## Table of Contents

- [Why DevKit & CLI?](#why-devkit--cli)
- [`dku` CLI](#dku-cli)
  - [Installation](#installation)
  - [Quick Start](#quick-start)
  - [Authentication](#authentication)
- [Dataiku DevKit](#dataiku-devkit)
  - [Installation](#installation-1)
  - [Components](#components)
  - [Benchmark](#benchmark)
- [Project Structure](#project-structure)
- [Development](#development)
- [License](#license)

---

## Why DevKit & CLI?

### CLI vs alternatives

| | `dsscli` | `dataikuapi` | `dku-cli` |
|---|---|---|---|
| Run from laptop | No (SSH only) | Yes | Yes |
| Auth management | N/A | Manual | Profiles + keychain |
| Learning curve | Medium | High (API docs) | Low (`--help`) |
| Output formats | Text | Python objects | table / json / csv |
| Scriptable | Bash | Python | Both |
| CI/CD ready | No | Boilerplate | `DKU_URL` + `DKU_API_KEY` |
| Full CRUD | No | Yes | Yes |
| Agentic use | No | Verbose | Built for it |

### DevKit vs raw CLI

Without the DevKit skills, agents must discover the API surface at runtime — reading docs, writing boilerplate, and polling for job status. The DevKit pre-loads that context:

| | Without DevKit | With DevKit |
|---|---|---|
| Agent cost (simple task) | $1.49 avg | $1.04 avg |
| Agent cost (complex task) | $2.83 avg | $1.40 avg |
| Wall time (simple) | 405s | 258s |
| Wall time (complex) | 684s | 402s |
| Tool calls (complex) | 60 avg | 43 avg |

The `dku-cli` skill reduces cost 30–50% by documenting exact commands upfront, eliminating runtime API discovery. The `dataiku` skill adds plugin scaffolding and platform knowledge on top of that.

---

## `dku` CLI

### Installation

Requires Python 3.10+ and [uv](https://docs.astral.sh/uv/). Install from a local clone (private repo — not on PyPI).

```bash
git clone https://github.com/dataiku/dataiku-cli.git
cd dataiku-cli
uv tool install --from . dku-cli

# Update (after git pull)
uv tool install --from . dku-cli --force --reinstall
```

> **`--force` alone is not enough** — it reuses the cached wheel. You need both `--force --reinstall` to rebuild from source after pulling changes.

### Quick Start

```bash
dku auth login        # authenticate to your DSS instance
dku whoami            # verify connection
dku project list      # list projects
dku dataset head my_dataset -P MYPROJECT   # preview data
dku plugin list -o json | jq '.[].id'      # JSON output for scripting
```

Full command reference: [skills/dku-cli/references/commands.md](dataiku-devkit/skills/dku-cli/references/commands.md)

### Authentication

```bash
dku auth login                    # interactive login
dku auth login --profile prod \
  --url https://dss.example.com \
  --api-key YOUR_KEY              # non-interactive (CI/CD)
dku auth switch production        # switch active profile
```

Credentials resolve in order: CLI flags → `DKU_URL`/`DKU_API_KEY` env vars → stored profile → OS keychain.

---

## Dataiku DevKit

### Installation

Since this is a private repo, install the DevKit by symlinking from your local clone. This means `git pull` automatically updates the skills everywhere.

```bash
# Skills (2 skill directories)
ln -sf /path/to/dataiku-cli/dataiku-devkit/skills/dataiku ~/.claude/skills/dataiku
ln -sf /path/to/dataiku-cli/dataiku-devkit/skills/dku-cli ~/.claude/skills/dku-cli

# Agents (3 agent definitions)
ln -sf /path/to/dataiku-cli/dataiku-devkit/agents/dss-explorer.md ~/.claude/agents/dss-explorer.md
ln -sf /path/to/dataiku-cli/dataiku-devkit/agents/plugin-reviewer.md ~/.claude/agents/plugin-reviewer.md
ln -sf /path/to/dataiku-cli/dataiku-devkit/agents/tool-designer.md ~/.claude/agents/tool-designer.md
```

#### Other agents (Codex, Cursor, etc.)

Copy `dataiku-devkit/skills/` into your agent's skill directory. No symlink equivalent exists for most agents — you'll need to re-copy after updates.

### Components

| Component | Type | Description |
|-----------|------|-------------|
| `dataiku` | Skill | Platform knowledge — reference docs covering plugins, formulas, LLM Mesh, agents, webapps, scenarios, MLOps, scaffolding, and deployment |
| `dku-cli` | Skill | CLI operations — chaining patterns, composability |
| `plugin-reviewer` | Agent | Deep code review against a structured checklist |
| `dss-explorer` | Agent | Explore a DSS project via CLI and produce a structured report |
| `tool-designer` | Agent | Design agent tool schemas and implementation plans |

### Benchmark

We benchmarked how AI agents (Claude Code) perform DSS tasks using `dku` CLI commands vs writing `dataikuapi` Python scripts directly.

**Setup:** 12 runs — 2 tasks (simple, complex) × 2 approaches × 3 runs each. Model: Claude Opus, headless (`claude -p --dangerously-skip-permissions`). Validated against DSS state + ground truth data.

- **Simple task:** Create project, upload 2 CSVs, join, group by tier+region, compute revenue (8 validation checks)
- **Complex task:** All of simple + ML model, agent, LLM completion (11 validation checks)

#### Results

| | Python API | dku CLI | Delta |
|---|---|---|---|
| Success rate | 6/6 (100%) | 6/6 (100%) | Tie |
| Simple cost | $1.49 avg | $1.04 avg | **-30%** |
| Complex cost | $2.83 avg | $1.40 avg | **-50%** |
| Simple wall time | 405s | 258s | **-36%** |
| Complex wall time | 684s | 402s | **-41%** |
| Simple tool calls | 39 avg | 32 avg | **-18%** |
| Complex tool calls | 60 avg | 43 avg | **-27%** |
| Tool overhead (simple) | 115s | 32s | **-72%** |
| Best single run | $1.21 / 319s | $0.76 / 168s | CLI |
| Worst single run | $1.94 / 526s | $1.28 / 325s | CLI |

#### Why CLI Helps Agents

1. **Lower tool overhead** — CLI commands chain with `&&` so multiple operations happen in a single tool call, reducing agent round-trips.
2. **Pre-documented interface** — The CLI skill documents exact commands and flags upfront, so agents don't need to discover API signatures at runtime.
3. **`--wait` eliminates polling** — `dku dataset build X --wait` blocks until done, replacing manual status-polling loops.
4. **Composite operations** — `dku dataset upload` combines file upload + format detection + schema inference in one command.

<details>
<summary>Per-run data and before/after bug fixes</summary>

#### Before/After Bug Fixes

Three bugs were fixed prior to the final benchmark (upload format detection, agent settings path, agent create type param):

| CLI Metric | Before fixes | After fixes | Change |
|---|---|---|---|
| Success rate | 4/6 (67%) | 6/6 (100%) | Fixed |
| Avg simple cost | $2.95 | $1.04 | **-65%** |
| Avg simple wall time | 692s | 258s | **-63%** |
| Avg simple tool calls | 69 | 32 | **-54%** |
| Worst run cost | $5.17 | $1.28 | **-75%** |

#### Per-Run Data

| Run | Pass | Cost | Wall | Calls | dku | python |
|---|---|---|---|---|---|---|
| CLI simple 002 | 8/8 | $0.76 | 168s | 23 | 12 | 10 |
| CLI simple 003 | 8/8 | $1.08 | 281s | 35 | 23 | 13 |
| PY simple 001 | 8/8 | $1.21 | 319s | 32 | 0 | 31 |
| CLI simple 001 | 8/8 | $1.28 | 325s | 37 | 19 | 21 |
| CLI complex 002 | 11/11 | $1.30 | 380s | 40 | 22 | 19 |
| CLI complex 003 | 11/11 | $1.31 | 437s | 42 | 21 | 21 |
| PY simple 003 | 8/8 | $1.31 | 369s | 35 | 0 | 33 |
| CLI complex 001 | 11/11 | $1.60 | 388s | 48 | 30 | 17 |
| PY simple 002 | 8/8 | $1.94 | 526s | 49 | 0 | 47 |
| PY complex 002 | 11/11 | $2.69 | 633s | 60 | 0 | 58 |
| PY complex 001 | 11/11 | $2.87 | 704s | 57 | 0 | 55 |
| PY complex 003 | 11/11 | $2.93 | 714s | 62 | 0 | 60 |

The top 5 runs by cost are all CLI. The bottom 3 are all Python complex.

</details>

---

## Project Structure

```
dataiku-cli/
├── src/dku_cli/                    # CLI source (Python package)
│   ├── main.py                     # Root Typer app, global options, whoami
│   ├── brand.py                    # ◆ icon, version_string(), status helpers
│   ├── helpers.py                  # resolve_project(), get_client_from_ctx(), read_json_input()
│   ├── client.py                   # Auth resolution → DSSClient factory
│   ├── auth.py                     # Keyring + file fallback credential storage
│   ├── config.py                   # TOML config read/write via platformdirs
│   ├── output.py                   # All rendering: table/json/csv, quiet mode
│   ├── errors.py                   # dataikuapi exception → user-friendly message + exit code
│   └── commands/                   # one file per noun (31 command groups)
├── dataiku-devkit/                 # AI agent DevKit
│   ├── skills/
│   │   ├── dataiku/
│   │   │   ├── SKILL.md            # Platform knowledge router
│   │   │   └── references/         # Platform reference docs
│   │   └── dku-cli/
│   │       ├── SKILL.md            # CLI operations reference
│   │       └── references/
│   │           └── commands.md     # Full command reference with flags
│   └── agents/
│       ├── plugin-reviewer.md      # Deep plugin code review
│       ├── dss-explorer.md         # Explore DSS projects via CLI
│       └── tool-designer.md        # Design agent tool schemas
├── benchmark/                      # 9-tier agent performance benchmark (192 scenarios)
├── tests/                          # CLI unit tests
└── pyproject.toml
```

---

## Development

```bash
git clone https://github.com/dataiku/dataiku-cli.git
cd dataiku-cli
uv sync
uv run pre-commit install
uv run pytest -v

# Install CLI globally
uv tool install --from . dku-cli
```

**Skills** (available anywhere the DevKit is installed):

| Skill | When to use |
|-------|-------------|
| `cli-meta-analysis` | After any session using the dku CLI or Dataiku skills — surfaces friction and gaps, writes to `.learnings/PENDING.md` |

**Slash commands** (Claude Code, when working in this repo):

| Command | When to use |
|---------|-------------|
| `/cli-improvement` | When you have benchmark results or learnings to turn into fixes — also reads `.learnings/PENDING.md` |
| `/cli-pr-review` | Before merging PRs that touch CLI commands, flags, or skill docs |

---

## License

Apache 2.0
