#!/usr/bin/env python3
"""Benchmark runner — orchestrates agent tests against a real Dataiku DSS sandbox.

Usage:
    python -m benchmark.runner                           # Full suite, both agents
    python -m benchmark.runner --agent claude             # Claude only
    python -m benchmark.runner --tier 1                   # Tier 1 only
    python -m benchmark.runner --test t1_project_list     # Single test
    python -m benchmark.runner --agent claude --tier 1,2  # Claude, tiers 1+2
    python -m benchmark.runner --parallel 8               # 8 concurrent runs
    python -m benchmark.runner --dry-run                  # Show what would run
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import yaml

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from benchmark.agents.base import BaseAgent, VerificationCheck, VerificationResult  # noqa: E402
from benchmark.agents.claude import ClaudeAgent  # noqa: E402
from benchmark.agents.codex import CodexAgent  # noqa: E402
from benchmark.analyzer.recommender import Recommender  # noqa: E402
from benchmark.analyzer.reporter import Reporter, TestResultRecord  # noqa: E402
from benchmark.analyzer.scorer import Scorer  # noqa: E402
from benchmark.analyzer.trace_parser import summarize_trace  # noqa: E402
from benchmark.scenarios.schema import Scenario, load_scenarios  # noqa: E402


AGENT_CLASSES: dict[str, type[BaseAgent]] = {
    "claude": ClaudeAgent,
    "codex": CodexAgent,
}

# System prompt injected into every test run.
# Includes compact CLI reference so both Claude and Codex know the commands.
SYSTEM_CONTEXT = """You have access to a Dataiku DSS instance via the `dku` CLI.
The CLI is already authenticated — you can run dku commands directly.
Be efficient: chain related dku commands with && in a single shell call.
Use -o json when you need structured output for further processing.

## dku CLI Reference (kubectl-style: dku <noun> <verb>)

Command groups and their verbs:
- auth: login, logout, status, list, switch
- config: set, get, list, path, variables, set-variables
- project: list, get, export, create, delete, duplicate, set-metadata, variables, set-variables, permissions, set-permissions, tags
- dataset: list, schema, head, build, create, upload, delete, clear, get-definition, set-definition, set-schema
- recipe: list, get, run, create, delete, set-code, get-code, set-definition, add-input, add-output, check-schema, apply-schema, create-join, create-group, create-stack, create-distinct, create-sort, create-filter, create-window, create-split, create-topn, create-embed, create-embed-docs, create-extract, create-llm-eval, create-agent-eval
- scenario: list, run, abort, status, create, delete, get-definition, set-definition
- job: list, run, status, log, abort, wait
- plugin: list, push, settings
- code-env: list, get, create, delete, update
- connection: list, create, test
- model: list, get, versions
- folder: list, ls, upload, download
- llm: list, completion, embeddings
- webapp: list, start, stop, status
- macro: list, run
- user: list, create
- flow: graph, zones, create-zone, propagate, check, sources, successors
- library: list, read, write, delete, mkdir
- agent: list, create, get, delete, wake-up, shutdown, status, add-tool, set-llm
- agent-tool: list, get, run, delete
- knowledge: list, create, get, build, search, delete
- bundle: list, export, download, import, activate
- api-service: list, create, get, create-package, list-packages
- wiki: list, create, get, update, delete
- sql: query
- (root): whoami

## Recipe Type Selection (IMPORTANT — prefer visual recipes over Python)

ALWAYS use visual recipes when possible. Python/SQL are last resort.

| Task | Recipe command | NOT Python |
|------|--------------|------------|
| Join datasets | `dku recipe create-join NAME -i ds1 -i ds2 --output-ds out` | NOT `pd.merge()` |
| Aggregate/group by | `dku recipe create-group NAME -i ds --output-ds out -k col` | NOT `df.groupby()` |
| Stack/union | `dku recipe create-stack NAME -i ds1 -i ds2 --output-ds out` | NOT `pd.concat()` |
| Deduplicate | `dku recipe create-distinct NAME -i ds --output-ds out` | NOT `df.drop_duplicates()` |
| Sort | `dku recipe create-sort NAME -i ds --output-ds out` | NOT `df.sort_values()` |
| Filter rows | `dku recipe create-filter NAME -i ds --output-ds out` | NOT `df[df.x > y]` |
| Window functions | `dku recipe create-window NAME -i ds --output-ds out` | NOT `df.groupby().transform()` |
| Top N rows | `dku recipe create-topn NAME -i ds --output-ds out` | NOT `df.nlargest()` |
| Split by condition | `dku recipe create-split NAME -i ds --output-ds out` | NOT manual filtering |
| Custom logic only | `dku recipe create NAME -t python -i ds --output-ds out` | Only when no visual recipe fits |

Common flags: --project/-P PROJECT_KEY, --output/-o json|csv|table, --quiet, --yes
Datasets: use --type UploadedFiles for datasets you'll upload to. Default Filesystem is for recipe outputs.
Embedding models: `dku llm list --purpose TEXT_EMBEDDING_EXTRACTION` (default only shows completion models).

## Visual Recipe Flags (key options for common recipes)

| Recipe | Key flags |
|--------|-----------|
| create-group | `-k col` (repeatable for multi-column), `--agg 'col:sum,avg'` |
| create-topn | `--n 10`, `--rank-by col:desc` (repeatable), `-k partition_col` |
| create-window | `-k partition_col`, `--order-key col:desc`, `--compute 'TYPE:col:output'` |
| create-pivot | `--row-key col` (repeatable), `--column-key col`, `--value-column col`, `--agg-type SUM` |
| create-sampling | `--method RANDOM_FIXED_NB`, `--size 1000`, `--ratio 0.1` |
| create-join | `-i ds1 -i ds2`, `--join-key col`, `--join-type LEFT/INNER/CROSS` |
| set-definition | `--definition JSON` (recipe-level) or `--payload JSON` (visual recipe config) |

Window --compute types: rowNumber, rank, denseRank, lag, lead, sum, avg, min, max, count, first, last.
Format: `--compute 'TYPE:source_col:output_col'` or `--compute 'rowNumber::rn'` (no source for rank types).

## After completing the task: META-FEEDBACK (REQUIRED)

After you finish the task (whether you succeeded or failed), output a structured feedback section.
This helps us improve the CLI and skill documentation. Use this EXACT format:

```
META-FEEDBACK:
skill_helpful: [yes/no/partial] — Did the CLI reference above help you pick the right commands?
commands_worked: [list of dku commands that worked as expected]
commands_failed: [list of dku commands that failed or had unexpected behavior, with brief error description]
commands_missing: [operations you wanted to do but couldn't find a dku command for]
confusing: [anything that was unclear, misleading, or took multiple attempts to figure out]
python_fallback: [yes/no] — Did you fall back to Python when a visual recipe should have worked? If yes, why?
help_text_gaps: [any --help output that was insufficient or misleading]
suggestion: [one specific improvement that would have saved you the most time]
END-META-FEEDBACK
```
"""


def load_config(config_path: Path | None = None) -> dict:
    """Load benchmark configuration."""
    path = config_path or Path(__file__).parent / "config.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


def preflight_check():
    """Verify DSS connectivity before running benchmarks."""
    print("  Preflight: checking DSS connectivity...")
    try:
        result = subprocess.run(
            ["dku", "whoami"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            print(f"  ERROR: dku whoami failed: {result.stderr}")
            sys.exit(1)
        print(f"  Connected: {result.stdout.strip()[:100]}")
    except FileNotFoundError:
        print("  ERROR: dku CLI not found. Install with: pip install dku-cli")
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print("  ERROR: dku whoami timed out. Check DSS connectivity.")
        sys.exit(1)


def create_project(project_key: str, name: str) -> bool:
    """Create a DSS project for a test. Returns True if successful."""
    result = subprocess.run(
        ["dku", "project", "create", project_key, "--name", name],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        # Project may already exist — that's fine
        if (
            "already exists" in result.stderr.lower()
            or "already exists" in result.stdout.lower()
        ):
            return True
        print(f"  Warning: failed to create project {project_key}: {result.stderr}")
        return False
    return True


def resolve_prompt(test: Scenario, run_id: str) -> str:
    """Resolve placeholders in the test prompt."""
    prompt = test.prompt
    if test.project_key:
        prompt = prompt.replace("{project}", test.project_key)
    # Prepend system context
    return f"{SYSTEM_CONTEXT}\n\nTask: {prompt}"


def run_single_test(
    agent: BaseAgent,
    test: Scenario,
    config: dict,
    run_id: str,
) -> TestResultRecord:
    """Run a single test with one agent."""
    prompt = resolve_prompt(test, run_id)
    cwd = str(PROJECT_ROOT)
    timeout = test.timeout or config["runner"].get("timeout", 180)

    start = time.monotonic()
    agent_result = agent.run(prompt, cwd, timeout=timeout)
    wall_ms = int((time.monotonic() - start) * 1000)

    # If duration wasn't set by the agent parser, use wall time
    if not agent_result.duration_ms:
        agent_result.duration_ms = wall_ms

    # Run verification steps against real DSS
    verification = run_verification(test) if test.expect.verify else None

    # Score
    scorer = Scorer(pass_threshold=config["scoring"].get("pass_threshold", 0.7))
    score = scorer.score(test, agent_result, verification)

    trace_summary = summarize_trace(agent_result)

    return TestResultRecord(
        test_id=test.id,
        tier=test.tier,
        category=test.category,
        prompt=test.prompt,
        agent=agent.name,
        score=score,
        trace_summary=trace_summary,
        agent_result=agent_result,
    )


def run_verification(test: Scenario) -> VerificationResult:
    """Run verification commands against real DSS."""
    checks = []
    for step in test.expect.verify:
        cmd = step.command
        if test.project_key:
            cmd = cmd.replace("{project}", test.project_key)

        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            passed = result.returncode == (step.expect_status or 0)

            if passed and step.expect_contains:
                passed = step.expect_contains in result.stdout

            checks.append(
                VerificationCheck(
                    command=cmd,
                    passed=passed,
                    output=result.stdout[:500],
                    error=result.stderr[:500] if not passed else "",
                )
            )
        except subprocess.TimeoutExpired:
            checks.append(
                VerificationCheck(
                    command=cmd,
                    passed=False,
                    error="Verification timed out",
                )
            )

    return VerificationResult(checks=checks)


def main():
    parser = argparse.ArgumentParser(description="dku-cli Benchmark Runner")
    parser.add_argument(
        "--agent", type=str, help="Agent to test (claude, codex, or comma-separated)"
    )
    parser.add_argument("--tier", type=str, help="Tier(s) to run (e.g., 1 or 1,2,3)")
    parser.add_argument("--test", type=str, help="Single test ID to run")
    parser.add_argument(
        "--parallel", type=int, default=None, help="Max parallel workers"
    )
    parser.add_argument("--config", type=str, default=None, help="Config file path")
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would run without executing"
    )
    parser.add_argument(
        "--skip-preflight", action="store_true", help="Skip DSS connectivity check"
    )
    args = parser.parse_args()

    config = load_config(Path(args.config) if args.config else None)
    run_id = f"bench_{datetime.now():%Y%m%d_%H%M%S}"

    print(f"\n  Benchmark: {run_id}")
    print(f"  {'=' * 50}")

    # Determine which agents to run
    agent_names = args.agent.split(",") if args.agent else config["runner"]["agents"]
    agents = [AGENT_CLASSES[name](config) for name in agent_names]
    print(f"  Agents: {', '.join(a.name for a in agents)}")

    # Load and filter scenarios
    scenario_dir = Path(__file__).parent / "scenarios"
    all_scenarios = load_scenarios(scenario_dir)

    if args.test:
        scenarios = [s for s in all_scenarios if s.id == args.test]
        if not scenarios:
            print(f"  ERROR: test '{args.test}' not found")
            sys.exit(1)
    elif args.tier:
        tiers = {int(t) for t in args.tier.split(",")}
        scenarios = [s for s in all_scenarios if s.tier in tiers]
    else:
        scenarios = all_scenarios

    print(f"  Scenarios: {len(scenarios)} tests")
    total_runs = len(scenarios) * len(agents)
    print(f"  Total runs: {total_runs} ({len(scenarios)} tests x {len(agents)} agents)")

    if args.dry_run:
        print("\n  Dry run — tests that would execute:")
        for s in scenarios:
            for a in agents:
                print(
                    f"    [{a.name:6s}] {s.id:25s} (tier {s.tier}, project={'yes' if s.needs_project else 'no'})"
                )
        return

    # Preflight
    if not args.skip_preflight:
        preflight_check()

    # Pre-create projects for tests that need them
    run_suffix = run_id[-6:].upper()
    for test in scenarios:
        if test.needs_project:
            project_key = f"BENCH_{run_suffix}_{test.id.upper().replace('T', '').replace('_', '')}"
            # Truncate to DSS max project key length (usually 25 chars)
            project_key = project_key[:25]
            test.project_key = project_key
            print(f"  Creating project: {project_key}")
            create_project(project_key, f"Benchmark {test.id}")

    # Run tests
    parallel = args.parallel or config["runner"].get("parallel", 4)
    results: list[TestResultRecord] = []
    completed = 0

    print(f"\n  Running {total_runs} tests (parallel={parallel})...\n")

    with ThreadPoolExecutor(max_workers=parallel) as pool:
        futures = {}
        for agent in agents:
            for test in scenarios:
                future = pool.submit(run_single_test, agent, test, config, run_id)
                futures[future] = (agent.name, test.id)

        for future in as_completed(futures):
            agent_name, test_id = futures[future]
            try:
                record = future.result()
                results.append(record)
                completed += 1
                status = "PASS" if record.score.passed else "FAIL"
                score = record.score.overall
                duration = record.agent_result.duration_ms
                print(
                    f"  [{completed:3d}/{total_runs}] {status} {agent_name:6s} {test_id:25s} "
                    f"score={score:.2f} {duration}ms"
                )
            except Exception as e:
                completed += 1
                print(
                    f"  [{completed:3d}/{total_runs}] ERR  {agent_name:6s} {test_id:25s} {e}"
                )

    # Generate reports
    print("\n  Generating reports...")
    reporter = Reporter(run_id)
    reporter.generate(results)

    recommender = Recommender(run_id)
    recommender.generate(results)

    print(f"  Done. Reports at: benchmark/reports/{run_id}/")


if __name__ == "__main__":
    main()
