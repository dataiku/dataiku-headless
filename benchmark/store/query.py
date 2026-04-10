"""Cross-run analysis queries built on the benchmark store reader."""

from __future__ import annotations

import logging
from datetime import datetime

from .baselines import get_baseline_score, load_baselines
from .reader import load_all_runs, load_run

logger = logging.getLogger(__name__)

# Default token pricing (per 1K tokens) when estimated_cost_usd is absent.
_DEFAULT_INPUT_COST_PER_1K = 0.015
_DEFAULT_OUTPUT_COST_PER_1K = 0.075


def _parse_timestamp(run_id: str) -> str | None:
    """Extract ISO timestamp from run_id like 'bench_20260325_164125'."""
    parts = run_id.split("_", 1)
    if len(parts) < 2:
        return None
    raw = parts[1]  # "20260325_164125"
    try:
        dt = datetime.strptime(raw, "%Y%m%d_%H%M%S")
        return dt.isoformat()
    except ValueError:
        return None


def _estimate_cost(summary: dict) -> float:
    """Return estimated_cost_usd if present, otherwise estimate from tokens."""
    if "estimated_cost_usd" in summary:
        return summary["estimated_cost_usd"]
    output_tokens = summary.get("total_output_tokens", 0)
    # We only have output tokens in the summary; estimate input as ~2x output
    # (rough heuristic). This gives a ballpark, not exact billing.
    input_tokens = output_tokens * 2
    cost = (input_tokens / 1000 * _DEFAULT_INPUT_COST_PER_1K) + (
        output_tokens / 1000 * _DEFAULT_OUTPUT_COST_PER_1K
    )
    return round(cost, 4)


def get_test_history(
    test_id: str, agent: str = "claude", limit: int = 20
) -> list[dict]:
    """Return score history for a specific test across runs.

    Returns list of {run_id, timestamp, score, passed, duration_ms,
    output_tokens} sorted newest first, capped at ``limit``.
    """
    all_runs = load_all_runs()
    results: list[dict] = []

    for run in all_runs:
        if run.get("agent") != agent:
            continue
        for test in run.get("tests", []):
            if test.get("test_id") != test_id:
                continue
            results.append(
                {
                    "run_id": run["run_id"],
                    "timestamp": _parse_timestamp(run["run_id"]),
                    "score": test.get("overall_score"),
                    "passed": test.get("passed"),
                    "duration_ms": test.get("duration_ms"),
                    "output_tokens": test.get("output_tokens"),
                }
            )
            break  # One test per run at most

    # Newest first
    results.reverse()
    return results[:limit]


def get_trends(
    agent: str = "claude", tier: int | None = None, last_n: int = 10
) -> list[dict]:
    """Return pass rate and cost trend across last N runs.

    If ``tier`` is specified, only counts tests in that tier.

    Returns list of {run_id, total_tests, passed, pass_rate,
    total_output_tokens, total_duration_ms, estimated_cost_usd}
    sorted oldest first (for plotting).
    """
    all_runs = load_all_runs()
    filtered = [r for r in all_runs if r.get("agent") == agent]

    # Take the last N runs (they're already oldest-first from load_all_runs)
    filtered = filtered[-last_n:] if last_n else filtered

    trends: list[dict] = []
    for run in filtered:
        if tier is not None:
            # Recalculate from individual tests for the requested tier
            tier_tests = [t for t in run.get("tests", []) if t.get("tier") == tier]
            total = len(tier_tests)
            passed = sum(1 for t in tier_tests if t.get("passed"))
            pass_rate = round(passed / total, 4) if total else 0.0
            output_tokens = sum(t.get("output_tokens", 0) for t in tier_tests)
            duration_ms = sum(t.get("duration_ms", 0) for t in tier_tests)
            scores = [t.get("overall_score", 0) for t in tier_tests]
        else:
            total = run.get("total_tests", 0)
            passed = run.get("passed", 0)
            pass_rate = run.get("pass_rate", 0.0)
            output_tokens = run.get("total_output_tokens", 0)
            duration_ms = run.get("total_duration_ms", 0)
            scores = [t.get("overall_score", 0) for t in run.get("tests", [])]

        avg_score = round(sum(scores) / len(scores), 4) if scores else 0.0

        trends.append(
            {
                "run_id": run["run_id"],
                "total_tests": total,
                "passed": passed,
                "pass_rate": pass_rate,
                "avg_score": avg_score,
                "total_output_tokens": output_tokens,
                "total_duration_ms": duration_ms,
                "estimated_cost_usd": _estimate_cost(run)
                if tier is None
                else round(
                    (output_tokens * 2 / 1000 * _DEFAULT_INPUT_COST_PER_1K)
                    + (output_tokens / 1000 * _DEFAULT_OUTPUT_COST_PER_1K),
                    4,
                ),
            }
        )

    return trends


def compare_runs(run_id_1: str, run_id_2: str) -> dict:
    """Compare two runs side-by-side.

    Returns dict with run1/run2 summaries, delta_pass_rate,
    regressions (score dropped > 0.1), and improvements (score
    improved > 0.1).
    """
    r1 = load_run(run_id_1)
    r2 = load_run(run_id_2)

    if r1 is None or r2 is None:
        missing = []
        if r1 is None:
            missing.append(run_id_1)
        if r2 is None:
            missing.append(run_id_2)
        return {"error": f"Run(s) not found: {', '.join(missing)}"}

    def _run_summary(run: dict) -> dict:
        return {
            "run_id": run["run_id"],
            "agent": run.get("agent"),
            "pass_rate": run.get("pass_rate", 0.0),
            "total_tests": run.get("total_tests", 0),
            "passed": run.get("passed", 0),
            "failed": run.get("failed", 0),
            "total_output_tokens": run.get("total_output_tokens", 0),
            "total_duration_ms": run.get("total_duration_ms", 0),
            "estimated_cost_usd": _estimate_cost(run),
        }

    # Build test score maps: test_id -> overall_score
    scores_1: dict[str, float] = {}
    for t in r1.get("tests", []):
        tid = t.get("test_id")
        if tid:
            scores_1[tid] = t.get("overall_score", 0.0)

    scores_2: dict[str, float] = {}
    for t in r2.get("tests", []):
        tid = t.get("test_id")
        if tid:
            scores_2[tid] = t.get("overall_score", 0.0)

    # Find all test_ids across both runs
    all_tests = set(scores_1.keys()) | set(scores_2.keys())

    regressions: list[dict] = []
    improvements: list[dict] = []
    threshold = 0.1

    for tid in sorted(all_tests):
        s1 = scores_1.get(tid)
        s2 = scores_2.get(tid)
        if s1 is None or s2 is None:
            continue  # Test only present in one run
        delta = round(s2 - s1, 4)
        if delta < -threshold:
            regressions.append(
                {"test_id": tid, "score_1": s1, "score_2": s2, "delta": delta}
            )
        elif delta > threshold:
            improvements.append(
                {"test_id": tid, "score_1": s1, "score_2": s2, "delta": delta}
            )

    return {
        "run1": _run_summary(r1),
        "run2": _run_summary(r2),
        "delta_pass_rate": round(
            r2.get("pass_rate", 0.0) - r1.get("pass_rate", 0.0), 4
        ),
        "regressions": regressions,
        "improvements": improvements,
    }


def get_regressions(run_id: str, threshold: float = 0.1) -> list[dict]:
    """Compare a run against baselines.json, return tests that regressed.

    Returns list of {test_id, baseline_score, current_score, delta}.
    Returns empty list if no baselines file or run not found.
    """
    run = load_run(run_id)
    if run is None:
        logger.warning("Run not found: %s", run_id)
        return []

    baselines = load_baselines()
    if not baselines or "scores" not in baselines:
        logger.info("No baselines set, nothing to compare against")
        return []

    agent = run.get("agent", "claude")
    regressions: list[dict] = []

    for test in run.get("tests", []):
        tid = test.get("test_id")
        if not tid:
            continue
        baseline_score = get_baseline_score(tid, agent)
        if baseline_score is None:
            continue
        current_score = test.get("overall_score", 0.0)
        delta = round(current_score - baseline_score, 4)
        if delta < -threshold:
            regressions.append(
                {
                    "test_id": tid,
                    "baseline_score": baseline_score,
                    "current_score": current_score,
                    "delta": delta,
                }
            )

    return regressions
