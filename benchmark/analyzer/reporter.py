"""Report generation for outcome-based benchmark runs."""

from __future__ import annotations

import json
import statistics
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional  # noqa: F401 — used by dataclass fields

from benchmark.agents.base import AgentResult
from benchmark.analyzer import coherence
from benchmark.analyzer.scorer import Score


@dataclass
class TestResultRecord:
    """Complete record for one test + one agent."""

    test_id: str
    category: str
    prompt: str
    agent: str
    score: Score
    agent_result: AgentResult
    difficulty: Optional[str] = None
    gap_type: str = "none"


def _stats(values: list[float]) -> dict:
    """min/max/mean/stddev for a list of numbers (sample stddev, 0 when n<2)."""
    return {
        "min": round(min(values), 4),
        "max": round(max(values), 4),
        "mean": round(statistics.fmean(values), 4),
        "stddev": round(statistics.stdev(values), 4) if len(values) > 1 else 0.0,
    }


def _mean_score(records: list) -> float:
    """Average fractional score across records (0.0 when empty)."""
    return (
        round(sum(r.score.score for r in records) / len(records), 3) if records else 0.0
    )


def _get_git_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""


class Reporter:
    """Generate benchmark reports."""

    def __init__(
        self,
        run_id: str,
        output_dir: Optional[Path] = None,
        config: Optional[dict] = None,
        environment: Optional[dict] = None,
    ):
        self.run_id = run_id
        self.output_dir = output_dir or Path("benchmark/reports") / run_id
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "traces").mkdir(exist_ok=True)
        self.config = config or {}
        self.environment = environment or {}

    def generate(self, records: list[TestResultRecord]):
        self._write_traces(records)
        summary = self._build_summary(records)
        self._write_summary(summary)
        self._print_terminal(summary, records)

    def _write_traces(self, records: list[TestResultRecord]):
        for rec in records:
            stem = f"{rec.test_id}_{rec.agent}"
            raw = rec.agent_result.raw_stdout or ""
            if rec.agent_result.raw_stderr:
                raw += "\n\n===== STDERR =====\n" + rec.agent_result.raw_stderr
            if raw.strip():
                (self.output_dir / "traces" / f"{stem}.log").write_text(raw)
            trace_file = self.output_dir / "traces" / f"{stem}.json"
            trace_file.write_text(
                json.dumps(
                    {
                        "test_id": rec.test_id,
                        "agent": rec.agent,
                        "prompt": rec.prompt,
                        "passed": rec.score.passed,
                        "score": rec.score.score,
                        "details": rec.score.details,
                        "assistant_text": rec.agent_result.assistant_text[:5000],
                        "skill_calls": rec.agent_result.skill_calls,
                        "mcp_calls": rec.agent_result.mcp_calls,
                        "mcp_tool_calls": [
                            {
                                "tool": tc.get("name"),
                                "arguments": tc.get("arguments"),
                                "error": tc.get("error"),
                            }
                            for tc in rec.agent_result.tool_calls
                            if tc.get("type") == "mcp"
                        ],
                        "coherence_issues": coherence.check(
                            rec.agent,
                            rec.agent_result.bash_commands,
                            rec.agent_result.mcp_calls,
                        ),
                        "bash_commands": rec.agent_result.bash_commands,
                        "errors": rec.agent_result.errors,
                        "timed_out": rec.agent_result.timed_out,
                        "errored": rec.agent_result.errored,
                        "usage_partial": rec.agent_result.usage_partial,
                    },
                    indent=2,
                )
            )

    def _build_summary(self, records: list[TestResultRecord]) -> dict:
        by_category: dict[str, list] = defaultdict(list)
        by_gap_type: dict[str, list] = defaultdict(list)
        by_difficulty: dict[str, list] = defaultdict(list)

        for rec in records:
            by_category[rec.category].append(rec)
            by_gap_type[rec.gap_type].append(rec)
            by_difficulty[rec.difficulty or "unknown"].append(rec)

        passed = sum(1 for r in records if r.score.passed)
        timed_out = sum(1 for r in records if r.agent_result.timed_out)
        errored = sum(1 for r in records if r.agent_result.errored)
        agents_used = sorted({rec.agent for rec in records}) if records else ["claude"]
        agent_name = agents_used[0] if len(agents_used) == 1 else ",".join(agents_used)

        total_input = sum(r.agent_result.input_tokens for r in records)
        total_output = sum(r.agent_result.output_tokens for r in records)
        total_cost = sum(r.agent_result.cost_usd for r in records)

        summary = {
            "run_id": self.run_id,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "agent": agent_name,
            "git_sha": _get_git_sha(),
            "environment": self.environment,
            "total_tests": len(records),
            "passed": passed,
            "failed": len(records) - passed,
            "timed_out": timed_out,
            "errored": errored,
            "pass_rate": round(passed / len(records), 3) if records else 0,
            "mean_score": _mean_score(records),
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_duration_ms": sum(r.agent_result.duration_ms for r in records),
            "total_cost_usd": round(total_cost, 4),
            "by_agent": {},
            "by_domain": {},
            "by_difficulty": {},
            "by_gap_type": {},
            "by_test_agent": {},
            "tests": [],
        }

        by_agent: dict[str, list] = defaultdict(list)
        for rec in records:
            by_agent[rec.agent].append(rec)

        profile_cfg = self.config.get("profiles", {})
        for agent, recs in sorted(by_agent.items()):
            p = sum(1 for r in recs if r.score.passed)
            agent_cfg = profile_cfg.get(agent, {})
            # Completed-only token/cost: exclude partial (timed-out) usage — the
            # fair, presentable figure; timeouts are reported separately.
            clean = [r for r in recs if not r.agent_result.usage_partial]
            n_clean = len(clean)
            summary["by_agent"][agent] = {
                "model": agent_cfg.get("model", ""),
                "profile": agent,
                "total": len(recs),
                "passed": p,
                "timed_out": sum(1 for r in recs if r.agent_result.timed_out),
                "errored": sum(1 for r in recs if r.agent_result.errored),
                "pass_rate": round(p / len(recs), 3),
                "mean_score": _mean_score(recs),
                "total_cost_usd": round(sum(r.agent_result.cost_usd for r in recs), 4),
                "completed_count": n_clean,
                "completed_cost_usd": round(
                    sum(r.agent_result.cost_usd for r in clean), 4
                ),
                "completed_input_tokens": sum(
                    r.agent_result.input_tokens for r in clean
                ),
                "completed_output_tokens": sum(
                    r.agent_result.output_tokens for r in clean
                ),
                "completed_cost_per_test": round(
                    sum(r.agent_result.cost_usd for r in clean) / n_clean, 4
                )
                if n_clean
                else 0.0,
                "completed_input_per_test": round(
                    sum(r.agent_result.input_tokens for r in clean) / n_clean
                )
                if n_clean
                else 0,
            }

        for cat, recs in sorted(by_category.items()):
            p = sum(1 for r in recs if r.score.passed)
            summary["by_domain"][cat] = {
                "total": len(recs),
                "passed": p,
                "pass_rate": round(p / len(recs), 3),
                "mean_score": _mean_score(recs),
            }

        difficulty_order = {"easy": 0, "medium": 1, "hard": 2}
        for diff, recs in sorted(
            by_difficulty.items(), key=lambda kv: difficulty_order.get(kv[0], 99)
        ):
            p = sum(1 for r in recs if r.score.passed)
            summary["by_difficulty"][diff] = {
                "total": len(recs),
                "passed": p,
                "pass_rate": round(p / len(recs), 3),
                "mean_score": _mean_score(recs),
            }

        for gap_type, recs in sorted(by_gap_type.items()):
            p = sum(1 for r in recs if r.score.passed)
            summary["by_gap_type"][gap_type] = {
                "total": len(recs),
                "passed": p,
                "pass_rate": round(p / len(recs), 3),
                "mean_score": _mean_score(recs),
            }

        by_test_agent: dict[str, list] = defaultdict(list)
        for rec in records:
            by_test_agent[f"{rec.test_id}::{rec.agent}"].append(rec)
        for key, recs in sorted(by_test_agent.items()):
            test_id, agent = key.split("::", 1)
            p = sum(1 for r in recs if r.score.passed)
            summary["by_test_agent"][key] = {
                "test_id": test_id,
                "agent": agent,
                "n": len(recs),
                "passed": p,
                "pass_rate": round(p / len(recs), 3),
                "mean_score": _mean_score(recs),
                "duration_ms": _stats([r.agent_result.duration_ms for r in recs]),
                "cost_usd": _stats([r.agent_result.cost_usd for r in recs]),
            }

        for rec in records:
            summary["tests"].append(
                {
                    "test_id": rec.test_id,
                    "agent": rec.agent,
                    "domain": rec.category,
                    "difficulty": rec.difficulty,
                    "passed": rec.score.passed,
                    "timed_out": rec.agent_result.timed_out,
                    "errored": rec.agent_result.errored,
                    "score": round(rec.score.score, 3),
                    "gap_type": rec.gap_type,
                    "details": rec.score.details,
                    "n_commands": len(rec.agent_result.bash_commands),
                    "skill_reads": sum(
                        1 for c in rec.agent_result.bash_commands if "/skills/" in c
                    ),
                    "skills_consulted": len(rec.agent_result.skill_calls),
                    "mcp_calls": len(rec.agent_result.mcp_calls),
                    "commands_executed": rec.agent_result.bash_commands[:10],
                    "duration_ms": rec.agent_result.duration_ms,
                    "input_tokens": rec.agent_result.input_tokens,
                    "output_tokens": rec.agent_result.output_tokens,
                    "cost_usd": round(rec.agent_result.cost_usd, 4),
                    "usage_partial": rec.agent_result.usage_partial,
                }
            )

        return summary

    def _write_summary(self, summary: dict):
        (self.output_dir / "summary.json").write_text(json.dumps(summary, indent=2))

    def _print_repeat_stats(self, summary: dict):
        groups = summary["by_test_agent"]
        if not groups or max(g["n"] for g in groups.values()) < 2:
            return
        print("  Repeat stats (per scenario x profile):")
        print(
            f"    {'scenario':30s} {'profile':16s} {'pass':>12s} "
            f"{'time mean':>10s} {'time std':>9s} {'cost mean':>10s} {'cost std':>9s}"
        )
        for g in sorted(groups.values(), key=lambda x: (x["test_id"], x["agent"])):
            dur = g["duration_ms"]
            cost = g["cost_usd"]
            passes = f"{g['passed']}/{g['n']} ({g['pass_rate'] * 100:.0f}%)"
            print(
                f"    {g['test_id']:30.30s} {g['agent']:16.16s} {passes:>12s} "
                f"{dur['mean'] / 1000:>9.1f}s {dur['stddev'] / 1000:>8.1f}s "
                f"${cost['mean']:>8.3f} ${cost['stddev']:>7.3f}"
            )
        print(f"{'=' * 60}\n")

    def _print_terminal(self, summary: dict, records: list[TestResultRecord]):
        print(f"\n{'=' * 60}")
        print(f"  Benchmark: {self.run_id}")
        to = summary.get("timed_out", 0)
        err = summary.get("errored", 0)
        notes = []
        if to:
            notes.append(f"{to} timed out")
        if err:
            notes.append(f"{err} errored")
        note = f" — {', '.join(notes)}" if notes else ""
        print(
            f"  {summary['passed']}/{summary['total_tests']} passed "
            f"({summary['pass_rate'] * 100:.0f}%){note}"
        )
        if len(summary["by_agent"]) > 1:
            for agent, stats in sorted(summary["by_agent"].items()):
                print(
                    f"    {agent:12s} {stats['passed']}/{stats['total']} "
                    f"({stats['pass_rate'] * 100:.0f}%) ${stats['total_cost_usd']:.3f}"
                )
        if len(summary["by_difficulty"]) > 1:
            print("  by difficulty:")
            for diff, stats in summary["by_difficulty"].items():
                print(
                    f"    {diff:8s} {stats['passed']}/{stats['total']} "
                    f"({stats['pass_rate'] * 100:.0f}%)"
                )
        print(f"{'=' * 60}\n")

        self._print_repeat_stats(summary)

        for rec in sorted(records, key=lambda r: (r.score.passed, r.test_id, r.agent)):
            if rec.score.passed:
                status = "PASS"
            elif rec.agent_result.errored:
                status = "ERR"
            elif rec.agent_result.timed_out:
                status = "TIMEOUT"
            else:
                status = "FAIL"
            cmds = len(rec.agent_result.bash_commands)
            dur = rec.agent_result.duration_ms / 1000
            print(
                f"  {status:7s} {rec.agent:12s} {rec.test_id:30s} cmds={cmds} {dur:.0f}s"
            )
            if not rec.score.passed and rec.score.details:
                for detail in list(rec.score.details.values())[:2]:
                    print(f"       -> {detail[:80]}")

        print("\n  Reports:")
        print(f"    {self.output_dir / 'summary.json'}")
        print(f"    {self.output_dir / 'traces'}")
        print(f"{'=' * 60}\n")
