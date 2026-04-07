#!/usr/bin/env python3
"""Analysis CLI for cross-run benchmark comparison.

Usage:
    python -m benchmark.cli trends [--tier N] [--last 10]
    python -m benchmark.cli compare <run1> <run2>
    python -m benchmark.cli history <test_id> [--last 20]
    python -m benchmark.cli regressions <run_id>
    python -m benchmark.cli set-baseline <run_id>
    python -m benchmark.cli costs [--last 5]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from benchmark.store.baselines import load_baselines, set_baseline  # noqa: E402
from benchmark.store.query import (  # noqa: E402
    compare_runs,
    get_regressions,
    get_test_history,
    get_trends,
)
from benchmark.store.reader import load_all_runs  # noqa: E402


def cmd_trends(args):
    """Show pass rate and cost trends across recent runs."""
    trends = get_trends(tier=args.tier, last_n=args.last)
    if not trends:
        print("  No runs found.")
        return

    print(f"\n  Pass rate trend (last {len(trends)} runs):\n")
    print(
        f"  {'Run':<30s} {'Tests':>5s} {'Pass%':>6s} {'AvgScore':>9s} {'Cost':>8s} {'Duration':>10s}"
    )
    print(f"  {'-' * 70}")
    for t in trends:
        cost_str = (
            f"${t['estimated_cost_usd']:.2f}" if t.get("estimated_cost_usd") else "n/a"
        )
        dur_str = (
            f"{t['total_duration_ms'] / 1000:.0f}s"
            if t.get("total_duration_ms")
            else "n/a"
        )
        avg_score = t.get("avg_score", 0)
        print(
            f"  {t['run_id']:<30s} {t['total_tests']:>5d} {t['pass_rate'] * 100:>5.1f}% "
            f"{avg_score:>8.3f} {cost_str:>8s} {dur_str:>10s}"
        )
    print()


def cmd_compare(args):
    """Compare two runs side-by-side."""
    result = compare_runs(args.run1, args.run2)
    if "error" in result:
        print(f"  ERROR: {result['error']}")
        return

    r1, r2 = result["run1"], result["run2"]
    delta_pct = result["delta_pass_rate"] * 100

    print(f"\n  Comparing: {r1['run_id']} vs {r2['run_id']}\n")
    print(f"  {'Metric':<20s} {'Run 1':>10s} {'Run 2':>10s} {'Delta':>10s}")
    print(f"  {'-' * 52}")
    print(f"  {'Tests':<20s} {r1['total_tests']:>10d} {r2['total_tests']:>10d}")
    print(f"  {'Passed':<20s} {r1['passed']:>10d} {r2['passed']:>10d}")
    print(
        f"  {'Pass rate':<20s} {r1['pass_rate'] * 100:>9.1f}% {r2['pass_rate'] * 100:>9.1f}% "
        f"{delta_pct:>+9.1f}%"
    )
    c1 = r1.get("estimated_cost_usd", 0) or 0
    c2 = r2.get("estimated_cost_usd", 0) or 0
    if c1 or c2:
        print(
            f"  {'Cost':<20s} {'$' + f'{c1:.2f}':>10s} {'$' + f'{c2:.2f}':>10s} {'$' + f'{c2 - c1:+.2f}':>10s}"
        )

    if result["regressions"]:
        print("\n  Regressions (score dropped > 0.10):")
        for r in result["regressions"]:
            print(
                f"    {r['test_id']:30s} {r['score_1']:.2f} -> {r['score_2']:.2f} ({r['delta']:+.2f})"
            )

    if result["improvements"]:
        print("\n  Improvements (score improved > 0.10):")
        for r in result["improvements"]:
            print(
                f"    {r['test_id']:30s} {r['score_1']:.2f} -> {r['score_2']:.2f} ({r['delta']:+.2f})"
            )

    if not result["regressions"] and not result["improvements"]:
        print("\n  No significant changes (threshold: 0.10).")
    print()


def cmd_history(args):
    """Show score history for a single test."""
    history = get_test_history(args.test_id, limit=args.last)
    if not history:
        print(f"  No results found for test: {args.test_id}")
        return

    print(f"\n  Score history for: {args.test_id} (last {len(history)})\n")
    print(f"  {'Run':<30s} {'Score':>6s} {'Pass':>5s} {'Tokens':>8s} {'Duration':>10s}")
    print(f"  {'-' * 62}")
    for h in history:
        dur_str = f"{h['duration_ms'] / 1000:.0f}s" if h.get("duration_ms") else "n/a"
        tok_str = str(h.get("output_tokens", "n/a"))
        print(
            f"  {h['run_id']:<30s} {h['score']:>6.3f} {'YES' if h['passed'] else 'NO':>5s} "
            f"{tok_str:>8s} {dur_str:>10s}"
        )
    print()


def cmd_regressions(args):
    """Show regressions vs baseline for a specific run."""
    regressions = get_regressions(args.run_id, threshold=args.threshold)
    baselines = load_baselines()
    baseline_run = baselines.get("baseline_run_id", "none set")

    if not regressions:
        print(f"  No regressions vs baseline ({baseline_run}).")
        return

    print(f"\n  Regressions vs baseline ({baseline_run}):\n")
    print(f"  {'Test':<35s} {'Baseline':>8s} {'Current':>8s} {'Delta':>8s}")
    print(f"  {'-' * 62}")
    for r in regressions:
        print(
            f"  {r['test_id']:<35s} {r['baseline_score']:>8.3f} {r['current_score']:>8.3f} "
            f"{r['delta']:>+7.3f}"
        )
    print()


def cmd_set_baseline(args):
    """Set a run as the golden baseline."""
    try:
        baselines = set_baseline(args.run_id)
    except ValueError as e:
        print(f"  ERROR: {e}")
        return
    n = len(baselines.get("scores", {}))
    print(f"  Baseline set from {args.run_id}: {n} test scores recorded.")
    print("  Written to: benchmark/baselines.json")


def cmd_costs(args):
    """Show cost breakdown across recent runs."""
    runs = load_all_runs()
    if not runs:
        print("  No runs found.")
        return

    # Take last N
    runs = runs[-args.last :]

    print(f"\n  Cost breakdown (last {len(runs)} runs):\n")
    print(
        f"  {'Run':<30s} {'Tests':>5s} {'In Tokens':>10s} {'Out Tokens':>10s} {'Cost':>8s}"
    )
    print(f"  {'-' * 65}")
    total_cost = 0
    for r in runs:
        cost = r.get("estimated_cost_usd", 0) or 0
        total_cost += cost
        in_tok = r.get("total_input_tokens", 0) or 0
        out_tok = r.get("total_output_tokens", 0) or 0
        print(
            f"  {r['run_id']:<30s} {r.get('total_tests', 0):>5d} {in_tok:>10,d} "
            f"{out_tok:>10,d} ${cost:>7.2f}"
        )
    print(f"  {'-' * 65}")
    print(f"  {'Total':<30s} {'':>5s} {'':>10s} {'':>10s} ${total_cost:>7.2f}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark analysis CLI — cross-run comparison, trends, and regression detection"
    )
    subparsers = parser.add_subparsers(dest="command", help="Analysis command")

    # trends
    p_trends = subparsers.add_parser("trends", help="Pass rate and cost trends")
    p_trends.add_argument("--tier", type=int, default=None, help="Filter by tier")
    p_trends.add_argument("--last", type=int, default=10, help="Number of recent runs")

    # compare
    p_compare = subparsers.add_parser("compare", help="Compare two runs")
    p_compare.add_argument("run1", help="First run ID")
    p_compare.add_argument("run2", help="Second run ID")

    # history
    p_history = subparsers.add_parser("history", help="Score history for a test")
    p_history.add_argument("test_id", help="Test ID to look up")
    p_history.add_argument(
        "--last", type=int, default=20, help="Number of recent results"
    )

    # regressions
    p_reg = subparsers.add_parser("regressions", help="Check regressions vs baseline")
    p_reg.add_argument("run_id", help="Run ID to check")
    p_reg.add_argument(
        "--threshold", type=float, default=0.1, help="Regression threshold"
    )

    # set-baseline
    p_base = subparsers.add_parser(
        "set-baseline", help="Set a run as the golden baseline"
    )
    p_base.add_argument("run_id", help="Run ID to use as baseline")

    # costs
    p_costs = subparsers.add_parser("costs", help="Cost breakdown across runs")
    p_costs.add_argument("--last", type=int, default=5, help="Number of recent runs")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    commands = {
        "trends": cmd_trends,
        "compare": cmd_compare,
        "history": cmd_history,
        "regressions": cmd_regressions,
        "set-baseline": cmd_set_baseline,
        "costs": cmd_costs,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
