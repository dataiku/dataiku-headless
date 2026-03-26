"""Generate actionable recommendations from benchmark results."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from benchmark.analyzer.reporter import TestResultRecord


class Recommender:
    """Analyze failures and produce actionable improvement suggestions."""

    def __init__(self, run_id: str, output_dir: Path | None = None):
        self.run_id = run_id
        self.output_dir = output_dir or Path("benchmark/reports") / run_id

    def generate(self, records: list[TestResultRecord]) -> str:
        """Generate recommendations markdown and write to file."""
        failures = [r for r in records if not r.score.passed]
        if not failures:
            content = f"# Recommendations from {self.run_id}\n\nAll tests passed. No recommendations.\n"
            self._write(content)
            return content

        sections = []
        sections.append(f"# Recommendations from {self.run_id}\n")
        sections.append(
            f"**{len(failures)} failures** across {len(set(f.test_id for f in failures))} tests.\n"
        )

        # Cluster by failure pattern
        patterns = self._cluster_failures(failures)

        # Generate recommendations per pattern
        priority = 1
        for pattern, items in sorted(patterns.items(), key=lambda x: -len(x[1])):
            agents_affected = set(r.agent for r in items)
            test_ids = sorted(set(r.test_id for r in items))
            severity = (
                "High" if len(items) >= 3 else "Medium" if len(items) >= 2 else "Low"
            )

            sections.append(f"## {priority}. {pattern} [{severity} Priority]\n")
            sections.append(f"**Affected tests:** {', '.join(test_ids)}")
            sections.append(f"**Agents:** {', '.join(agents_affected)}")
            sections.append("")

            # Generate specific fix
            fix = self._suggest_fix(pattern, items)
            if fix:
                sections.append(f"**Suggested fix:**\n{fix}")
            sections.append("")
            priority += 1

        # Agent-specific section
        claude_only = [r for r in failures if r.agent == "claude"]
        codex_only = [r for r in failures if r.agent == "codex"]

        if claude_only:
            sections.append("## Claude-Specific Issues\n")
            for r in claude_only:
                sections.append(f"- **{r.test_id}**: {r.score.details}")

        if codex_only:
            sections.append("\n## Codex-Specific Issues\n")
            for r in codex_only:
                sections.append(f"- **{r.test_id}**: {r.score.details}")

        # Agent meta-feedback section (from structured self-reports)
        meta_recs = self._meta_feedback_recommendations(records)
        if meta_recs:
            sections.append(meta_recs)

        content = "\n".join(sections)
        self._write(content)
        return content

    def _cluster_failures(
        self, failures: list[TestResultRecord]
    ) -> dict[str, list[TestResultRecord]]:
        """Cluster failures by root cause pattern."""
        patterns: dict[str, list[TestResultRecord]] = defaultdict(list)

        for r in failures:
            scores = r.score.scores

            # Determine primary failure reason
            if scores.get("command_correct", 1.0) < 0.5:
                patterns["Wrong or missing command"].append(r)
            elif scores.get("flags_correct", 1.0) < 0.5:
                patterns["Incorrect flags/options"].append(r)
            elif scores.get("chaining", 1.0) < 0.5:
                patterns["Chaining violation (separate bash calls)"].append(r)
            elif scores.get("skill_routing", 1.0) < 0.5:
                patterns["Wrong skill invoked"].append(r)
            elif scores.get("agent_delegation", 1.0) < 0.5:
                patterns["Wrong/no agent spawned"].append(r)
            elif scores.get("outcome_verified", 1.0) < 0.5:
                patterns["DSS outcome verification failed"].append(r)
            elif scores.get("text_content", 1.0) < 0.5:
                patterns["Missing expected output text"].append(r)
            else:
                patterns["Low efficiency / other"].append(r)

        return patterns

    def _suggest_fix(self, pattern: str, items: list[TestResultRecord]) -> str:
        """Suggest a specific fix for a failure pattern."""
        fixes = {
            "Wrong or missing command": (
                "Add explicit command examples to `skills/dku-cli/SKILL.md` for the failed scenarios.\n"
                "Consider adding a quick-reference table mapping common tasks to commands."
            ),
            "Incorrect flags/options": (
                "Add flag documentation to `skills/dku-cli/SKILL.md`.\n"
                "Ensure common flags (`-o json`, `-P PROJECT`, `--yes`, `-n N`) are shown in examples."
            ),
            "Chaining violation (separate bash calls)": (
                "Strengthen the chaining guidance in `skills/dku-cli/SKILL.md`.\n"
                "Add concrete chaining templates for common multi-step patterns:\n"
                "```\n"
                "# Create + verify\n"
                "dku dataset create X -P P && dku dataset schema X -P P\n\n"
                "# Run + check\n"
                "dku recipe run X -P P && dku job list -P P -o json | head -1\n"
                "```"
            ),
            "Wrong skill invoked": (
                "Check skill trigger keywords in the relevant `SKILL.md` frontmatter.\n"
                "Ensure trigger phrases are specific enough to avoid cross-skill confusion."
            ),
            "Wrong/no agent spawned": (
                "Check agent descriptions in `agents/*.md`.\n"
                "Ensure the agent description clearly matches the test prompt intent."
            ),
            "DSS outcome verification failed": (
                "The agent ran commands but DSS state doesn't match expectations.\n"
                "Check if the CLI command worked correctly or if the agent used wrong parameters.\n"
                "May indicate a CLI bug rather than an agent issue."
            ),
        }
        return fixes.get(pattern, "Review the specific test failures for details.")

    def _meta_feedback_recommendations(self, records: list[TestResultRecord]) -> str:
        """Generate recommendations from agent meta-feedback across all tests."""
        all_meta = [
            (r.test_id, r.trace_summary.get("meta_feedback"))
            for r in records
            if r.trace_summary.get("meta_feedback")
        ]
        if not all_meta:
            return ""

        lines = []
        lines.append("## Agent Self-Reported Feedback\n")
        lines.append(
            f"**{len(all_meta)}/{len(records)} tests** included structured meta-feedback.\n"
        )

        # Aggregate suggestions (most actionable)
        suggestions = [
            (tid, m["suggestion"])
            for tid, m in all_meta
            if m and m.get("suggestion") and m["suggestion"].lower() not in ("none", "n/a", "")
        ]
        if suggestions:
            lines.append("### Top suggestions from the agent\n")
            for tid, sug in suggestions:
                lines.append(f"- [{tid}] {sug}")
            lines.append("")

        # Missing commands
        missing = [
            (tid, m["commands_missing"])
            for tid, m in all_meta
            if m and m.get("commands_missing") and m["commands_missing"].lower() not in ("none", "n/a", "")
        ]
        if missing:
            lines.append("### Commands the agent wanted but couldn't find\n")
            for tid, cmd in missing:
                lines.append(f"- [{tid}] {cmd}")
            lines.append("")

        # Python fallbacks
        fallbacks = [
            (tid, m["python_fallback"])
            for tid, m in all_meta
            if m and m.get("python_fallback", "").lower().startswith("yes")
        ]
        if fallbacks:
            lines.append("### Python fallbacks (visual recipe should have worked)\n")
            for tid, reason in fallbacks:
                lines.append(f"- [{tid}] {reason}")
            lines.append("")

        return "\n".join(lines)

    def _write(self, content: str):
        """Write recommendations to file."""
        path = self.output_dir / "recommendations.md"
        path.write_text(content)
