"""Report generation — JSON summaries and terminal output."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from benchmark.analyzer.scorer import Score
from benchmark.analyzer.trace_parser import summarize_trace
from benchmark.agents.base import AgentResult
from benchmark.scenarios.schema import Scenario


@dataclass
class TestResultRecord:
    """Complete record for one test + one agent."""

    test_id: str
    tier: int
    category: str
    prompt: str
    agent: str
    score: Score
    trace_summary: dict
    agent_result: AgentResult


class Reporter:
    """Generate benchmark reports."""

    def __init__(self, run_id: str, output_dir: "Optional[Path]" = None):
        self.run_id = run_id
        self.output_dir = output_dir or Path("benchmark/reports") / run_id
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "traces").mkdir(exist_ok=True)

    def generate(self, records: list[TestResultRecord]):
        """Generate all report artifacts."""
        self._write_traces(records)
        summary = self._build_summary(records)
        self._write_summary(summary)
        self._print_terminal(summary, records)

    def _write_traces(self, records: list[TestResultRecord]):
        """Write raw traces for each test."""
        for rec in records:
            trace_file = self.output_dir / "traces" / f"{rec.test_id}_{rec.agent}.json"
            trace_file.write_text(json.dumps({
                "test_id": rec.test_id,
                "agent": rec.agent,
                "trace": rec.trace_summary,
                "score": {
                    "overall": rec.score.overall,
                    "passed": rec.score.passed,
                    "scores": rec.score.scores,
                    "details": rec.score.details,
                },
                "raw_output_length": len(rec.agent_result.raw_output),
            }, indent=2))

    def _build_summary(self, records: list[TestResultRecord]) -> dict:
        """Build aggregate summary."""
        by_agent: dict[str, list[TestResultRecord]] = defaultdict(list)
        by_tier: dict[int, dict[str, list[TestResultRecord]]] = defaultdict(lambda: defaultdict(list))
        by_category: dict[str, dict[str, list[TestResultRecord]]] = defaultdict(lambda: defaultdict(list))

        for rec in records:
            by_agent[rec.agent].append(rec)
            by_tier[rec.tier][rec.agent].append(rec)
            by_category[rec.category][rec.agent].append(rec)

        summary = {
            "run_id": self.run_id,
            "total_tests": len(set(r.test_id for r in records)),
            "agents": {},
            "by_tier": {},
            "by_category": {},
            "failures": [],
            "comparison": {},
        }

        # Per-agent aggregates
        for agent, recs in by_agent.items():
            passed = sum(1 for r in recs if r.score.passed)
            total_tokens = sum(r.agent_result.input_tokens + r.agent_result.output_tokens for r in recs)
            total_duration = sum(r.agent_result.duration_ms for r in recs)
            summary["agents"][agent] = {
                "total": len(recs),
                "passed": passed,
                "failed": len(recs) - passed,
                "pass_rate": round(passed / len(recs), 3) if recs else 0,
                "total_tokens": total_tokens,
                "total_duration_ms": total_duration,
                "avg_duration_ms": total_duration // len(recs) if recs else 0,
            }

        # Per-tier per-agent
        for tier, agent_recs in sorted(by_tier.items()):
            tier_key = f"tier{tier}"
            summary["by_tier"][tier_key] = {}
            for agent, recs in agent_recs.items():
                passed = sum(1 for r in recs if r.score.passed)
                summary["by_tier"][tier_key][agent] = {
                    "total": len(recs),
                    "passed": passed,
                    "pass_rate": round(passed / len(recs), 3) if recs else 0,
                }

        # Failures
        for rec in records:
            if not rec.score.passed:
                summary["failures"].append({
                    "test_id": rec.test_id,
                    "tier": rec.tier,
                    "agent": rec.agent,
                    "overall_score": round(rec.score.overall, 3),
                    "scores": {k: round(v, 3) for k, v in rec.score.scores.items()},
                    "details": rec.score.details,
                })

        # Head-to-head comparison
        test_ids = set(r.test_id for r in records)
        claude_wins = []
        codex_wins = []
        both_pass = []
        both_fail = []

        for tid in test_ids:
            agents_for_test = {r.agent: r for r in records if r.test_id == tid}
            c = agents_for_test.get("claude")
            x = agents_for_test.get("codex")
            if c and x:
                if c.score.passed and not x.score.passed:
                    claude_wins.append(tid)
                elif x.score.passed and not c.score.passed:
                    codex_wins.append(tid)
                elif c.score.passed and x.score.passed:
                    both_pass.append(tid)
                else:
                    both_fail.append(tid)

        summary["comparison"] = {
            "claude_only_wins": claude_wins,
            "codex_only_wins": codex_wins,
            "both_pass": both_pass,
            "both_fail": both_fail,
        }

        return summary

    def _write_summary(self, summary: dict):
        """Write summary JSON."""
        path = self.output_dir / "summary.json"
        path.write_text(json.dumps(summary, indent=2))

    def _print_terminal(self, summary: dict, records: list[TestResultRecord]):
        """Print results to terminal."""
        print(f"\n{'=' * 60}")
        print(f"  Benchmark Run: {self.run_id}")
        print(f"{'=' * 60}\n")

        # Agent comparison
        for agent, stats in summary["agents"].items():
            emoji = "C" if agent == "claude" else "X"
            rate = stats["pass_rate"] * 100
            print(f"  [{emoji}] {agent:8s}  {stats['passed']}/{stats['total']} passed ({rate:.0f}%)  "
                  f"avg {stats['avg_duration_ms']}ms  {stats['total_tokens']:,} tokens")

        # Tier breakdown
        print(f"\n  {'Tier':<8}", end="")
        agents = list(summary["agents"].keys())
        for a in agents:
            print(f"  {a:>10}", end="")
        print()
        print(f"  {'-' * (8 + 12 * len(agents))}")

        for tier_key, tier_data in sorted(summary["by_tier"].items()):
            print(f"  {tier_key:<8}", end="")
            for a in agents:
                data = tier_data.get(a, {})
                rate = data.get("pass_rate", 0) * 100
                total = data.get("total", 0)
                passed = data.get("passed", 0)
                print(f"  {passed}/{total} ({rate:3.0f}%)", end="")
            print()

        # Head-to-head
        comp = summary.get("comparison", {})
        print(f"\n  Head-to-head:")
        print(f"    Both pass:       {len(comp.get('both_pass', []))}")
        print(f"    Claude only:     {len(comp.get('claude_only_wins', []))}")
        print(f"    Codex only:      {len(comp.get('codex_only_wins', []))}")
        print(f"    Both fail:       {len(comp.get('both_fail', []))}")

        # Failures
        failures = summary.get("failures", [])
        if failures:
            print(f"\n  Failures ({len(failures)}):")
            for f in failures[:10]:
                print(f"    {f['test_id']:20s} [{f['agent']:6s}] score={f['overall_score']:.2f}  {f.get('details', {})}")

        print(f"\n  Report: {self.output_dir / 'summary.json'}")
        print(f"{'=' * 60}\n")
