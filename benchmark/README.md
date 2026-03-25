# dku-cli Agent Benchmark

Evaluates how well AI coding agents use the dku-cli and Dataiku DevKit skills against a real Dataiku DSS sandbox. The benchmark loop: run test → find CLI/skill limitation → fix → re-run → measure improvement.

**Currently uses Claude Code (Opus) only.** Codex adapter exists but is not active.

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

## Usage

```bash
# Full suite — all 192 scenarios (expensive, ~$20+)
uv run python -m benchmark.runner --agent claude

# Single test
uv run python -m benchmark.runner --test o1_finserv_rag_demo --agent claude --parallel 1

# By tier
uv run python -m benchmark.runner --tier 9 --agent claude          # open-ended only
uv run python -m benchmark.runner --tier 6 --agent claude          # project builds
uv run python -m benchmark.runner --tier 7,8 --agent claude        # advanced + stress

# Dry run (show what would execute, no cost)
uv run python -m benchmark.runner --dry-run --agent claude --skip-preflight

# Adjust parallelism (default: 4)
uv run python -m benchmark.runner --parallel 1 --agent claude
```

## Test Tiers (192 scenarios)

| Tier | File | Count | What It Evaluates |
|------|------|-------|-------------------|
| 1 | `tier1_commands.yaml` + `tier1_generated.yaml` | 140 | Single-command knowledge — does the agent know the right `dku` command? |
| 2 | `tier2_flags.yaml` | 5 | Flag correctness — `-o json`, `-P PROJECT`, `--yes`, `-n N` |
| 3 | `tier3_chaining.yaml` | 3 | Chaining — are related commands `&&`-chained in a single bash call? |
| 4 | `tier4_skills.yaml` | 4 | Skill routing — does Claude invoke the right skill? |
| 5 | `tier5_agents.yaml` | 2 | Agent delegation — does Claude spawn the right subagent? |
| 6 | `projects.yaml` + `tier6_e2e.yaml` | 9 | Progressive project builds — create + upload → recipe pipeline → scenario → GenAI → full project |
| 7 | `tier7_errors.yaml` + `advanced.yaml` (partial) | 16 | Error recovery + advanced workflows: multi-recipe pipelines, flow ops, agents, bundles, SQL, diagnostics |
| 8 | `advanced.yaml` (partial) | 3 | Stress tests: multi-project ops, full GenAI pipeline, maximum complexity |
| 9 | `open_ended.yaml` | 10 | **Open-ended real-world prompts** — no step-by-step instructions, agent decides what to build |

### Tier 9: Open-Ended Scenarios (most valuable)

These simulate actual field work. The agent receives a business scenario and must figure out what to build.

| ID | Prompt Summary | Tests |
|----|---------------|-------|
| `o1_finserv_rag_demo` | "Build a demo for a financial services customer showing RAG + agentic capabilities" | KB, embedding, agent, data modeling |
| `o2_healthcare_pipeline` | "Healthcare company needs data pipeline for encounters, diagnoses, treatments" | Multi-dataset join, cleaning, aggregation |
| `o3_retail_customer360` | "Retail company wants unified customer profile from transactions + web + support" | 3-way join, segmentation, value metrics |
| `o4_content_moderation` | "Social media company wants AI-powered content moderation" | LLM classification, eval, agent |
| `o5_investigate_broken` | "Something is wrong with project X — do triage" | Diagnostic, flow check, job logs |
| `o6_insurance_claims` | "Insurance company wants claims processing with similarity search" | KB, embedding, agent, data pipeline |
| `o7_instance_health` | "You're a DSS admin — do a health check" | Read-only, cross-project, plugins, envs |
| `o8_manufacturing_qc` | "Manufacturing quality control analytics" | Sensor data, correlations, defect rates |
| `o9_migrate_pandas` | "Migrate this pandas script into Dataiku" | Script decomposition, recipe mapping |
| `o10_telecom_genai` | "Telecom churn prevention combining traditional analytics + GenAI" | Pipeline + KB + agent in one project |

### Tier 6: Progressive Project Builds

| ID | Complexity | What It Builds |
|----|-----------|---------------|
| `p1_create_and_upload` | Simple | Project + 1 dataset + upload CSV |
| `p2_multi_dataset` | Medium | Project + 3 related datasets |
| `p3_recipe_pipeline` | Medium | Dataset → Python recipe → output |
| `p4_scenario_automation` | Hard | Dataset → recipe → scenario |
| `p5_genai_project` | Hard | Dataset → embedding → knowledge bank |
| `p6_full_project` | Very hard | Datasets + recipes + library + wiki + variables |

## Architecture

```
benchmark/
├── config.yaml                    # Agent models, parallelism, timeout
├── .env                           # DSS credentials (gitignored)
├── agents/
│   ├── base.py                    # Abstract agent + AgentResult dataclass
│   ├── claude.py                  # Claude Code headless adapter (stream-json)
│   └── codex.py                   # Codex headless adapter (inactive)
├── scenarios/
│   ├── schema.py                  # Pydantic models for scenario YAML
│   ├── projects.yaml              # Tier 6: progressive project builds (p1-p6)
│   ├── advanced.yaml              # Tier 7-8: complex workflows (a1-a16)
│   ├── open_ended.yaml            # Tier 9: real-world prompts (o1-o10)
│   ├── tier1_commands.yaml        # Tier 1: hand-written command tests
│   ├── tier1_generated.yaml       # Tier 1: auto-generated from CLAUDE.md
│   ├── tier2_flags.yaml           # Tier 2: flag correctness
│   ├── tier3_chaining.yaml        # Tier 3: command chaining
│   ├── tier4_skills.yaml          # Tier 4: skill routing
│   ├── tier5_agents.yaml          # Tier 5: agent delegation
│   ├── tier6_e2e.yaml             # Tier 6: end-to-end workflows
│   └── tier7_errors.yaml          # Tier 7: error recovery
├── analyzer/
│   ├── trace_parser.py            # Parse JSONL from Claude headless output
│   ├── scorer.py                  # Score against rubrics
│   ├── reporter.py                # narrative.md + summary.json + terminal
│   └── recommender.py             # Actionable skill/doc patches
├── generator.py                   # Auto-generate tier 1 from CLAUDE.md
├── runner.py                      # Main orchestrator
└── reports/                       # Output dir (gitignored)
    └── {run_id}/
        ├── summary.json           # Per-test scores, commands, metrics
        ├── narrative.md           # Rich narrative per test with agent output
        └── recommendations.md     # Failure patterns + suggested fixes
```

## How It Works

1. **Pre-flight** — verifies DSS connectivity via `dku whoami`
2. **Project creation** — creates `BENCH_*` / `DEMO_*` projects for tests that need them
3. **Headless execution** — runs Claude via `claude -p --output-format stream-json --verbose --dangerously-skip-permissions --model opus --max-turns 15`
4. **Trace parsing** — extracts bash commands, skill invocations, agent spawns, file reads/writes from JSONL
5. **DSS verification** — runs `dku` commands post-test to verify actual DSS state (project exists, datasets created, recipes wired)
6. **Scoring** — command correctness (regex match), outcome verification (DSS state), efficiency (output tokens + call count)
7. **Reporting** — narrative.md with per-test breakdown, summary.json for aggregation, recommendations.md for patterns

## Scoring

Each test has a rubric with weighted dimensions:

| Dimension | What It Measures |
|-----------|-----------------|
| `command_correct` | Did the agent use the expected `dku` commands? (regex on trace) |
| `flags_correct` | Were the right flags used? (`-o json`, `--type`, etc.) |
| `outcome_verified` | Does the DSS state match expectations? (real `dku` verification commands) |
| `efficiency` | Output tokens + bash call count. Fewer = better. |
| `chaining` | Were related commands `&&`-chained? (tier 3 specific) |
| `skill_routing` | Did Claude invoke the right skill? (tier 4 specific) |

**Pass threshold: 0.70** (configurable in config.yaml)

## Reports

Reports are written to `benchmark/reports/{run_id}/`:

| File | Contents |
|------|----------|
| `summary.json` | Per-test scores, commands executed, output tokens, duration |
| `narrative.md` | Rich report: task, commands, score breakdown, agent output excerpt, CLI/skill insights |
| `recommendations.md` | Clustered failure patterns with suggested fixes |

## Known Friction Points (from benchmarking)

These are the top issues discovered through benchmark runs. They inform what to fix in the CLI and skill:

### 1. Pre-creating output datasets (~25% of wasted commands)
The agent manually creates Filesystem datasets before `dku recipe create`, even though `--output-ds` auto-creates them. This triggers a cascade: no `--type` → `--type Filesystem` without `-c` → `dku connection list` → `--type Filesystem -c filesystem_managed`. **4-7 wasted commands every time.**

### 2. Recipe create syntax confusion (~14% of wasted commands)
The agent tries wrong syntax first: positional type (`dku recipe create NAME python`), then missing `-i`/`--output-ds`, then `--output` instead of `--output-ds`, then `--help`, then correct. **2-4 wasted commands per recipe.**

### 3. Project delete / idempotent create (~6%)
When projects exist from prior runs, the agent tries `--confirm` (doesn't exist), `echo y |` (works but messy). The skill now documents `--yes` and `--if-not-exists`.

### 4. Knowledge bank create missing `--embedding-llm` (~6%)
The agent tries `dku knowledge create` without `--embedding-llm`, then needs `--help` to discover it. Also doesn't know to use `--purpose TEXT_EMBEDDING_EXTRACTION` to find embedding models.

### 5. `set-code` doesn't support stdin
The agent naturally tries heredoc (`dku recipe set-code NAME << 'EOF'`), which doesn't work. Must write to temp file then use `-c @/tmp/file.py`.

## Cost Estimates

| Scope | Claude (Opus) |
|-------|--------------|
| Single tier 1 test | ~$0.05 |
| Single tier 6/9 test | ~$0.15-0.30 |
| All tier 9 (10 tests) | ~$2-3 |
| All tier 6 (6 tests) | ~$1-2 |
| Full suite (192 tests) | ~$20-30 |

## Project Isolation

Test resources are created in DSS projects prefixed `BENCH_` or `DEMO_`. These are not automatically cleaned up:

```bash
# List benchmark projects
dku project list -o json | jq -r '.[] | select(.key | startswith("BENCH_") or startswith("DEMO_")) | .key'

# Delete all (careful!)
for key in $(dku project list -o json | jq -r '.[] | select(.key | startswith("BENCH_")) | .key'); do
  echo y | dku project delete "$key"
done
```

## Auto-Generating Tests

Expand tier 1 to cover all CLI commands (reads the command table from CLAUDE.md):

```bash
uv run python -m benchmark.generator
# Outputs: benchmark/scenarios/tier1_generated.yaml (130 scenarios)
```
