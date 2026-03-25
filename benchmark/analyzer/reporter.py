"""Report generation — rich narratives, not just pass/fail."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from benchmark.agents.base import AgentResult
from benchmark.analyzer.scorer import Score


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
    """Generate benchmark reports with rich narrative feedback."""

    def __init__(self, run_id: str, output_dir: Optional[Path] = None):
        self.run_id = run_id
        self.output_dir = output_dir or Path("benchmark/reports") / run_id
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "traces").mkdir(exist_ok=True)

    def generate(self, records: list[TestResultRecord]):
        """Generate all report artifacts."""
        self._write_traces(records)
        summary = self._build_summary(records)
        self._write_summary(summary)
        self._write_narrative(records)
        self._print_terminal(summary, records)

    def _write_traces(self, records: list[TestResultRecord]):
        """Write raw traces for each test."""
        for rec in records:
            trace_file = self.output_dir / "traces" / f"{rec.test_id}_{rec.agent}.json"
            trace_file.write_text(
                json.dumps(
                    {
                        "test_id": rec.test_id,
                        "agent": rec.agent,
                        "prompt": rec.prompt,
                        "trace": rec.trace_summary,
                        "score": {
                            "overall": rec.score.overall,
                            "passed": rec.score.passed,
                            "scores": rec.score.scores,
                            "details": rec.score.details,
                        },
                        "assistant_text": rec.agent_result.assistant_text[:5000],
                        "bash_commands": rec.agent_result.bash_commands,
                        "errors": rec.agent_result.errors,
                        "raw_output_length": len(rec.agent_result.raw_output),
                    },
                    indent=2,
                )
            )

    def _write_narrative(self, records: list[TestResultRecord]):
        """Write rich narrative report — the main output for skill/CLI improvement."""
        sections = []
        sections.append(f"# Benchmark Narrative Report: {self.run_id}\n")

        # Sort by tier, then by pass/fail (failures first)
        sorted_recs = sorted(records, key=lambda r: (r.tier, r.score.passed, r.test_id))

        for rec in sorted_recs:
            sections.append(self._narrate_test(rec))

        # Overall findings
        sections.append(self._narrate_findings(records))

        path = self.output_dir / "narrative.md"
        path.write_text("\n".join(sections))

    def _narrate_test(self, rec: TestResultRecord) -> str:
        """Generate a rich narrative for a single test result."""
        status = "PASS" if rec.score.passed else "FAIL"
        lines = []
        lines.append(
            f"---\n## [{status}] {rec.test_id} (score: {rec.score.overall:.2f})\n"
        )
        lines.append(f"**Task:** {rec.prompt.strip()[:300]}\n")

        # What the agent did
        cmds = rec.agent_result.bash_commands
        if cmds:
            lines.append("**Commands executed:**")
            for i, cmd in enumerate(cmds, 1):
                # Truncate very long commands
                display = cmd[:200] + "..." if len(cmd) > 200 else cmd
                lines.append(f"{i}. `{display}`")
            lines.append("")
        else:
            lines.append("**Commands executed:** None\n")

        # Skills and agents
        if rec.agent_result.skill_invocations:
            lines.append(
                f"**Skills invoked:** {', '.join(rec.agent_result.skill_invocations)}"
            )
        if rec.agent_result.agent_spawns:
            descs = [
                a.get("description", "unknown") for a in rec.agent_result.agent_spawns
            ]
            lines.append(f"**Agents spawned:** {', '.join(descs)}")

        # Scoring breakdown
        lines.append("\n**Score breakdown:**")
        for key, val in rec.score.scores.items():
            icon = "+" if val >= 0.7 else "-"
            lines.append(f"  {icon} {key}: {val:.2f}")

        # What went wrong (details)
        if rec.score.details:
            lines.append("\n**Issues found:**")
            for key, detail in rec.score.details.items():
                lines.append(f"  - {detail}")

        # Agent's own output (what it told the user)
        agent_text = rec.agent_result.assistant_text.strip()
        if agent_text:
            # Look for error messages, confusion, or interesting observations
            truncated = agent_text[:1500]
            if len(agent_text) > 1500:
                truncated += "\n  ... (truncated)"
            lines.append(f"\n**Agent output (excerpt):**\n```\n{truncated}\n```")

        # Errors encountered
        if rec.agent_result.errors:
            lines.append("\n**Errors:**")
            for err in rec.agent_result.errors:
                lines.append(f"  - {err}")

        # Timing and cost
        duration_s = rec.agent_result.duration_ms / 1000
        out_tok = rec.agent_result.output_tokens
        lines.append(
            f"\n**Metrics:** {duration_s:.1f}s, {out_tok:,} output tokens, "
            f"{len(cmds)} commands"
        )

        # Analysis: what does this tell us about the skill/CLI?
        analysis = self._analyze_for_improvements(rec)
        if analysis:
            lines.append(f"\n**Skill/CLI insight:** {analysis}")

        lines.append("")
        return "\n".join(lines)

    def _analyze_for_improvements(self, rec: TestResultRecord) -> str:
        """Infer what this result tells us about skill/CLI limitations."""
        insights = []
        cmds = rec.agent_result.bash_commands
        text = rec.agent_result.assistant_text.lower()

        # Check for common patterns
        if rec.agent_result.timed_out:
            insights.append(
                "Agent timed out — task may be too complex for a single prompt, "
                "or the CLI output was too large to process."
            )

        # Agent tried a command that doesn't exist
        for cmd in cmds:
            if "error" in cmd.lower() or "not found" in cmd.lower():
                insights.append(f"Agent encountered an error running: {cmd[:100]}")

        # Agent expressed confusion in its output
        confusion_signals = [
            "i'm not sure",
            "doesn't seem to",
            "couldn't find",
            "not available",
            "no such command",
            "error:",
            "failed to",
        ]
        for signal in confusion_signals:
            if signal in text:
                # Extract the context around the confusion
                idx = text.index(signal)
                context = rec.agent_result.assistant_text[max(0, idx - 50) : idx + 100]
                insights.append(
                    f"Agent expressed uncertainty: '...{context.strip()}...'"
                )
                break

        # Agent used Python API instead of CLI
        if any("dataikuapi" in cmd or "import dataiku" in cmd for cmd in cmds):
            insights.append(
                "Agent fell back to Python API instead of using dku CLI. "
                "The skill should provide clearer guidance for this task."
            )

        # Agent didn't chain commands
        dku_calls = [c for c in cmds if "dku " in c]
        if len(dku_calls) > 5:
            insights.append(
                f"Agent used {len(dku_calls)} separate dku calls. "
                "Consider adding chaining examples for this workflow to the skill."
            )

        # Agent read skill docs
        if rec.trace_summary.get("skill_docs_read"):
            docs = rec.trace_summary["skill_docs_read"]
            insights.append(f"Agent consulted skill docs: {', '.join(docs)}")

        if not insights:
            if rec.score.passed:
                return "Clean pass — skill/CLI worked as expected for this task."
            else:
                return "Failed without clear signals — review the trace for details."

        return " | ".join(insights)

    def _narrate_findings(self, records: list[TestResultRecord]) -> str:
        """Generate overall findings section."""
        lines = []
        lines.append("---\n# Overall Findings\n")

        passed = [r for r in records if r.score.passed]
        failed = [r for r in records if not r.score.passed]

        lines.append(
            f"**Results:** {len(passed)}/{len(records)} passed "
            f"({len(passed) / len(records) * 100:.0f}%)\n"
        )

        # Group failures by category
        if failed:
            lines.append("## Failures\n")
            for rec in failed:
                lines.append(
                    f"- **{rec.test_id}** ({rec.score.overall:.2f}): "
                    f"{', '.join(rec.score.details.values()) or 'See trace'}"
                )

        # Common patterns across all tests
        all_cmds = []
        for r in records:
            all_cmds.extend(r.agent_result.bash_commands)

        # Commands the agent struggled with
        lines.append("\n## Skill/CLI Improvement Areas\n")

        confusion_tests = [
            r
            for r in records
            if any(
                s in r.agent_result.assistant_text.lower()
                for s in ["error", "couldn't", "not available", "failed"]
            )
        ]
        if confusion_tests:
            lines.append("### Agent encountered friction:")
            for r in confusion_tests:
                lines.append(
                    f"- {r.test_id}: review agent output for CLI error messages or missing commands"
                )

        timeout_tests = [r for r in records if r.agent_result.timed_out]
        if timeout_tests:
            lines.append("\n### Timeouts (task too complex or output too large):")
            for r in timeout_tests:
                lines.append(f"- {r.test_id}")

        lines.append("")
        return "\n".join(lines)

    def _build_summary(self, records: list[TestResultRecord]) -> dict:
        """Build aggregate summary JSON."""
        by_tier: dict[int, list[TestResultRecord]] = defaultdict(list)
        by_category: dict[str, list[TestResultRecord]] = defaultdict(list)

        for rec in records:
            by_tier[rec.tier].append(rec)
            by_category[rec.category].append(rec)

        passed = sum(1 for r in records if r.score.passed)

        summary = {
            "run_id": self.run_id,
            "agent": "claude",
            "total_tests": len(records),
            "passed": passed,
            "failed": len(records) - passed,
            "pass_rate": round(passed / len(records), 3) if records else 0,
            "total_output_tokens": sum(r.agent_result.output_tokens for r in records),
            "total_duration_ms": sum(r.agent_result.duration_ms for r in records),
            "by_tier": {},
            "by_category": {},
            "tests": [],
        }

        for tier, recs in sorted(by_tier.items()):
            p = sum(1 for r in recs if r.score.passed)
            summary["by_tier"][f"tier{tier}"] = {
                "total": len(recs),
                "passed": p,
                "pass_rate": round(p / len(recs), 3),
            }

        for cat, recs in sorted(by_category.items()):
            p = sum(1 for r in recs if r.score.passed)
            summary["by_category"][cat] = {
                "total": len(recs),
                "passed": p,
                "pass_rate": round(p / len(recs), 3),
            }

        for rec in records:
            summary["tests"].append(
                {
                    "test_id": rec.test_id,
                    "tier": rec.tier,
                    "category": rec.category,
                    "passed": rec.score.passed,
                    "overall_score": round(rec.score.overall, 3),
                    "scores": {k: round(v, 3) for k, v in rec.score.scores.items()},
                    "commands_executed": rec.agent_result.bash_commands[:10],
                    "duration_ms": rec.agent_result.duration_ms,
                    "output_tokens": rec.agent_result.output_tokens,
                    "issues": rec.score.details,
                }
            )

        return summary

    def _write_summary(self, summary: dict):
        path = self.output_dir / "summary.json"
        path.write_text(json.dumps(summary, indent=2))

    def _print_terminal(self, summary: dict, records: list[TestResultRecord]):
        """Print results to terminal."""
        print(f"\n{'=' * 60}")
        print(f"  Benchmark: {self.run_id}")
        print(
            f"  {summary['passed']}/{summary['total_tests']} passed "
            f"({summary['pass_rate'] * 100:.0f}%)"
        )
        print(f"{'=' * 60}\n")

        for rec in sorted(records, key=lambda r: (r.score.passed, r.test_id)):
            status = "PASS" if rec.score.passed else "FAIL"
            cmds = len(rec.agent_result.bash_commands)
            dur = rec.agent_result.duration_ms / 1000
            print(
                f"  {status} {rec.test_id:30s} score={rec.score.overall:.2f} "
                f"cmds={cmds} {dur:.0f}s"
            )
            if not rec.score.passed and rec.score.details:
                for detail in list(rec.score.details.values())[:2]:
                    print(f"       -> {detail[:80]}")

        print("\n  Reports:")
        print(f"    {self.output_dir / 'summary.json'}")
        print(f"    {self.output_dir / 'narrative.md'}")
        print(f"    {self.output_dir / 'recommendations.md'}")
        print(f"{'=' * 60}\n")
