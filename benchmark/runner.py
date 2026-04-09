#!/usr/bin/env python3
"""Benchmark runner — orchestrates agent tests against a real Dataiku DSS sandbox.

Usage:
    python -m benchmark.runner                           # Full suite, both agents
    python -m benchmark.runner --agent claude             # Claude only
    python -m benchmark.runner --tier 1                   # Tier 1 only
    python -m benchmark.runner --test t1_project_list     # Single test
    python -m benchmark.runner --agent claude --tier 1,2  # Claude, tiers 1+2
    python -m benchmark.runner --parallel 8               # 8 concurrent runs
    python -m benchmark.runner --tag smoke                # Run smoke-tagged tests only
    python -m benchmark.runner --dry-run                  # Show what would run
"""

from __future__ import annotations

import argparse
import shutil
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
from benchmark.cost import estimate_cost_from_config  # noqa: E402
from benchmark.scenarios.schema import Scenario, load_scenarios  # noqa: E402


AGENT_CLASSES: dict[str, type[BaseAgent]] = {
    "claude": ClaudeAgent,
    "codex": CodexAgent,
}

FIXTURE_BASE = Path("/tmp/bench_fixtures")

# System prompt injected into every test run.
# Points the agent to the skill files — tests the real agent experience.
SYSTEM_CONTEXT = """You have access to a Dataiku DSS instance via the `dku` CLI.
The CLI is already authenticated — you can run dku commands directly.

## IMPORTANT: Read the skill docs FIRST

Before starting, read these skill files — they are your guide:
1. `skills/dku-cli/SKILL.md` — CLI commands, patterns, gotchas, and examples
2. `skills/dataiku/SKILL.md` — Platform knowledge (when to use visual recipes vs Python, etc.)

Use `--help` on any command you're unsure about: `dku <noun> <verb> --help`

## Key rules (read the skills for full details)
- Prefer visual recipes (join, group, sort, filter, window, etc.) over Python
- Use `--type UploadedFiles` for datasets you'll upload to
- Chain related commands with `&&` in a single shell call
- Use `-o json` when you need structured output for further processing
- Always verify your work with `dku dataset head`

## After completing the task: META-FEEDBACK (REQUIRED)

After you finish the task (whether you succeeded or failed), output a structured feedback section.
This helps us improve the CLI and skill documentation. Use this EXACT format:

```
META-FEEDBACK:
skill_helpful: [yes/no/partial] — Did the skill docs help you pick the right commands?
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


def get_fixture_target(test_id: str) -> Path:
    """Return a per-test fixture directory to avoid race conditions."""
    return FIXTURE_BASE / test_id


def inject_fixtures(test: Scenario, config: dict) -> Path:
    """Copy fixture files to a per-test temp dir for the agent to use.

    Returns the fixture target path for this test.
    """
    target = get_fixture_target(test.id)
    if not test.fixtures:
        return target
    fixture_base = Path(config["runner"].get("fixture_dir", "benchmark/fixtures"))
    target.mkdir(parents=True, exist_ok=True)
    for ref in test.fixtures:
        src_dir = fixture_base / ref.path
        if not src_dir.is_dir():
            print(f"  Warning: fixture dir not found: {src_dir}")
            continue
        # Determine which files to copy
        if ref.files:
            files = [src_dir / f for f in ref.files]
        else:
            files = [
                f
                for f in src_dir.iterdir()
                if f.is_file() and f.suffix in (".csv", ".xlsx", ".py", ".md", ".json")
            ]
        for f in files:
            if f.exists():
                shutil.copy2(f, target / f.name)
    return target


def cleanup_fixtures() -> None:
    """Remove all temporary fixture directories."""
    shutil.rmtree(FIXTURE_BASE, ignore_errors=True)


def resolve_prompt(
    test: Scenario, run_id: str, fixture_target: Path | None = None
) -> str:
    """Resolve placeholders in the test prompt."""
    prompt = test.prompt
    if test.project_key:
        prompt = prompt.replace("{project}", test.project_key)
    target = fixture_target or get_fixture_target(test.id)
    prompt = prompt.replace("{fixture_dir}", str(target))
    # Prepend system context
    return f"{SYSTEM_CONTEXT}\n\nTask: {prompt}"


def run_single_test(
    agent: BaseAgent,
    test: Scenario,
    config: dict,
    run_id: str,
) -> TestResultRecord:
    """Run a single test with one agent."""
    # Inject fixtures into a per-test directory (thread-safe)
    fixture_target = inject_fixtures(test, config)

    prompt = resolve_prompt(test, run_id, fixture_target)
    cwd = str(PROJECT_ROOT)
    timeout = test.timeout or config["runner"].get("timeout", 180)

    start = time.monotonic()
    agent_result = agent.run(prompt, cwd, timeout=timeout)
    wall_ms = int((time.monotonic() - start) * 1000)

    # If duration wasn't set by the agent parser, use wall time
    if not agent_result.duration_ms:
        agent_result.duration_ms = wall_ms

    # Compute cost estimate
    agent_config = config.get("agents", {}).get(agent.name, {})
    agent_result.cost_usd = estimate_cost_from_config(
        agent_result.input_tokens, agent_result.output_tokens, agent_config
    )

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
    import json as _json

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
            error_parts = []

            if passed and step.expect_contains:
                if step.expect_contains not in result.stdout:
                    passed = False
                    error_parts.append(
                        f"Expected '{step.expect_contains}' not found in output"
                    )

            # Row count check — parse JSON array output
            if passed and step.expect_min_rows is not None:
                try:
                    data = _json.loads(result.stdout)
                    rows = (
                        data
                        if isinstance(data, list)
                        else data.get("rows", data.get("data", []))
                    )
                    if len(rows) < step.expect_min_rows:
                        passed = False
                        error_parts.append(
                            f"Expected >= {step.expect_min_rows} rows, got {len(rows)}"
                        )
                except (_json.JSONDecodeError, TypeError):
                    passed = False
                    error_parts.append(
                        "Could not parse JSON output for row count check"
                    )

            # Column name check — parse JSON output for column names
            if passed and step.expect_columns:
                try:
                    data = _json.loads(result.stdout)
                    if isinstance(data, list) and data:
                        actual_cols = set(data[0].keys())
                    elif isinstance(data, dict) and "columns" in data:
                        actual_cols = {
                            c.get("name", c) if isinstance(c, dict) else c
                            for c in data["columns"]
                        }
                    else:
                        actual_cols = set()
                    missing = set(step.expect_columns) - actual_cols
                    if missing:
                        passed = False
                        error_parts.append(f"Missing columns: {sorted(missing)}")
                except (_json.JSONDecodeError, TypeError):
                    passed = False
                    error_parts.append("Could not parse JSON output for column check")

            checks.append(
                VerificationCheck(
                    command=cmd,
                    passed=passed,
                    output=result.stdout[:500],
                    error="; ".join(error_parts)
                    if error_parts
                    else (result.stderr[:500] if not passed else ""),
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

    # Check no_python_recipes if requested
    if test.expect.no_python_recipes and test.project_key:
        checks.extend(_check_no_python_recipes(test.project_key))

    return VerificationResult(checks=checks)


def _check_no_python_recipes(project_key: str) -> list[VerificationCheck]:
    """Verify no python/r/shell recipe types exist in the project."""
    import json as _json

    cmd = f"dku recipe list -P {project_key} -o json"
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            return [
                VerificationCheck(
                    command=cmd, passed=False, error=f"Failed: {result.stderr[:200]}"
                )
            ]

        recipes = _json.loads(result.stdout)
        code_types = {"python", "r", "shell", "pyspark", "sparkr", "spark_scala"}
        code_recipes = [r for r in recipes if r.get("type", "").lower() in code_types]

        if code_recipes:
            names = [r.get("name", "?") for r in code_recipes]
            return [
                VerificationCheck(
                    command="no_python_recipes check",
                    passed=False,
                    error=f"Found {len(code_recipes)} code recipe(s): {', '.join(names)}. Expected visual recipes only.",
                )
            ]
        return [
            VerificationCheck(
                command="no_python_recipes check",
                passed=True,
                output="All recipes are visual",
            )
        ]
    except Exception as e:
        return [
            VerificationCheck(
                command="no_python_recipes check", passed=False, error=str(e)
            )
        ]


def check_regressions(run_id: str, config: dict) -> None:
    """Compare current run against baselines and print warnings."""
    try:
        from benchmark.store.baselines import load_baselines
        from benchmark.store.query import get_regressions
    except ImportError:
        return

    baselines = load_baselines()
    if not baselines.get("scores"):
        return

    threshold = config["runner"].get("baseline_threshold", 0.1)
    regressions = get_regressions(run_id, threshold=threshold)

    if regressions:
        print(
            f"\n  WARNING: {len(regressions)} regression(s) vs baseline ({baselines.get('baseline_run_id', '?')}):"
        )
        for r in regressions:
            print(
                f"    {r['test_id']:30s} {r['baseline_score']:.2f} -> {r['current_score']:.2f} ({r['delta']:+.2f})"
            )
    else:
        print("  No regressions vs baseline.")


def main():
    parser = argparse.ArgumentParser(description="dku-cli Benchmark Runner")
    parser.add_argument(
        "--agent", type=str, help="Agent to test (claude, codex, or comma-separated)"
    )
    parser.add_argument("--tier", type=str, help="Tier(s) to run (e.g., 1 or 1,2,3)")
    parser.add_argument("--test", type=str, help="Single test ID to run")
    parser.add_argument(
        "--tag",
        type=str,
        help="Run scenarios matching a tag (e.g., smoke, ci, migration)",
    )
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
    elif args.tag:
        scenarios = [s for s in all_scenarios if args.tag in s.tags]
    else:
        scenarios = all_scenarios

    print(f"  Scenarios: {len(scenarios)} tests")
    if args.tag:
        print(f"  Tag filter: {args.tag}")
    total_runs = len(scenarios) * len(agents)
    print(f"  Total runs: {total_runs} ({len(scenarios)} tests x {len(agents)} agents)")

    if args.dry_run:
        print("\n  Dry run — tests that would execute:")
        for s in scenarios:
            fixtures_str = (
                f" fixtures={','.join(f.path for f in s.fixtures)}"
                if s.fixtures
                else ""
            )
            tags_str = f" tags={s.tags}" if s.tags else ""
            for a in agents:
                print(
                    f"    [{a.name:6s}] {s.id:30s} (tier {s.tier}, project={'yes' if s.needs_project else 'no'}{fixtures_str}{tags_str})"
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
                cost = record.agent_result.cost_usd
                print(
                    f"  [{completed:3d}/{total_runs}] {status} {agent_name:6s} {test_id:25s} "
                    f"score={score:.2f} {duration}ms ${cost:.3f}"
                )
            except Exception as e:
                completed += 1
                print(
                    f"  [{completed:3d}/{total_runs}] ERR  {agent_name:6s} {test_id:25s} {e}"
                )

    # Generate reports
    print("\n  Generating reports...")
    reporter = Reporter(run_id, config=config)
    reporter.generate(results)

    recommender = Recommender(run_id)
    recommender.generate(results)

    # Check for regressions vs baseline
    check_regressions(run_id, config)

    # Cleanup
    cleanup_fixtures()

    print(f"\n  Done. Reports at: benchmark/reports/{run_id}/")


if __name__ == "__main__":
    main()
