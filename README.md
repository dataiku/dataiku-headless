# ◆ dku-cli — Dataiku DevKit

Install AI coding agents with the knowledge to build in Dataiku DSS.

---

## What's in it?

| Component | What it does |
|-----------|-------------|
| `/dataiku` skill | Teaches AI what Dataiku is — plugins, formulas, agents, scenarios, LLM Mesh |
| `/dataiku-internal-branding` skill | Dataiku's design system — colors, typography, component patterns |
| `/dku-cli` skill | Teaches AI how to operate Dataiku via shell commands |
| `dku` CLI | Binary that actually runs Dataiku operations |
| `/cli-meta-analysis` skill | Reflects on AI's CLI usage — spots inefficiencies |
| Subagents | plugin-reviewer, dss-explorer, tool-designer |

> Skills = knowledge (what exists). CLI = action (what runs). You can have skills without CLI, but you need both to operate Dataiku.

---

## What do you want?

| Goal | Install |
|------|---------|
| AI understands Dataiku (write code, answer questions, review) | Skills only |
| AI actually operates Dataiku (run jobs, build datasets) | Skills + CLI |
| Full DevKit (skills + slash commands + subagents) | Marketplace bundle |

---

## Install

### Skills only (any AI tool)

```bash
npx skills add dataiku/dataiku-cli -g -a claude-code   # Claude Code
npx skills add dataiku/dataiku-cli -g -a codex        # Codex
```

### Skills + CLI

```bash
# Step 1 — skills
npx skills add dataiku/dataiku-cli -g -a claude-code

# Step 2 — CLI
git clone git@github.com:dataiku/dataiku-cli.git
cd dataiku-cli
uv tool install --from . dku-cli
dku --version

# Step 3 — connect
dku auth login
dku whoami
```

### Full DevKit (Claude Code only)

```
/plugin marketplace add dataiku/dataiku-cli
```

Then follow Step 2 and 3 from Skills + CLI.

---

## Quick Start

```bash
dku whoami                  # verify connection
dku project list            # list projects
dku dataset head DS -P PROJ # preview data
```

Full reference: [dataiku-devkit/skills/dku-cli/references/commands.md](dataiku-devkit/skills/dku-cli/references/commands.md)

---

## Benchmark

12 runs — 2 tasks (simple, complex) x 2 approaches x 3 runs each. Claude Opus, headless. Validated against DSS state + ground truth.

| | Python API | dku CLI | Delta |
|---|---|---|---|
| Success rate | 6/6 (100%) | 6/6 (100%) | Tie |
| Simple cost | $1.49 avg | $1.04 avg | **-30%** |
| Complex cost | $2.83 avg | $1.40 avg | **-50%** |
| Simple wall time | 405s | 258s | **-36%** |
| Complex wall time | 684s | 402s | **-41%** |
| Simple tool calls | 39 avg | 32 avg | **-18%** |
| Complex tool calls | 60 avg | 43 avg | **-27%** |

**Why CLI helps agents:** `&&` chaining reduces tool calls, `--wait` eliminates polling, `dku dataset upload` combines file upload + format detection + schema inference in one command.

See [benchmark/README.md](benchmark/README.md) for per-run data and methodology.

---

## Update

```bash
# Skills
npx skills update -g

# CLI
cd /path/to/dataiku-cli
git pull
uv tool install --from . dku-cli --force --reinstall
```

---

## Development

```bash
uv sync
uv run pre-commit install
uv run pytest -v
```

---

## License

Apache 2.0
