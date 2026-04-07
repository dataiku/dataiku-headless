# dku-cli Agent Benchmark

Evaluates how well AI coding agents use the dku-cli and Dataiku DevKit skills against a real Dataiku DSS sandbox. The benchmark loop: run test → find CLI/skill limitation → fix → re-run → measure improvement.

**Key design principle:** The agent reads the actual skill files (`SKILL.md`) during tests — no hardcoded cheat sheets. This means benchmark results directly measure skill quality.

**Currently uses Claude Code (Opus) only.** Codex adapter exists but is not active.

## Prerequisites

- **Claude Code CLI** — installed and authenticated (`claude --version`). The runner invokes `claude -p` in headless mode.
- **Dataiku DSS instance** — a sandbox with API access. Tests create/delete projects freely.
- **`dku` CLI** — installed and on PATH (`uv tool install --from . dku-cli` or `uv run dku`).

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

# 5. Run a quick smoke test (7 tests, ~$0.50)
uv run python -m benchmark.runner --tag smoke
```

## Usage

```bash
# Full suite — all 206 scenarios (expensive, ~$20+)
uv run python -m benchmark.runner --agent claude

# By tag (recommended for quick validation)
uv run python -m benchmark.runner --tag smoke               # 7 fast tests (~$0.50)
uv run python -m benchmark.runner --tag migration            # Alteryx/Excel/pandas migrations
uv run python -m benchmark.runner --tag fixture              # All fixture-backed tests

# By tier
uv run python -m benchmark.runner --tier 9                   # Open-ended only
uv run python -m benchmark.runner --tier 10                  # Migration scenarios
uv run python -m benchmark.runner --tier 6,10                # Projects + migrations

# Single test
uv run python -m benchmark.runner --test fx_sales_pipeline --parallel 1

# Dry run (show what would execute, no cost)
uv run python -m benchmark.runner --dry-run --skip-preflight

# Adjust parallelism (default: 4)
uv run python -m benchmark.runner --parallel 1
```

## Test Tiers (206 scenarios)

| Tier | Files | Count | What It Evaluates |
|------|-------|-------|-------------------|
| 1 | `tier1_commands.yaml` + `tier1_generated.yaml` | 140 | Single-command knowledge — does the agent know the right `dku` command? |
| 2 | `tier2_flags.yaml` | 5 | Flag correctness — `-o json`, `-P PROJECT`, `--yes`, `-n N` |
| 3 | `tier3_chaining.yaml` | 3 | Chaining — are related commands `&&`-chained in a single bash call? |
| 4 | `tier4_skills.yaml` | 4 | Skill routing — does Claude invoke the right skill? |
| 5 | `tier5_agents.yaml` | 2 | Agent delegation — does Claude spawn the right subagent? |
| 6 | `projects.yaml` + `tier6_e2e.yaml` + `fixture_pipelines.yaml` | 11 | Progressive builds + fixture-backed pipelines (sales, healthcare) |
| 7 | `tier7_errors.yaml` + `advanced.yaml` (partial) | 16 | Error recovery + advanced workflows |
| 8 | `advanced.yaml` (partial) | 3 | Stress tests: multi-project, max complexity |
| 9 | `open_ended.yaml` | 10 | Open-ended real-world prompts — agent decides what to build |
| 10 | `migration_*.yaml` + `auto_fixtures.yaml` | 8 | Migration scenarios (Alteryx, Excel, pandas) + auto-generated fixture tests |

### Tags

Scenarios can be tagged for quick filtering with `--tag`:

| Tag | Count | Purpose |
|-----|-------|---------|
| `smoke` | 7 | Fast validation — 5 tier-1 commands + 1 chaining + 1 fixture pipeline |
| `fixture` | ~10 | All tests using fixture data (not agent-generated) |
| `migration` | 3 | Alteryx/Excel/pandas migration scenarios |
| `alteryx` | 2 | Alteryx-specific tests |
| `excel` | 2 | Excel-specific tests |
| `pandas` | 2 | Pandas migration tests |
| `auto` | 5 | Auto-generated from fixture directories |

## Fixtures

Pre-built test data in `benchmark/fixtures/`. Scenarios reference fixtures instead of relying on agent-generated synthetic data.

```
fixtures/
  catalog.yaml                     # Index of all fixture sets
  sales/test1/                     # 50 orders, 20 customers, 10 products
  alteryx/test1/                   # 100-row customer segmentation + workflow spec
  excel/test1/                     # 80-row financial report + workbook spec
  pandas/test1/                    # 200-row ETL input + script.py to migrate
  healthcare/test1/                # 100 encounters, 80 diagnoses, 60 treatments
```

### Drop-and-go: adding new fixtures

```bash
# 1. Create a fixture directory
mkdir -p benchmark/fixtures/alteryx/test2

# 2. Add files (at minimum: input data + optional spec)
cp my_data.csv benchmark/fixtures/alteryx/test2/input.csv
cp my_spec.md benchmark/fixtures/alteryx/test2/workflow_spec.md   # optional

# 3. Auto-generate scenarios from all fixture directories
uv run python -m benchmark.generate_fixtures

# 4. Run the new tests
python -m benchmark.runner --tag alteryx
```

The generator scans `fixtures/<category>/<testN>/` and creates a "here are files, recreate in Dataiku" scenario for each. If a `workflow_spec.md` or `script.py` exists, the prompt tells the agent to read it first. Otherwise it gets just the file list.

## Cross-Run Analysis

Results accumulate in `benchmark/reports/bench_*/summary.json`. The analysis CLI reads them all:

```bash
# Pass rate trends across recent runs
uv run python -m benchmark.cli trends --last 10

# Compare two specific runs
uv run python -m benchmark.cli compare bench_20260325_132113 bench_20260325_164125

# Score history for one test
uv run python -m benchmark.cli history fx_sales_pipeline --last 20

# Set a golden baseline (best run)
uv run python -m benchmark.cli set-baseline bench_20260325_164125

# Check regressions vs baseline
uv run python -m benchmark.cli regressions bench_20260331_091500

# Cost breakdown
uv run python -m benchmark.cli costs --last 5
```

### Baselines

`benchmark/baselines.json` stores per-test golden scores. After a run, the runner automatically compares against baselines and warns about regressions:

```
WARNING: 2 regression(s) vs baseline (bench_20260325_164125):
  t6_data_pipeline              0.85 -> 0.70 (-0.15)
  a5_knowledge_search           0.90 -> 0.78 (-0.12)
```

## Architecture

```
benchmark/
├── config.yaml                    # Agent models, cost rates, parallelism, timeout
├── baselines.json                 # Golden baseline scores (gitignored)
├── runner.py                      # Main orchestrator
├── cli.py                         # Cross-run analysis CLI (trends, compare, etc.)
├── cost.py                        # Cost estimation from token counts
├── compare.py                     # Regression detection helpers
├── generate_fixtures.py           # Auto-generate scenarios from fixture dirs
├── generator.py                   # Auto-generate tier 1 from CLAUDE.md
├── agents/
│   ├── base.py                    # Abstract agent + AgentResult + VerificationResult
│   ├── claude.py                  # Claude Code headless adapter (stream-json)
│   └── codex.py                   # Codex headless adapter (placeholder)
├── scenarios/
│   ├── schema.py                  # Pydantic models (Scenario, FixtureRef, Rubric, etc.)
│   ├── tier1_commands.yaml        # Tier 1: hand-written command tests
│   ├── tier1_generated.yaml       # Tier 1: auto-generated from CLAUDE.md
│   ├── tier2_flags.yaml           # Tier 2: flag correctness
│   ├── tier3_chaining.yaml        # Tier 3: command chaining
│   ├── tier4_skills.yaml          # Tier 4: skill routing
│   ├── tier5_agents.yaml          # Tier 5: agent delegation
│   ├── projects.yaml              # Tier 6: progressive project builds (p1-p6)
│   ├── tier6_e2e.yaml             # Tier 6: end-to-end workflows
│   ├── fixture_pipelines.yaml     # Tier 6: fixture-backed pipelines (sales, healthcare)
│   ├── tier7_errors.yaml          # Tier 7: error recovery
│   ├── advanced.yaml              # Tier 7-8: complex workflows (a1-a16)
│   ├── open_ended.yaml            # Tier 9: real-world prompts (o1-o10)
│   ├── migration_alteryx.yaml     # Tier 10: Alteryx workflow migration
│   ├── migration_excel.yaml       # Tier 10: Excel workbook migration
│   ├── migration_pandas.yaml      # Tier 10: pandas script migration
│   └── auto_fixtures.yaml         # Tier 10: auto-generated from fixture dirs
├── fixtures/                      # Pre-built test data (not agent-generated)
│   ├── catalog.yaml               # Fixture index with schemas
│   ├── sales/test1/               # Orders, customers, products
│   ├── alteryx/test1/             # Customer segmentation workflow
│   ├── excel/test1/               # Quarterly financial report
│   ├── pandas/test1/              # ETL pipeline script
│   └── healthcare/test1/          # Encounters, diagnoses, treatments
├── store/                         # Cross-run analysis (reads summary.json files)
│   ├── reader.py                  # Scan and load reports/bench_*/summary.json
│   ├── query.py                   # Trends, history, compare, regressions
│   └── baselines.py               # Load/set golden baselines
├── analyzer/
│   ├── trace_parser.py            # Parse JSONL from Claude headless output
│   ├── scorer.py                  # Score against rubrics (7 dimensions)
│   ├── reporter.py                # narrative.md + summary.json + terminal
│   └── recommender.py             # Actionable skill/doc patches
└── reports/                       # Output dir (gitignored)
    └── {run_id}/
        ├── summary.json           # Per-test scores, costs, commands, metrics
        ├── narrative.md           # Rich narrative per test with agent output
        ├── recommendations.md     # Failure patterns + suggested fixes
        └── traces/                # Raw JSONL traces per test
```

## How It Works

1. **Pre-flight** — verifies DSS connectivity via `dku whoami`
2. **Fixture injection** — copies fixture files to per-test `/tmp/bench_fixtures/{test_id}/` directories (thread-safe)
3. **Project creation** — creates `BENCH_*` projects for tests that need them
4. **Headless execution** — runs Claude via `claude -p --output-format stream-json` with a prompt that tells the agent to read `skills/dku-cli/SKILL.md` first
5. **Trace parsing** — extracts bash commands, skill invocations, agent spawns, file reads/writes from JSONL
6. **DSS verification** — runs `dku` commands post-test to verify actual DSS state (row counts, column names, recipe types)
7. **Scoring** — weighted rubric across 7 dimensions (see below)
8. **Regression check** — compares scores against `baselines.json`, warns about regressions
9. **Reporting** — narrative.md, summary.json (with cost + git SHA), recommendations.md
10. **Cleanup** — removes temporary fixture files

## Scoring

Each test has a rubric with weighted dimensions. Only dimensions with non-None weight are included in the aggregate — prevents phantom dimensions from distorting scores.

| Dimension | What It Measures | Default Weight |
|-----------|-----------------|----------------|
| `command_correct` | Did the agent use the expected `dku` commands? (regex on trace) | 1.0 |
| `flags_correct` | Were the right flags used? (`-o json`, `--type`, etc.) | 1.0 |
| `outcome_verified` | Does DSS state match expectations? (real verification: exit code, row count, columns, recipe types) | 1.0 |
| `efficiency` | Output tokens + bash call count. Fewer = better. | 0.5 |
| `chaining` | Were related commands `&&`-chained? | 1.0 |
| `skill_routing` | Did Claude invoke the right skill? | 1.0 |
| `visual_recipe_ratio` | Ratio of visual recipes vs code recipes created | opt-in |
| `no_forbidden` | Were forbidden commands avoided? | opt-in |
| `agent_delegation` | Did Claude spawn the right subagent? | opt-in |
| `text_content` | Expected text in agent output? | opt-in |

### Verification features

- `expect_status` — exit code check (default: 0)
- `expect_contains` — substring match on stdout
- `expect_min_rows` — minimum row count in JSON array output
- `expect_columns` — column names that must exist in JSON output
- `no_python_recipes` — fail if any python/r/shell recipe types found in project

**Pass threshold: 0.70** (configurable in config.yaml)

## Reports

Each run writes to `benchmark/reports/{run_id}/`:

| File | Contents |
|------|----------|
| `summary.json` | Per-test scores, costs, tokens, duration, git SHA, timestamp |
| `narrative.md` | Rich report: task, commands, score breakdown, agent output, CLI/skill insights |
| `recommendations.md` | Clustered failure patterns with suggested fixes |
| `traces/` | Raw JSONL trace per test |

The `summary.json` includes enriched metadata for cross-run analysis:

```json
{
  "run_id": "bench_20260331_091500",
  "timestamp": "2026-03-31T09:15:00",
  "agent": "claude",
  "agent_model": "opus",
  "git_sha": "d195273",
  "estimated_cost_usd": 22.40,
  "total_input_tokens": 1500000,
  "total_output_tokens": 250000,
  "pass_rate": 0.823,
  "tests": [...]
}
```

## Cost Estimates

| Scope | Claude (Opus) |
|-------|--------------|
| Single tier 1 test | ~$0.05 |
| Single tier 6/9 test | ~$0.15-0.30 |
| Smoke tests (7 tests) | ~$0.50-1.00 |
| All tier 9 (10 tests) | ~$2-3 |
| All tier 10 migrations (8 tests) | ~$3-5 |
| Full suite (206 tests) | ~$20-30 |

Cost rates are configured per-agent in `config.yaml` (`cost_per_1k_input`, `cost_per_1k_output`).

## After a Run: Reading Results

1. **Terminal output** shows pass/fail + score for each test
2. **`narrative.md`** — open this first. It shows what the agent did, what it got wrong, and the agent's own meta-feedback (what was confusing, what commands failed)
3. **`recommendations.md`** — clustered failure patterns ranked by frequency. The top item is your highest-impact fix
4. **`summary.json`** — structured data for cross-run analysis. Feed to `uv run python -m benchmark.cli trends`

**The improvement loop:**
```
Run benchmark → Read narrative.md → Identify gap →
  CLI bug?       → Fix in src/dku_cli/commands/*.py + add prescriptive error message
  Skill gap?     → Fix in skills/dku-cli/SKILL.md (cheat sheet or gotchas table)
  Missing feature → Add CLI command or visual recipe support
→ Re-run benchmark → Compare with `uv run python -m benchmark.cli compare OLD NEW`
```

## Writing Scenarios

Scenarios are YAML files in `benchmark/scenarios/`. Each file has a `tests:` list:

```yaml
tests:
  - id: my_test_name              # Unique ID
    tier: 6                        # 1-10 (see tier table above)
    category: pipeline             # Grouping for reports
    tags: ["smoke", "fixture"]     # For --tag filtering (optional)
    prompt: |                      # What the agent sees
      Build a pipeline in project {project} that joins
      orders with customers and groups by region.
      Data files are at {fixture_dir}/orders.csv.
    needs_project: true            # Runner pre-creates a BENCH_* project
    timeout: 300                   # Seconds (default: 300)
    fixtures:                      # Optional: inject fixture files
      - path: sales/test1
        files: [orders.csv, customers.csv]
        inject_as: filesystem
    expect:
      commands:                    # Expected dku commands (regex patterns)
        - pattern: "dku recipe create-join"
          required: true
        - pattern: "dku recipe create-group"
          required: true
      no_python_recipes: true      # Fail if Python recipes found in project
      verify:                      # Post-test DSS state checks
        - command: "dku recipe list -P {project} -o json"
          expect_status: 0
          expect_min_rows: 2       # At least 2 recipes
    rubric:                        # Scoring weights (omit = not scored)
      command_correct: 1.0
      outcome_verified: 1.0
      efficiency: 0.3
      visual_recipe_ratio: 1.0    # Penalize Python recipe usage
```

**Placeholders** resolved at runtime: `{project}` → `BENCH_XXXXXX_...`, `{fixture_dir}` → `/tmp/bench_fixtures/{test_id}/`.

## Auto-Generating Tests

### From CLAUDE.md command table (tier 1)

```bash
uv run python -m benchmark.generator
# Outputs: benchmark/scenarios/tier1_generated.yaml (130 scenarios)
```

### From fixture directories (tier 10)

```bash
uv run python -m benchmark.generate_fixtures
# Scans fixtures/<category>/<testN>/, generates auto_fixtures.yaml
```

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
