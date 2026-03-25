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
- **`dku` CLI** — 139 commands across 25 groups. A `kubectl`-style tool for terminal use, CI/CD pipelines, and agent shell commands.
- **Dataiku DevKit** — 2 skills, 28 platform reference docs, and 3 subagents that teach AI coding agents how to build plugins, manage projects, and operate DSS.

```bash
uv tool install git+https://github.com/dataiku/dataiku-cli.git          # CLI
/plugin marketplace add git@github.com:dataiku/dataiku-cli.git          # DevKit (skills+agents) — Claude Code
npx skills add dataiku/dataiku-cli -g -a codex                          # DevKit (skills) — Codex
```

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

## Quick Start

```bash
# Authenticate
dku auth login
# DSS URL: https://my-dss.company.com
# API Key: ········
# ◆ Connected to DSS 14.0.2 as chris

# Quick status check
dku whoami
# ◆ chris on https://my-dss.company.com (DSS 14.0.2) [admin]

# List projects
dku project list

# Create a project
dku project create MYPROJECT --name "My Project"

# Preview a dataset
dku dataset head my_dataset -P MYPROJECT

# List plugins (JSON for scripting)
dku plugin list -o json | jq '.[].id'
```

---

## `dku` CLI

### Installation

Requires Python 3.10+ and [uv](https://docs.astral.sh/uv/).

**Remote:**
```bash
uv tool install git+https://github.com/dataiku/dataiku-cli.git
```

**Local (from cloned repo):**
```bash
git clone https://github.com/dataiku/dataiku-cli && cd dataiku-cli
uv tool install .
```

**Update:**
```bash
uv tool install --reinstall git+https://github.com/dataiku/dataiku-cli.git
```

### Authentication

#### Profiles

dku-cli supports named profiles for managing multiple DSS instances:

```bash
# Login to default profile
dku auth login

# Login to a named profile
dku auth login --profile production

# Non-interactive (CI/CD)
dku auth login --profile prod --url https://dss.example.com --api-key YOUR_KEY

# Switch active profile
dku auth switch production

# List profiles
dku auth list

# Check current status
dku auth status

# Remove a profile
dku auth logout --profile production

# Remove all stored profiles
dku auth logout --all
```

#### Credential Storage

Credentials are resolved in this order:

1. **CLI flags**: `--url` + `--api-key`
2. **Environment variables**: `DKU_URL` + `DKU_API_KEY`
3. **Stored profile**: selected by `--profile`, otherwise the active profile
4. **OS keychain**: macOS Keychain, GNOME Keyring, Windows Credential Manager
5. **Fallback file**: `~/.config/dku/credentials.toml` (0600 permissions)

Defaults resolve in a similarly predictable order:

1. **Project**: `--project` → `DKU_PROJECT` → active profile `default_project`
2. **Output**: `-o/--output` → config `output` → command fallback

#### CI/CD

```bash
export DKU_URL=https://dss.company.com
export DKU_API_KEY=$DSS_API_KEY
dku project list -o json
```

### Output Formats

All list/get commands support `-o` / `--output`:

```bash
dku project list                         # Table (default) — for humans
dku project list -o json | jq '.[].key'  # JSON — for scripting
dku project list -o csv > projects.csv   # CSV — for spreadsheets
```

Persist a default: `dku config set output json`. For agents, use JSON + quiet mode: `dku -q project list -o json`.

For machine-readable failures, add `--errors json`. Success payloads still go to stdout and error payloads go to stderr.

```bash
dku --errors json recipe get missing_recipe -P MYPROJECT -o json
```

### JSON Input

Creation and mutation commands accept structured JSON:

```bash
dku dataset set-schema ds1 -P PROJ --definition '{"columns":[...]}'  # Literal
dku recipe set-code my_recipe -P PROJ --code @transform.py           # From file
cat schema.json | dku dataset set-schema ds1 -P PROJ --definition -  # From stdin
```

### Configuration

```toml
# ~/.config/dku/config.toml
active_profile = "sandbox"
output = "json"

[sandbox]
url = "https://sandbox.dss.example.com"
default_project = "MYPROJECT"

[production]
url = "https://prod.dss.example.com"
```

| Variable | Description |
|---|---|
| `DKU_URL` | DSS instance URL |
| `DKU_API_KEY` | API key |
| `DKU_PROJECT` | Default project key |

### Agentic Workflow

Build a complete DSS project from scratch — all composable shell commands:

```bash
dku project create AGENT_TEST --name "Agent Test"
dku project set-variables -P AGENT_TEST --set env=dev
dku dataset create raw_data --type UploadedFiles -P AGENT_TEST
dku dataset upload raw_data data.csv -P AGENT_TEST
dku dataset set-schema raw_data -P AGENT_TEST --definition @schema.json
dku recipe create transform --type python --input raw_data --output clean_data -P AGENT_TEST
dku recipe set-code transform -P AGENT_TEST --code @transform.py
dku library write python/utils/helpers.py -P AGENT_TEST --content @helpers.py
dku scenario create daily_build -P AGENT_TEST
dku knowledge create my_kb -P AGENT_TEST
dku bundle export v1 -P AGENT_TEST
dku project delete AGENT_TEST --confirm
```

### Command Reference

Full reference for all 139 commands across 25 groups: [docs/commands.md](docs/commands.md)

---

## Dataiku DevKit

### Installation

The DevKit teaches AI coding agents how to use the CLI and build Dataiku plugins. Installing it gives your agent 2 skills (28 reference docs) and 3 subagents. The skills reference `dku` commands throughout — install the CLI too if you haven't already.

#### Claude Code — via marketplace (recommended)

```bash
/plugin marketplace add git@github.com:dataiku/dataiku-cli.git
/plugin install dataiku-devkit@dataiku-marketplace
```

SSH is recommended over HTTPS — key-based auth means background updates work without a token. After installation, updates are one command:

```bash
/plugin marketplace update
```

#### Claude Code — local (from cloned repo)

```bash
/plugin marketplace add ./
/plugin install dataiku-devkit@dataiku-marketplace
```

#### Codex, Cursor, Copilot, and other agents — via npx skills

```bash
npx skills add dataiku/dataiku-cli -g -a codex    # OpenAI Codex
npx skills add dataiku/dataiku-cli -g -a cursor   # Cursor
```

`-g` installs globally across all projects. Update later with:

```bash
npx skills update dataiku/dataiku-cli
```

#### Manual (no Node.js, no git required)

Copy `dataiku-devkit/skills/` and `dataiku-devkit/agents/` into your agent's directories (e.g., `~/.claude/skills/`, `~/.claude/agents/`).

### Components

| Component | Type | Description |
|-----------|------|-------------|
| `dataiku` | Skill | Platform knowledge — 28 reference docs covering plugins, formulas, LLM Mesh, agents, webapps, scenarios, MLOps, scaffolding, and deployment |
| `dku-cli` | Skill | CLI operations — 139 commands, chaining patterns, composability |
| `plugin-reviewer` | Agent | Deep code review against a structured checklist |
| `dss-explorer` | Agent | Explore a DSS project via CLI and produce a structured report |
| `tool-designer` | Agent | Design agent tool schemas and implementation plans |

### Benchmark

We benchmarked how AI agents (Claude Code) perform DSS tasks using `dku` CLI commands vs writing `dataikuapi` Python scripts directly. Both approaches use `dataikuapi` under the hood — the CLI just gives agents a higher-level interface with less boilerplate per operation.

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

Note: CLI runs still use Python for operations the CLI can't handle (recipe config, ML training) — the advantage is using CLI for the ~60% that's CRUD/inspection/builds.

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
│   └── commands/                   # 25 command groups (one file per noun)
│       ├── project.py
│       ├── dataset.py
│       ├── recipe.py
│       ├── scenario.py
│       ├── job.py
│       ├── library.py
│       ├── agent.py
│       ├── agent_tool.py
│       ├── knowledge.py
│       ├── llm.py
│       ├── flow.py
│       ├── bundle.py
│       ├── api_service.py
│       ├── wiki.py
│       ├── sql.py
│       ├── plugin.py
│       ├── codeenv.py
│       ├── connection.py
│       ├── model.py
│       ├── folder.py
│       ├── webapp.py
│       ├── macro.py
│       ├── user.py
│       ├── auth_cmd.py
│       └── config_cmd.py
├── dataiku-devkit/                 # AI agent DevKit
│   ├── .claude-plugin/
│   │   └── plugin.json             # Plugin manifest (Claude Code marketplace)
│   ├── skills/
│   │   ├── dataiku/
│   │   │   ├── SKILL.md            # Platform knowledge router
│   │   │   └── references/         # 28 reference docs
│   │   └── dku-cli/
│   │       ├── SKILL.md            # CLI operations reference
│   │       └── references/
│   │           └── commands.md     # Full command reference with flags
│   └── agents/
│       ├── plugin-reviewer.md      # Deep plugin code review
│       ├── dss-explorer.md         # Explore DSS projects via CLI
│       └── tool-designer.md        # Design agent tool schemas
├── benchmark/                      # 9-tier agent performance benchmark (192 scenarios)
│   ├── README.md
│   ├── runner.py
│   ├── generator.py
│   ├── config.yaml
│   ├── scenarios/
│   └── agents/
├── tests/                          # CLI unit tests (298 tests)
│   ├── conftest.py                 # Mock fixtures, patch_client
│   ├── test_auth.py
│   ├── test_output.py
│   └── commands/                   # Per-group test files (27 files)
├── docs/
│   ├── commands.md                 # Full CLI command reference
│   └── command-api-mapping.md      # CLI command → dataikuapi call mapping
└── pyproject.toml
```

---

## Development

```bash
git clone https://github.com/dataiku/dataiku-cli
cd dataiku-cli
uv sync
uv run dku --help
uv run pytest -v
```

---

## License

Apache 2.0
