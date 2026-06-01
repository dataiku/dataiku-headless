"""Scoring engine — flat fractional grading."""

from __future__ import annotations

from dataclasses import dataclass, field

from benchmark.agents.base import OutcomeVerification
from benchmark.scenarios.schema import NewScenario


@dataclass
class Score:
    score: float = 0.0
    gap_type: str = "none"
    details: dict[str, str] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        """Strict success: every check passed."""
        return self.score >= 1.0


class OutcomeScorer:
    """Flat fractional scorer: score = checks passed / total checks."""

    def score(
        self,
        scenario: NewScenario,
        verification: OutcomeVerification,
    ) -> Score:
        results = verification.results
        n_total = len(results)
        n_passed = sum(1 for r in results if r.passed)

        details: dict[str, str] = {}
        for r in results:
            if not r.passed:
                details[f"{r.check_name}:{r.command[:40]}"] = (
                    r.message or f"{r.check_name} failed"
                )

        return Score(
            score=n_passed / n_total if n_total else 0.0,
            gap_type=scenario.expected_gap,
            details=details,
        )
