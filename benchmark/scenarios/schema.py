"""Pydantic models for benchmark test scenarios."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field


class ExpectedCommand(BaseModel):
    """An expected dku command in the agent trace."""

    pattern: str
    required: bool = True
    flags: list[str] = Field(default_factory=list)


class VerifyStep(BaseModel):
    """A verification step run against real DSS after the test."""

    command: str
    expect_status: int = 0
    expect_contains: Optional[str] = None
    expect_json: Optional[dict] = None


class Expectations(BaseModel):
    """What we expect from the agent run."""

    commands: list[ExpectedCommand] = Field(default_factory=list)
    no_commands: list[str] = Field(default_factory=list)
    skill_invoked: Optional[str] = None
    agent_spawned: Optional[str] = None
    chaining: Optional[bool] = None
    verify: list[VerifyStep] = Field(default_factory=list)
    text_contains: list[str] = Field(default_factory=list)
    text_excludes: list[str] = Field(default_factory=list)


class Rubric(BaseModel):
    """Scoring weights for a test."""

    command_correct: float = 1.0
    flags_correct: float = 1.0
    chaining: float = 1.0
    skill_routing: float = 1.0
    outcome_verified: float = 1.0
    efficiency: float = 0.5


class Scenario(BaseModel):
    """A single benchmark test scenario."""

    id: str
    tier: int
    category: str
    prompt: str
    needs_project: bool = False
    timeout: Optional[int] = None
    expect: Expectations = Field(default_factory=Expectations)
    rubric: Rubric = Field(default_factory=Rubric)

    # Set at runtime
    project_key: Optional[str] = None


class ScenarioFile(BaseModel):
    """A YAML file containing multiple test scenarios."""

    tests: list[Scenario]


def load_scenarios(path: Path) -> list[Scenario]:
    """Load all scenario YAML files from a directory."""
    scenarios = []
    for yaml_file in sorted(path.glob("*.yaml")):
        with open(yaml_file) as f:
            data = yaml.safe_load(f)
        if data and "tests" in data:
            sf = ScenarioFile(**data)
            scenarios.extend(sf.tests)
    return scenarios
