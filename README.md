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
npx skills add github:dataiku/dataiku-cli -g -a codex                   # DevKit (skills) — Codex
```

## Why dku-cli?

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

## Installation

The DevKit ships two independent components. Install what you need — or both.

---

### `dku` CLI

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

---

### Dataiku DevKit (skills + agents)

The DevKit teaches AI coding agents how to use the CLI and build Dataiku plugins. Installing it gives your agent 2 skills (28 reference docs) and 3 subagents. The skills reference `dku` commands throughout — install the CLI too if you haven't already.

| Component | Type | Description |
|-----------|------|-------------|
| `dataiku` | Skill | Platform knowledge — 28 reference docs covering plugins, formulas, LLM Mesh, agents, webapps, scenarios, MLOps, scaffolding, and deployment |
| `dku-cli` | Skill | CLI operations — 139 commands, chaining patterns, composability |
| `plugin-reviewer` | Agent | Deep code review against a structured checklist |
| `dss-explorer` | Agent | Explore a DSS project via CLI and produce a structured report |
| `tool-designer` | Agent | Design agent tool schemas and implementation plans |

The `dku-cli` skill alone produces the 30-50% cost reduction in the [benchmark](#benchmark-agent-performance) below. The `dataiku` skill adds plugin scaffolding, platform knowledge, and code review.

#### Claude Code — via marketplace (recommended)

```bash
/plugin marketplace add git@github.com:dataiku/dataiku-cli.git
/plugin install dataiku-devkit@dataiku-devkit
```

SSH is recommended over HTTPS — key-based auth means background updates work without a token. After installation, updates are one command:

```bash
/plugin marketplace update
```

#### Claude Code — local (from cloned repo)

```bash
/plugin marketplace add ./
/plugin install dataiku-marketplace@dataiku-devkit
```

#### Codex, Cursor, Copilot, and 40+ other agents — via npx skills

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

---

## Project Structure

```
dataiku-cli/
├── src/dku_cli/           # CLI source (Python package, 139 commands)
├── dataiku-devkit/        # AI agent DevKit
│   ├── .claude-plugin/    # Plugin manifest (Claude Code marketplace)
│   ├── skills/
│   │   ├── dataiku/       # Platform knowledge (28 reference docs)
│   │   └── dku-cli/       # CLI operations reference
│   └── agents/            # 3 subagents (plugin-reviewer, dss-explorer, tool-designer)
├── benchmark/             # 9-tier agent performance benchmark (192 scenarios)
├── tests/                 # CLI unit tests (298 tests)
└── docs/                  # Command → API mapping
```

## Authentication

### Profiles

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

### Credential Storage

Credentials are resolved in this order:

1. **CLI flags**: `--url` + `--api-key`
2. **Environment variables**: `DKU_URL` + `DKU_API_KEY`
3. **Stored profile**: selected by `--profile`, otherwise the active profile
4. **OS keychain**: macOS Keychain, GNOME Keyring, Windows Credential Manager
5. **Fallback file**: `~/.config/dku/credentials.toml` (0600 permissions)

Defaults resolve in a similarly predictable order:

1. **Project**: `--project` → `DKU_PROJECT` → active profile `default_project`
2. **Output**: `-o/--output` → config `output` → command fallback

### CI/CD

```bash
export DKU_URL=https://dss.company.com
export DKU_API_KEY=$DSS_API_KEY
dku project list -o json
```

## Agentic Workflow

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

## Benchmark: Agent Performance

We benchmarked how AI agents (Claude Code) perform DSS tasks using `dku` CLI commands vs writing `dataikuapi` Python scripts directly. Both approaches use `dataikuapi` under the hood — the CLI just gives agents a higher-level interface with less boilerplate per operation.

**Setup:** 12 runs — 2 tasks (simple, complex) × 2 approaches × 3 runs each. Model: Claude Opus, headless (`claude -p --dangerously-skip-permissions`). Validated against DSS state + ground truth data.

- **Simple task:** Create project, upload 2 CSVs, join, group by tier+region, compute revenue (8 validation checks)
- **Complex task:** All of simple + ML model, agent, LLM completion (11 validation checks)

### Results

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

### Why CLI Helps Agents

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

## Output Formats

All list/get commands support `-o` / `--output`:

```bash
dku project list                    # Table (default) — for humans
dku project list -o json | jq '.[].key'  # JSON — for scripting
dku project list -o csv > projects.csv   # CSV — for spreadsheets
```

Persist a default: `dku config set output json`. For agents, use JSON + quiet mode: `dku -q project list -o json`.

For machine-readable failures, add `--errors json`. Success payloads still go to stdout and error payloads go to stderr.

```bash
dku --errors json recipe get missing_recipe -P MYPROJECT -o json
```

## JSON Input

Creation and mutation commands accept structured JSON:

```bash
dku dataset set-schema ds1 -P PROJ --definition '{"columns":[...]}'  # Literal
dku recipe set-code my_recipe -P PROJ --code @transform.py           # From file
cat schema.json | dku dataset set-schema ds1 -P PROJ --definition -  # From stdin
```

## Configuration

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

## Development

```bash
git clone https://github.com/dataiku/dataiku-cli
cd dataiku-cli
uv sync
uv run dku --help
uv run pytest -v
```

## License

Apache 2.0

---

## Command Reference

<details>
<summary>All 139 commands across 25 groups (click to expand)</summary>

### `dku project`

```bash
dku project list                              # List all projects
dku project get MYPROJECT                     # Project details
dku project create MYPROJECT --name "Name"    # Create project
dku project delete MYPROJECT --confirm        # Delete (irreversible)
dku project duplicate PROJ --target-key NEW --target-name "New"
dku project export MYPROJECT -d ./exports     # Export as ZIP
dku project variables -P MYPROJECT            # Show variables
dku project set-variables -P MYPROJECT --set env=production
dku project permissions -P MYPROJECT          # Show permissions
dku project set-permissions -P MYPROJECT --definition @perms.json
dku project tags -P MYPROJECT                 # Show tags
```

### `dku dataset`

```bash
dku dataset list -P MYPROJECT                 # List datasets
dku dataset create raw_data --type UploadedFiles -P MYPROJECT
dku dataset upload raw_data ./data.csv -P MYPROJECT  # Upload + auto-detect format/schema
dku dataset schema my_dataset -P MYPROJECT    # Show schema
dku dataset set-schema my_dataset -P MYPROJECT --definition '{"columns":[...]}'
dku dataset head my_dataset -P MYPROJECT -n 5 # Preview rows
dku dataset build my_dataset --wait           # Build and wait
dku dataset get-definition my_dataset -P MYPROJECT  # Full JSON
dku dataset get-definition my_dataset -P MYPROJECT -o json
dku dataset set-definition my_dataset -P MYPROJECT --definition @def.json
dku dataset clear my_dataset -P MYPROJECT     # Clear data
dku dataset delete old_dataset -P MYPROJECT   # Delete
```

### `dku recipe`

```bash
dku recipe list -P MYPROJECT                  # List recipes
dku recipe create transform --type python --input raw_data --output clean_data -P MYPROJECT
dku recipe get my_recipe -P MYPROJECT         # Recipe details
dku recipe set-code transform --code @transform.py -P MYPROJECT
dku recipe get-code transform -P MYPROJECT    # Print code to stdout
dku recipe get-code transform -P MYPROJECT -o json
dku recipe run my_recipe --wait               # Run and wait
dku recipe add-input my_recipe --ref extra_ds -P MYPROJECT
dku recipe add-output my_recipe --ref result_ds -P MYPROJECT
dku recipe set-definition my_recipe --definition @def.json -P MYPROJECT
dku recipe check-schema my_recipe -P MYPROJECT    # Preview schema updates
dku recipe apply-schema my_recipe -P MYPROJECT    # Apply schema updates
dku recipe create-llm-eval rag_eval --input qa_data --eval-store eval_store_1 --output eval_scored --output-metrics eval_metrics -P MYPROJECT
dku recipe create-agent-eval agent_eval --input agent_runs --eval-store agent_store_1 --output eval_out --output-metrics eval_metrics -P MYPROJECT
dku recipe delete my_recipe -P MYPROJECT      # Delete
```

For `dku recipe create-llm-eval` and `dku recipe create-agent-eval`, any dataset passed with `--output` or `--output-metrics` must already exist in DSS. The CLI now validates that upfront and fails directly if those datasets are missing.

### `dku scenario`

```bash
dku scenario list -P MYPROJECT                # List scenarios
dku scenario create daily_build -P MYPROJECT  # Create
dku scenario run my_scenario --wait           # Run and wait
dku scenario abort my_scenario -P MYPROJECT   # Abort running
dku scenario status my_scenario -P MYPROJECT  # Recent runs
dku scenario get-definition my_scenario -P MYPROJECT
dku scenario get-definition my_scenario -P MYPROJECT -o json
dku scenario set-definition my_scenario -P MYPROJECT --definition @def.json
dku scenario delete my_scenario -P MYPROJECT  # Delete
```

### `dku job`

```bash
dku job list -P MYPROJECT                     # List recent jobs
dku job run --target my_dataset -P MYPROJECT  # Build target(s)
dku job run --target ds1 --target ds2 --wait  # Build multiple + wait
dku job status JOB_ID -P MYPROJECT            # Job details
dku job log JOB_ID -P MYPROJECT               # View job log
dku job abort JOB_ID -P MYPROJECT             # Abort job
dku job wait JOB_ID -P MYPROJECT --timeout 300  # Wait with timeout
```

### `dku library`

```bash
dku library list -P MYPROJECT                 # List files
dku library write python/utils/helpers.py --content @helpers.py -P MYPROJECT
dku library read python/utils/helpers.py -P MYPROJECT   # Print to stdout
dku library mkdir python/utils -P MYPROJECT   # Create directory
dku library delete python/utils/old.py -P MYPROJECT
```

### `dku agent`

```bash
dku agent list -P MYPROJECT                   # List agents
dku agent create my_agent --type TOOLS_USING_AGENT -P MYPROJECT
dku agent get my_agent -P MYPROJECT           # Settings
dku agent add-tool my_agent --tool tool1 -P MYPROJECT
dku agent set-llm my_agent --llm-id llm1 -P MYPROJECT
dku agent wake-up my_agent -P MYPROJECT       # Start
dku agent shutdown my_agent -P MYPROJECT      # Stop
dku agent status my_agent -P MYPROJECT        # Check state
dku agent delete my_agent -P MYPROJECT        # Delete
```

### `dku agent-tool`

```bash
dku agent-tool list -P MYPROJECT              # List tools
dku agent-tool get tool1 -P MYPROJECT         # Tool settings
dku agent-tool run tool1 --input '{"query":"..."}' -P MYPROJECT
dku agent-tool delete tool1 -P MYPROJECT      # Delete
```

### `dku knowledge`

```bash
dku knowledge list -P MYPROJECT               # List knowledge banks
dku knowledge create my_kb -P MYPROJECT       # Create
dku knowledge get my_kb -P MYPROJECT          # Settings
dku knowledge build my_kb --wait -P MYPROJECT # Build and wait
dku knowledge search my_kb --query "revenue" -P MYPROJECT
dku knowledge delete my_kb -P MYPROJECT       # Delete
```

`dku knowledge get` expects JSON from the DSS API. On getitstarted instances, the sleep/wake page can intercept the request and return HTML instead. When that happens, the CLI fails explicitly and tells you to wake the instance in the browser before retrying.

### `dku llm`

```bash
dku llm list -P MYPROJECT                     # List completion LLMs
dku llm list --purpose TEXT_EMBEDDING_EXTRACTION -P MYPROJECT
dku llm completion LLM_ID "Summarize this" -P MYPROJECT
dku llm completion LLM_ID "Extract entities" --system "You are a NER model" --json-output
dku llm embeddings LLM_ID --text "sample text" -P MYPROJECT
```

`dku llm list` defaults to `GENERIC_COMPLETION`. `dku llm embeddings` only accepts LLM IDs available for `TEXT_EMBEDDING_EXTRACTION` in the target project. Use `dku llm list --purpose TEXT_EMBEDDING_EXTRACTION` to find a compatible model.

### `dku bundle`

```bash
dku bundle list -P MYPROJECT                  # List bundles
dku bundle export v1 -P MYPROJECT             # Create snapshot
dku bundle download v1 --dest ./bundles -P MYPROJECT
dku bundle import ./bundle.zip -P MYPROJECT   # Import archive
dku bundle activate v1 -P MYPROJECT           # Activate
```

### `dku api-service`

```bash
dku api-service list -P MYPROJECT             # List services
dku api-service create my_api -P MYPROJECT    # Create
dku api-service get my_api -P MYPROJECT       # Settings
dku api-service create-package my_api -P MYPROJECT
dku api-service list-packages my_api -P MYPROJECT
```

### `dku wiki`

```bash
dku wiki list -P MYPROJECT                    # List articles
dku wiki create "Setup Guide" --body @guide.md -P MYPROJECT
dku wiki get ARTICLE_ID -P MYPROJECT          # Read article
```

### `dku sql`

```bash
dku sql query "SELECT * FROM users LIMIT 10" --connection my_pg
dku sql query @query.sql --connection my_pg   # From file
```

### `dku flow`

```bash
dku flow graph -P MYPROJECT                   # Flow graph summary
dku flow graph -P MYPROJECT -o json           # Full graph as JSON
dku flow zones -P MYPROJECT                   # List zones
dku flow create-zone "Staging" -P MYPROJECT   # Create zone
dku flow propagate ds1 -P MYPROJECT           # Schema propagation from dataset
dku flow check -P MYPROJECT                   # Consistency check
dku flow sources -P MYPROJECT                 # Find root datasets
dku flow successors ds1 -P MYPROJECT          # Downstream nodes
```

### `dku plugin`

```bash
dku plugin list                               # List plugins
dku plugin push ./my-plugin.zip               # Upload plugin
dku plugin settings my-plugin                 # View settings
dku plugin settings my-plugin --set k=v       # Update setting
```

### `dku code-env`

```bash
dku code-env list                             # List code environments
dku code-env get py39                         # Code env details
dku code-env create my-env                    # Create new code env
dku code-env delete py39                      # Delete code env
dku code-env update py39                      # Update packages
```

### `dku connection`

```bash
dku connection list                           # List connections (admin)
dku connection create my_pg --type PostgreSQL --definition @conn.json
dku connection test my_connection             # Test a connection
```

### `dku user`

```bash
dku user list                                 # List DSS users
dku user create jdoe --display-name "John Doe" --email john@example.com
```

### `dku model`

```bash
dku model list -P MYPROJECT                   # List saved models
dku model get MODEL_ID -P MYPROJECT           # Model details
dku model versions MODEL_ID -P MYPROJECT      # List model versions
```

### `dku folder`

```bash
dku folder list -P MYPROJECT                  # List managed folders
dku folder ls FOLDER_ID -P MYPROJECT          # List folder contents
dku folder upload FOLDER_ID ./data.csv -P MYPROJECT
dku folder download FOLDER_ID /data.csv -P MYPROJECT
```

### `dku webapp`

```bash
dku webapp list -P MYPROJECT                  # List web apps
dku webapp start WEBAPP_ID -P MYPROJECT       # Start backend
dku webapp stop WEBAPP_ID -P MYPROJECT        # Stop backend
dku webapp status WEBAPP_ID -P MYPROJECT      # Check status
```

### `dku macro`

```bash
dku macro list -P MYPROJECT                   # List macros
dku macro run MACRO_ID -P MYPROJECT           # Run macro
dku macro run MACRO_ID --params '{"key":"value"}' --wait
```

### `dku config`

```bash
dku config set default_project MYPROJECT      # Set default project
dku config get default_project                # Get config value
dku config set output json                    # Set default output format
dku config list                               # Show all config
dku config path                               # Print config file path
dku config variables                          # Instance-level variables
dku config set-variables --set key=value      # Set instance variables
```

### `dku whoami`

```bash
dku whoami    # ◆ chris on https://dss.example.com (DSS 14.0.2) [admin]
```

</details>
