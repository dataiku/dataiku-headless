# dku-cli Agent Benchmark

Evaluates how well AI coding agents (Claude Code, Codex) can use the dku-cli and Dataiku DevKit skills against a real Dataiku DSS sandbox.

## Setup

```bash
# 1. Install dependencies (from project root)
uv sync

# 2. Configure DSS credentials
cp benchmark/.env.example benchmark/.env
# Edit benchmark/.env with your DSS URL and API key

# 3. Authenticate the CLI
source benchmark/.env
dku auth login --url "$DKU_URL" --api-key "$DKU_API_KEY"

# 4. Verify connectivity
dku whoami
```

### Agent Prerequisites

| Agent | Install | Verify |
|-------|---------|--------|
| Claude Code | `npm install -g @anthropic-ai/claude-code` | `claude --version` |
| Codex | `npm install -g @openai/codex` | `codex --version` |

## Usage

```bash
# Full suite — both agents, all tiers
python -m benchmark.runner

# Single agent
python -m benchmark.runner --agent claude
python -m benchmark.runner --agent codex

# Single tier
python -m benchmark.runner --tier 1
python -m benchmark.runner --tier 1,2,3

# Single test
python -m benchmark.runner --test t1_project_list

# Adjust parallelism
python -m benchmark.runner --parallel 8

# Dry run (show what would execute)
python -m benchmark.runner --dry-run

# Skip preflight DSS check
python -m benchmark.runner --skip-preflight
```

## Test Tiers

| Tier | Tests | What It Evaluates |
|------|-------|-------------------|
| 1 | 10 | Basic command knowledge — does the agent know the right `dku` command? |
| 2 | 5 | Flag correctness — `-o json`, `-P PROJECT`, `--yes`, `-n N` |
| 3 | 3 | Chaining — are related commands `&&`-chained in a single bash call? |
| 4 | 4 | Skill routing — does Claude invoke the right skill (new-plugin, deploy-plugin, etc.)? |
| 5 | 2 | Agent delegation — does Claude spawn the right subagent (dss-explorer, tool-designer)? |
| 6 | 3 | End-to-end workflows — multi-step pipelines, plugin build+deploy, diagnostics |
| 7 | 3 | Error recovery — graceful handling of non-existent resources |

## Auto-Generating Tests

Expand Tier 1 to cover all 140+ CLI commands:

```bash
python -m benchmark.generator
# Outputs: benchmark/scenarios/tier1_generated.yaml
```

## Reports

Reports are written to `benchmark/reports/{run_id}/`:

| File | Contents |
|------|----------|
| `summary.json` | Aggregate pass rates, per-tier breakdown, head-to-head comparison |
| `traces/{test_id}_{agent}.json` | Per-test trace with commands, scores, details |
| `recommendations.md` | Actionable improvements for skills, docs, and CLI |

## How It Works

1. **Pre-flight** — verifies DSS connectivity via `dku whoami`
2. **Project creation** — creates `BENCH_*` projects for tests that need them
3. **Parallel execution** — runs agents via headless CLI (`claude -p`, `codex exec`)
4. **Trace parsing** — extracts bash commands, skills invoked, agents spawned from JSONL output
5. **Verification** — runs `dku` commands to verify actual DSS state after each test
6. **Scoring** — evaluates against rubric (command correctness, flags, chaining, skill routing, outcomes)
7. **Reporting** — generates JSON summary, terminal output, and recommendations

## Agent Configurations

| Agent | Model | Mode |
|-------|-------|------|
| Claude Code | Opus | `claude -p --output-format json --dangerously-skip-permissions --model opus` |
| Codex | gpt-5.4 xhigh | `codex exec --json -m gpt-5.4 -c model_reasoning_effort="xhigh" --dangerously-bypass-approvals-and-sandbox` |

## Cost Estimates

| Scope | Claude (Opus) | Codex (gpt-5.4) |
|-------|--------------|-----------------|
| Single test | ~$0.10 | ~$0.05 |
| Tier 1 (10 tests) | ~$1.00 | ~$0.50 |
| Full suite (30 tests) | ~$5-15 | ~$3-8 |

## Project Isolation

All test resources are created in DSS projects prefixed `BENCH_`. These are not automatically cleaned up — delete them manually when done:

```bash
dku project list -o json | jq -r '.[] | select(.key | startswith("BENCH_")) | .key'
```
