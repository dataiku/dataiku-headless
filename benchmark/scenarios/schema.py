"""Pydantic models for benchmark test scenarios."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field


class ColumnSpec(BaseModel):
    name: str
    type: str


class OutputDatasetSpec(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schema_: list[ColumnSpec] = Field(default_factory=list, alias="schema")
    row_count: int = 0
    data: list[dict] = Field(default_factory=list)


class FlowNode(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schema_: list[ColumnSpec] = Field(default_factory=list, alias="schema")
    type: Literal["source", "intermediate", "output"] = "intermediate"


class FlowRecipe(BaseModel):
    type: str
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    config: dict = Field(default_factory=dict)


class FlowShapeSpec(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    nodes: dict[str, FlowNode] = Field(default_factory=dict)
    recipes: list[FlowRecipe] = Field(default_factory=list)
    exact_recipe_count: bool = True
    exact_dataset_count: bool = False


class Check(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    run: str
    assert_: str = Field(alias="assert")
    columns: list[str] = Field(default_factory=list)
    min: int = 0
    column: str = ""
    contains: str = ""
    dataset: str = ""
    trigger_type: str = ""
    reporter_type: str = ""
    email: str = ""


class NewScenario(BaseModel):
    id: str
    domain: str
    difficulty: Literal["easy", "medium", "hard"]
    expected_gap: Literal["none", "tool_gap", "capability_gap"] = "none"
    # Per-scenario overrides for the difficulty-tiered runner defaults. Only set
    # for genuine outliers; otherwise the tier for `difficulty` applies.
    timeout: int | None = None
    max_turns: int | None = None
    fixtures: list[str] = Field(default_factory=list)
    setup: list[str] = Field(default_factory=list)
    initial_checks: list[Check] = Field(default_factory=list)
    prompt: str
    validation_gaps: list[str] = Field(default_factory=list)
    checks: list[Check] = Field(default_factory=list)
    project_key: str | None = None
    expected_outputs: dict[str, OutputDatasetSpec] = Field(default_factory=dict)
    expected_flow: FlowShapeSpec | None = None
    task_file: Path | None = None
    solution_file: Path | None = None


def load_new_scenarios(path: Path) -> list[NewScenario]:
    scenarios: list[NewScenario] = []
    for task_file in sorted(path.glob("*/*/task.yaml")):
        with open(task_file) as f:
            data = yaml.safe_load(f) or {}
        scenario = NewScenario(**data)
        scenario.task_file = task_file
        solution_file = task_file.with_name("solution.md")
        if solution_file.exists():
            scenario.solution_file = solution_file
        scenarios.append(scenario)
    return scenarios
