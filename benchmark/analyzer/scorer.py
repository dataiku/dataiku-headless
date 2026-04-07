"""Scoring engine — evaluates agent results against scenario rubrics."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from benchmark.agents.base import AgentResult, VerificationResult
from benchmark.analyzer.trace_parser import (
    count_bash_calls_with_dku,
    extract_dku_commands,
)
from benchmark.scenarios.schema import Scenario


@dataclass
class Score:
    """Scores for a single test run."""

    scores: dict[str, float] = field(default_factory=dict)
    overall: float = 0.0
    passed: bool = False
    details: dict[str, str] = field(default_factory=dict)


class Scorer:
    """Score agent results against scenario expectations."""

    def __init__(self, pass_threshold: float = 0.7):
        self.pass_threshold = pass_threshold

    def score(
        self,
        test: Scenario,
        result: AgentResult,
        verification: VerificationResult | None = None,
    ) -> Score:
        scores: dict[str, float] = {}
        details: dict[str, str] = {}

        dku_cmds = extract_dku_commands(result)
        all_bash = " ".join(result.bash_commands)

        # 1. Command correctness
        if test.expect.commands:
            required = [e for e in test.expect.commands if e.required]
            if required:
                matched = 0
                for exp in required:
                    found = any(re.search(exp.pattern, cmd) for cmd in dku_cmds)
                    if not found:
                        # Also check full bash commands (may be chained)
                        found = bool(re.search(exp.pattern, all_bash))
                    if found:
                        matched += 1
                    else:
                        details[f"missing_cmd_{exp.pattern}"] = (
                            f"Expected pattern '{exp.pattern}' not found"
                        )
                scores["command_correct"] = matched / len(required)

        # 2. No forbidden commands
        if test.expect.no_commands:
            violations = []
            for forbidden in test.expect.no_commands:
                if any(re.search(forbidden, cmd) for cmd in dku_cmds):
                    violations.append(forbidden)
                elif re.search(forbidden, all_bash):
                    violations.append(forbidden)
            if violations:
                scores["no_forbidden"] = 0.0
                details["forbidden_commands"] = str(violations)
            else:
                scores["no_forbidden"] = 1.0

        # 3. Flag correctness
        if test.expect.commands:
            flag_scores = []
            for exp in test.expect.commands:
                if not exp.flags:
                    continue
                # Resolve {project} placeholder in expected flags
                resolved_flags = [
                    f.replace("{project}", test.project_key) if test.project_key else f
                    for f in exp.flags
                ]
                for cmd in dku_cmds:
                    if re.search(exp.pattern, cmd):
                        hits = sum(1 for f in resolved_flags if f in cmd)
                        flag_scores.append(hits / len(resolved_flags))
                        break
                # Also check full bash string
                if not flag_scores and re.search(exp.pattern, all_bash):
                    hits = sum(1 for f in resolved_flags if f in all_bash)
                    flag_scores.append(hits / len(resolved_flags))
            if flag_scores:
                scores["flags_correct"] = max(flag_scores)

        # 4. Chaining
        if test.expect.chaining is not None and test.expect.chaining:
            bash_call_count = count_bash_calls_with_dku(result)
            if bash_call_count <= 1:
                scores["chaining"] = 1.0
            elif bash_call_count <= 2:
                scores["chaining"] = 0.5
                details["chaining"] = f"Used {bash_call_count} bash calls instead of 1"
            else:
                scores["chaining"] = 0.0
                details["chaining"] = f"Used {bash_call_count} bash calls instead of 1"

        # 5. Skill routing (Claude-specific)
        if test.expect.skill_invoked:
            if result.agent != "claude":
                # Skip skill scoring for non-Claude agents
                pass
            else:
                invoked = test.expect.skill_invoked in result.skill_invocations
                scores["skill_routing"] = 1.0 if invoked else 0.0
                if not invoked:
                    details["skill_routing"] = (
                        f"Expected skill '{test.expect.skill_invoked}', "
                        f"got {result.skill_invocations or 'none'}"
                    )

        # 6. Agent delegation (Claude-specific)
        if test.expect.agent_spawned:
            if result.agent != "claude":
                pass
            else:
                spawned = any(
                    test.expect.agent_spawned in str(a) for a in result.agent_spawns
                )
                scores["agent_delegation"] = 1.0 if spawned else 0.0

        # 7. Outcome verification (real DSS)
        if verification and verification.checks:
            passed = sum(1 for c in verification.checks if c.passed)
            scores["outcome_verified"] = passed / len(verification.checks)
            for c in verification.checks:
                if not c.passed:
                    details[f"verify_fail_{c.command[:30]}"] = c.error or "Check failed"

        # 8. Text contains/excludes
        if test.expect.text_contains:
            text = result.assistant_text.lower()
            hits = sum(1 for t in test.expect.text_contains if t.lower() in text)
            scores["text_content"] = hits / len(test.expect.text_contains)

        if test.expect.text_excludes:
            text = result.assistant_text.lower()
            violations = sum(1 for t in test.expect.text_excludes if t.lower() in text)
            if violations:
                scores["text_content"] = scores.get("text_content", 1.0) * 0.5

        # 9. Efficiency — based on output tokens (reflects agent work, not context loading)
        # and number of bash calls (fewer = more decisive)
        bash_count = len(result.bash_commands)
        output_efficiency = min(1.0, 2_000 / max(result.output_tokens, 1))
        call_efficiency = 1.0 if bash_count <= 2 else 0.5 if bash_count <= 4 else 0.2
        scores["efficiency"] = (output_efficiency + call_efficiency) / 2

        # 10. Visual recipe ratio — measures use of visual vs code recipes.
        # Detected from: recipe create commands in trace + file writes of .py files.
        # Also checks no_python_recipes verification results if present.
        if test.rubric.visual_recipe_ratio is not None:
            visual_cmds = sum(
                1
                for cmd in dku_cmds
                if re.search(
                    r"dku recipe create-(join|group|stack|distinct|sort|filter|window|split|topn|pivot|sampling|geojoin|fuzzy-join)",
                    cmd,
                )
            )
            code_cmds = sum(
                1
                for cmd in dku_cmds
                if re.search(r"dku recipe create\b.*-t\s+(python|r|shell|pyspark)", cmd)
            )
            # Also count .py file writes as a signal the agent wrote Python code
            py_writes = sum(1 for f in result.file_writes if f.endswith(".py"))
            if py_writes > 0 and code_cmds == 0:
                code_cmds = (
                    1  # Agent wrote Python but we didn't catch the create command
                )

            total_recipes = visual_cmds + code_cmds
            if total_recipes > 0:
                ratio = visual_cmds / total_recipes
                scores["visual_recipe_ratio"] = ratio
                if ratio < 1.0:
                    details["visual_recipe_ratio"] = (
                        f"{visual_cmds} visual, {code_cmds} code recipes "
                        f"({ratio:.0%} visual)"
                    )
            else:
                scores["visual_recipe_ratio"] = 0.0
                details["visual_recipe_ratio"] = "No recipe create commands found"

        # Weighted aggregate — only include dimensions declared in the rubric
        # to prevent phantom dimensions (no_forbidden, agent_delegation, etc.)
        # from distorting scores with a default weight.
        rubric = test.rubric.model_dump()
        weighted = 0.0
        total_weight = 0.0
        for key, value in scores.items():
            weight = rubric.get(key)
            if weight is None:
                continue
            weighted += value * weight
            total_weight += weight

        overall = weighted / total_weight if total_weight > 0 else 0.0

        return Score(
            scores=scores,
            overall=overall,
            passed=overall >= self.pass_threshold,
            details=details,
        )
