# dku-cli Agent Benchmark

Evaluates AI agents on real Dataiku DSS tasks. Grading is binary outcome-only: all critical DSS state checks must pass.

## Prerequisites

- **`dku` CLI** — installed and authenticated (`dku whoami` succeeds)
- **Dataiku DSS instance** — API access, projects created/deleted freely
- **Docker** — agents run inside the `bench-agents` sandbox container; MCP profiles also use a `bench-mcp` HTTP sidecar container
- **Agent API keys** — set `ANTHROPIC_API_KEY` for Claude profiles, `OPENAI_API_KEY` for Codex profiles
- **`dataiku-agent-dev-kit`** — skills bind-mounted at run, MCP server source baked into the `bench-mcp` sidecar image

### .env file

```bash
cp benchmark/.env.example benchmark/.env
```

```ini
# benchmark/.env (gitignored — never commit real credentials)

DKU_URL=https://your-dss-instance.example.com
DKU_API_KEY=your-dss-api-key
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
```

### Agent Dev Kit path

The benchmark pulls from [`dataiku-agent-dev-kit`](https://github.com/dataiku/dataiku-agent-dev-kit) in two ways:

| Variable | Read by | When | What it feeds |
|---|---|---|---|
| `AGENT_DEV_KIT_SRC` | `docker/build.sh` (shell env) | image **build** | the MCP server source baked into the `bench-mcp` sidecar image |
| `AGENT_DEV_KIT_PATH` | `benchmark/.env` → runner | every **run** | the skills bind-mounted per profile |

Both default to a sibling clone of `dataiku-cli`:

```bash
# Only if the repo is NOT a sibling of dataiku-cli:
export AGENT_DEV_KIT_SRC=/path/to/dataiku-agent-dev-kit   # for build.sh
# and set AGENT_DEV_KIT_PATH=/path/to/dataiku-agent-dev-kit in benchmark/.env
```

## Quick Start

```bash
# 1. Install benchmark dependencies
uv sync --group benchmark

# 2. Configure credentials
cp benchmark/.env.example benchmark/.env
# Edit benchmark/.env with your DSS URL, API key, and agent keys

# 3. Build the sandbox images (needs Docker, ~2-3 min first build).
#    Builds both bench-agents (agent runtime) and bench-mcp (MCP sidecar).
benchmark/docker/build.sh

# 4. Verify connectivity
dku whoami

# 5. List available profiles and scenarios
uv run python -m benchmark.runner --list

# 6. Run one easy scenario (~30-90s)
uv run python -m benchmark.runner --profile claude_dku_skills --scenario filter_and_sort --parallel 1 --verbose

# 7. Run default profiles on all scenarios
uv run python -m benchmark.runner

# 8. Generate trend dashboard
uv run python -m benchmark.dashboard
```

### Common variations

```bash
# Filter by profile/domain/difficulty
uv run python -m benchmark.runner --profile claude_dku_skills --domain data_prep --difficulty easy

# Override model at runtime
uv run python -m benchmark.runner --profile claude_dku_skills --model claude-sonnet-4-6

# Compare profiles
uv run python -m benchmark.runner --profile claude_vanilla,claude_dku_skills --domain data_prep

# Repeat for statistical stability
uv run python -m benchmark.runner --profile claude_dku_skills --scenario filter_and_sort --repeat 5

# Validate solutions against live DSS
uv run python -m benchmark.runner --domain data_prep --validate

# Keep DSS projects after run for inspection
uv run python -m benchmark.runner --scenario filter_and_sort --no-cleanup

# Dry-run to see what would execute
uv run python -m benchmark.runner --dry-run
```

### Keeping things up to date

The three artifacts under test refresh differently:

| Artifact | Source | To get latest |
|---|---|---|
| **`dku` CLI** | baked into the `bench-agents` image from `dku-cli` HEAD | `git pull` in `dataiku-cli` **+ rebuild** |
| **MCP server** | baked into the `bench-mcp` sidecar image from `dataiku-agent-dev-kit/dataiku_mcp` | `git pull` in `dataiku-agent-dev-kit` **+ rebuild** |
| **Skills** | bind-mounted from the host at run time | `git pull` in `dataiku-agent-dev-kit` (no rebuild) |
| **claude / codex CLIs** | `npm i -g` at build (layer-cached) | rebuild with `--no-cache` |

One-command refresh:

```bash
benchmark/docker/build.sh --pull            # latest dku + MCP
benchmark/docker/build.sh --pull --no-cache # also refresh the agent CLIs
```

The runner's preflight prints a **Freshness** line and warns when the running image was built from older commits than your host checkouts. Provenance (baked SHAs) is recorded in every report.

All runner CLI flags are documented in the [CLI Reference](docs/cli-reference.md).

## Example Output

### `--list`

```
  Profiles:
    claude_dku_skills    model=claude-sonnet-4-6 (default)

  Scenarios (52):
    automation/
      dataset_trigger_scenario        medium  gap=none
      email_reporter                  medium  gap=none
      scenario_with_recipe_run        medium  gap=none
      time_trigger_scenario           easy    gap=none
    cross_project/
      foreign_dataset_flow            medium  gap=none
    dashboard/
      chart_insight                   medium  gap=none
      interactive_chart               medium  gap=none
      multi_chart_dashboard           medium  gap=none
      multi_tile_dashboard            medium  gap=none
    ...
```

### Single scenario run

```
  Benchmark: bench_20260529_095529
  ==================================================
  Profiles: codex_dku_skills
  Mode: outcome
  Scenarios: 1
  Total runs: 1 (1 tests x 1 agents)

  Preflight: checking DSS connectivity...
  Connected: Connected to DSS instance 'my-instance'

  Running 1 tests (parallel=1)...

    [  1/1] PASS codex_dku_skills filter_and_sort              opt=100% 34251ms $0.832 [coherent]

  Generating reports...

  Done. Reports at: benchmark/reports/bench_20260529_095529/
```

### Compare output

```
                    Pass / Fail Matrix
 ┌────────────────────┬──────────┬──────┬──────────────────┬──────────┐
 │ Scenario           │ Domain   │ Diff │ codex_dku_skills │ Overall  │
 ├────────────────────┼──────────┼──────┼──────────────────┼──────────┤
 │ filter_and_sort    │ data_prep│ easy │ PASS             │ 1/1      │
 │ upload_and_aggreg. │ data_prep│ easy │ FAIL             │ 0/1      │
 ├────────────────────┼──────────┼──────┼──────────────────┼──────────┤
 │ TOTAL              │          │      │ 1/2  (50%)       │ 1/2 (50%)│
 └────────────────────┴──────────┴──────┴──────────────────┴──────────┘

                    Profile Stats
 ┌──────────────────┬──────┬───────────┬─────────┬─────────────┐
 │ Profile          │ Runs │ Pass Rate │ Avg Time│ Total Cost  │
 ├──────────────────┼──────┼───────────┼─────────┼─────────────┤
 │ codex_dku_skills │ 2    │ 50% (1/2) │ 94s     │ $1.664      │
 └──────────────────┴──────┴───────────┴─────────┴─────────────┘
```

### Coherence tag

Every result line includes a coherence tag:

- **`coherent`** — agent used only the tool surface its profile was granted
- **`INCOHERENT: vanilla used the dku CLI`** — agent reached for a surface it shouldn't have (see [Sandbox & coherence](#sandbox--coherence))

## Profiles

Defined in `config.yaml`. The `runner.profiles` key sets the default(s). Each profile is one `claude_*` / `codex_*` pair sharing a tool-surface preset (YAML anchors), differing only in `vendor` and `model`.

| Profile | DSS surface | Skills |
|---------|-------------|--------|
| `*_vanilla` | raw `dataikuapi` + DSS creds only (no dku CLI) | none |
| `*_dku` | the `dku` CLI | none |
| `*_dku_skills` | the `dku` CLI | `dku-cli`, `dataiku` |
| `*_mcp` | the dataiku MCP server only (no dku, no raw API) | none |
| `*_mcp_skills` | the dataiku MCP server | auto-discovered from the agent-dev-kit |

Full per-profile config keys are in the [CLI Reference](docs/cli-reference.md#profile-config-keys).

## Sandbox & coherence

Every agent run executes inside the `bench-agents` Docker image (build it with `benchmark/docker/build.sh`). The container is the isolation boundary; the host prepares config and parses the agent CLI's stdout.

The agent image ships **runtime only**: the `claude`/`codex` CLIs, the `dku` CLI (installed as a uv tool, its source deleted), and `dataiku-api-client` for the vanilla baseline. It contains **no** repo, scenarios, `solution.md`, `.env`, skills, or the MCP server source. Per run, the host bind-mounts the fixture dir at `/work` and a config dir, and **copies in only the skills the profile grants** — so a no-skills profile literally has no skills on disk.

The MCP server runs **out-of-process in a separate `bench-mcp` sidecar container** over streamable-HTTP, not as a child of the agent. The runner starts one shared sidecar per run on a per-run docker network (alias `bench-mcp`), hands it the DSS creds, and gives MCP-profile agents only the network + a URL (`http://bench-mcp:8000/mcp`). This is what keeps the MCP comparison realistic and fair: the agent has **no MCP source on disk to read** and **no DSS creds in any file or env it can reach** — it must use the tools blind, as in a real deployment.

This makes cross-profile comparison fair by construction:

- `vanilla` gets DSS creds in its env and uses `dataikuapi`; the `dku` CLI is off `PATH`.
- `dku` / `dku_skills` get creds + the `dku` CLI; granted skills are copied in.
- `mcp` / `mcp_skills` get **no** agent-side DSS creds and **no** MCP source; the `dku` CLI is off `PATH`, so the only DSS surface is the sidecar URL over HTTP.

`benchmark/analyzer/coherence.py` is the trace-level sanity net on top of this: it flags any run whose bash/MCP trace reached for a surface its profile was not granted (raw `DSSClient` in a dku/mcp profile, the `dku` CLI in an mcp profile, or any read of `/opt/bench`, `.env`, `solution.md`, or its own `/cfg` config). The runner prints a `coherent` / `INCOHERENT: …` tag per result and records `coherence_issues` in each trace.

Coherence issues are recorded per-trace in `reports/<run_id>/traces/`. They do not directly cause a FAIL — the profile stats table separately shows pass rates for coherent vs incoherent runs when you compare.

Troubleshooting guide: [Troubleshooting Reference](docs/troubleshooting.md).

## Scenarios

Each scenario is a directory:

```
benchmark/scenarios/<domain>/<id>/
  task.yaml     — fixtures, setup, prompt, critical/optional checks
  solution.md   — maintainer-only executable witness used by --validate
```

**52 scenarios** across 11 domains.

## Scenario Contract

Each scenario has three distinct layers:

- `task.yaml` `prompt` defines the full benchmark intent. This is the task shown to the agent.
- `task.yaml` `checks` define the enforced success contract. These are the machine-checked outcomes used for scoring.
- `solution.md` is a maintainer artifact used only by `--validate`. It proves that at least one executable path exists today, but it is not part of the benchmark semantics and does not define how agents are expected to solve the task.

This matters for agent-agnostic benchmarks:

- Agents are scored against `checks`, not against `solution.md`.
- `solution.md` may use any valid path that satisfies the current checks.
- A scenario can be broader in intent than what the current harness can fully prove.

When the harness cannot yet prove the full intent, record that explicitly in `task.yaml` with `validation_gaps`. In that case:

- the prompt should stay capability-first
- the checks should remain honest about what is enforced today
- `solution.md` should document the executable baseline and the missing proof

## task.yaml Format

```yaml
id: upload_and_aggregate
domain: data_prep
difficulty: easy          # easy | medium | hard
expected_gap: none        # none | tool_gap | capability_gap
fixtures:
  - world/orders          # copied from benchmark/fixtures/ to /tmp/bench_fixtures/
setup:
  - "dku dataset create orders --type UploadedFiles -P {project}"
initial_checks:
  - run: "dku dataset schema revenue_by_region -P {project}"
    assert: exit_code_nonzero   # must fail before agent runs
prompt: |
  Natural-language task shown to the agent.
validation_gaps:
  - Optional list for cases where current checks only prove part of the intended capability.
checks:
  critical:
    - run: "dku dataset head revenue_by_region -P {project} -n 10 -o json"
      assert: min_rows
      min: 4
  optional:
    - run: "dku recipe list -P {project} -o json"
      assert: no_python_recipes
```

Placeholders: `{project}` → `BENCH_*` key, `{fixture_dir}` → path to the per-test fixture directory.

## Assertions

| Type | Checks |
|------|--------|
| `exit_code_zero` / `exit_code_nonzero` | Command exit code |
| `has_columns` | Named columns exist in schema |
| `min_rows` | Row count ≥ min |
| `column_is_numeric` | Column type is numeric |
| `output_contains` | stdout contains string |
| `no_python_recipes` | No Python/R/shell recipes in project |
| `output_schema` | Dataset schema matches `expected_outputs` (DSS client) |
| `output_rows` | Row count + sample data match `expected_outputs` (DSS client) |
| `flow_shape` | Flow nodes/recipes match `expected_flow` (DSS client) |

## Scoring

- **Pass** — all critical checks pass
- **optional_score** — fraction of optional checks that pass (quality signal, doesn't affect pass/fail)
- **gap_type** — `tool_gap` or `capability_gap` flags known limitations so they don't skew overall results

Passing a scenario means the enforced checks passed. It does not automatically mean the harness proved every aspect of the natural-language prompt. For partially validated scenarios, `validation_gaps` is the source of truth for what remains unproven.

## Reports

Each run writes to `benchmark/reports/{run_id}/`:

| File | Contents |
|------|----------|
| `summary.json` | Per-test results, costs, tokens, duration, git SHA |
| `traces/` | Per-test debug JSON: agent output excerpts, bash commands, MCP/skill calls, `coherence_issues`, and errors |

### Trend dashboard

```bash
uv run python -m benchmark.dashboard
```

Reads all reports and generates `benchmark/reports/_dashboard.html` with:

- **Pass rate over time** — overall and per-profile line chart
- **Cost per run** — bar chart tracking API spend across runs
- **Latest breakdown** — pass rate by domain and difficulty
- **Run history table** — every run with date, SHA, pass rate, cost

The dashboard opens in your browser automatically (pass `--no-open` to suppress). Charts render inline via Chart.js.

## Comparing Runs

```bash
# Latest run per profile (default) — picks the newest report dir for each profile
uv run python -m benchmark.compare

# All report dirs — no per-profile filtering
uv run python -m benchmark.compare --all

# Explicit A/B comparison — always shows regression/improvement summary
uv run python -m benchmark.compare --baseline bench_20260527_165642 --candidate bench_20260528_095949

# Compare two specific runs (positional args)
uv run python -m benchmark.compare bench_20260527_165642 bench_20260528_095949

# Filter by profile or domain
uv run python -m benchmark.compare --profile claude_dku_skills,codex_dku_skills
uv run python -m benchmark.compare --profile claude_dku_skills --domain data_prep

# Profile stats only — skip the per-scenario matrix
uv run python -m benchmark.compare --profiles-only

# Export to file (json, csv, or markdown)
uv run python -m benchmark.compare --export json
uv run python -m benchmark.compare --export csv
uv run python -m benchmark.compare --export md
# Exports land in benchmark/reports/_compare_<timestamp>.<ext>
```

### Default selection logic

With no arguments, `compare` loads all report dirs but keeps only the **newest run per unique profile**. This prevents stale runs from diluting the view. Pass `--all` to load every dir regardless.

### Output

The compare command prints up to two tables:

- **Pass / Fail Matrix** — rows are scenarios, columns are profiles; cells show `PASS`/`FAIL` (or `N/M` when multiple runs are aggregated)
- **Profile Stats** — per-profile aggregates: run count, pass rate, avg time, avg commands, avg token usage, total cost

### Regression section

When exactly two run dirs are loaded (via `--baseline`/`--candidate`, positional args, or as a side effect of per-profile dedup), a regression section is appended listing newly-passing, regressed, and still-failing profile/scenario pairs.

### Export

`--export json` dumps the full matrix, per-run breakdowns, and per-cell records to a JSON file. `--export csv` writes every test result as a row. `--export md` generates a standalone markdown report including the matrix and profile stats tables.

## Writing a Scenario

1. Create `benchmark/scenarios/<domain>/<id>/task.yaml` + `solution.md`
2. Write the prompt for the real intended DSS capability, not the narrowest path the current CLI can express
3. Define `checks` as the machine-checked outcomes the harness can honestly enforce today
4. If checks do not prove the full prompt intent, add explicit `validation_gaps`
5. Use `solution.md` as a maintainer-side executable witness for `--validate`, not as the canonical agent workflow
6. Run `--validate --domain <domain>` to confirm the witness path satisfies the current checks on live DSS

Scenario authoring policy lives in [benchmark/CLAUDE.md](CLAUDE.md).

## Reference documents

- [Architecture](docs/architecture.md) — directory layout, runner lifecycle, container isolation model
- [CLI Reference](docs/cli-reference.md) — runner flags and profile config keys
- [Troubleshooting](docs/troubleshooting.md) — common issues and coherence table
- [Authoring Guide](CLAUDE.md) — scenario contract, prompt rubric, editing checklist
