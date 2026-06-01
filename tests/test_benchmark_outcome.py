from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest.mock import MagicMock

import yaml

from benchmark.agents.base import OutcomeCheckResult, OutcomeVerification
from benchmark.analyzer.assertions import (
    ASSERTION_REGISTRY,
    _find_alias_assignment,
    _keyed_sample_mismatches,
    _normalize_value,
    _ordered_sample_mismatches,
    _schema_signature,
    _unordered_sample_mismatches,
    _values_equal,
    check_flow_shape,
    check_output_rows,
    check_output_schema,
    check_reporter_sends_email,
    check_trigger_watches,
)
from benchmark.analyzer.scorer import OutcomeScorer
from benchmark.fixtures.generate_world import build_world
from benchmark.agents.claude import ClaudeCodeAgent
from benchmark.agents.codex import CodexAgent
from benchmark.runner import (
    _agent_class,
    _needs_dss_client,
    _resolve_agent_names,
    extract_solution_commands,
)
from benchmark.scenarios.schema import (
    Check,
    FlowNode,
    FlowRecipe,
    FlowShapeSpec,
    NewScenario,
    OutputDatasetSpec,
    load_new_scenarios,
)


def test_load_new_scenarios_reads_directory_layout(tmp_path: Path):
    task_dir = tmp_path / "data_prep" / "sample_case"
    task_dir.mkdir(parents=True)
    task_file = task_dir / "task.yaml"
    task_file.write_text(
        yaml.safe_dump(
            {
                "id": "sample_case",
                "domain": "data_prep",
                "difficulty": "easy",
                "prompt": "Do the thing",
                "checks": [
                    {
                        "run": "echo ok",
                        "assert": "output_contains",
                        "contains": "ok",
                    }
                ],
            }
        )
    )
    (task_dir / "solution.md").write_text("```bash\necho ok\n```")

    scenarios = load_new_scenarios(tmp_path)

    assert len(scenarios) == 1
    assert scenarios[0].id == "sample_case"
    assert scenarios[0].task_file == task_file
    assert scenarios[0].solution_file == task_dir / "solution.md"


def test_assertions_cover_columns_rows_and_numeric_types():
    schema_payload = (
        '[{"name":"amount","type":"double"},{"name":"region","type":"string"}]'
    )
    rows_payload = '[{"region":"East","amount":1.0},{"region":"West","amount":2.0}]'
    recipe_payload = '[{"name":"r1","type":"grouping"}]'

    passed, _ = ASSERTION_REGISTRY["has_columns"](
        schema_payload,
        0,
        Check(run="x", assert_="has_columns", columns=["amount", "region"]),
    )
    assert passed is True

    passed, _ = ASSERTION_REGISTRY["min_rows"](
        rows_payload, 0, Check(run="x", assert_="min_rows", min=2)
    )
    assert passed is True

    passed, _ = ASSERTION_REGISTRY["column_is_numeric"](
        schema_payload, 0, Check(run="x", assert_="column_is_numeric", column="amount")
    )
    assert passed is True

    passed, _ = ASSERTION_REGISTRY["no_python_recipes"](
        recipe_payload, 0, Check(run="x", assert_="no_python_recipes")
    )
    assert passed is True


def test_outcome_scorer_is_fraction_of_passing_checks():
    scenario_root = Path(__file__).resolve().parents[1] / "benchmark" / "scenarios"
    scenario = load_new_scenarios(scenario_root)[0]
    verification = OutcomeVerification(
        results=[
            OutcomeCheckResult(
                check_name="exit_code_zero", command="cmd1", passed=True
            ),
            OutcomeCheckResult(
                check_name="min_rows",
                command="cmd2",
                passed=False,
                message="too few rows",
            ),
            OutcomeCheckResult(
                check_name="column_is_numeric", command="cmd3", passed=True
            ),
            OutcomeCheckResult(check_name="has_columns", command="cmd4", passed=True),
        ],
    )

    score = OutcomeScorer().score(scenario, verification)

    assert score.score == 0.75
    assert score.passed is False
    assert score.gap_type == scenario.expected_gap
    assert "min_rows:cmd2" in score.details


def test_outcome_scorer_passes_only_when_all_checks_pass():
    scenario_root = Path(__file__).resolve().parents[1] / "benchmark" / "scenarios"
    scenario = load_new_scenarios(scenario_root)[0]

    all_pass = OutcomeVerification(
        results=[
            OutcomeCheckResult(check_name="a", command="c1", passed=True),
            OutcomeCheckResult(check_name="b", command="c2", passed=True),
        ]
    )
    score = OutcomeScorer().score(scenario, all_pass)
    assert score.score == 1.0
    assert score.passed is True

    none_pass = OutcomeVerification(
        results=[OutcomeCheckResult(check_name="a", command="c1", passed=False)]
    )
    score = OutcomeScorer().score(scenario, none_pass)
    assert score.score == 0.0
    assert score.passed is False


def test_extract_solution_commands_reads_first_bash_block(tmp_path: Path):
    solution_file = tmp_path / "solution.md"
    solution_file.write_text(
        "# Solution\n\n```bash\n# comment\nfirst command\nsecond command\n```\n"
    )

    commands = extract_solution_commands(solution_file)

    assert commands == ["first command", "second command"]


def test_build_world_has_expected_row_counts():
    world = build_world()

    assert len(world["orders"]) == 500
    assert len(world["customers"]) == 100
    assert len(world["products"]) == 50
    assert len(world["events"]) == 1000
    assert len(world["users"]) == 200


def test_resolve_agent_names_from_defaults():
    config = {
        "runner": {"profiles": ["claude_dku"]},
        "profiles": {"claude_dku": {"model": "test"}},
    }
    args = argparse.Namespace(profile=None)
    assert _resolve_agent_names(args, config) == ["claude_dku"]


def test_resolve_agent_names_from_flag():
    config = {"runner": {"profiles": ["default_profile"]}}
    assert _resolve_agent_names(argparse.Namespace(profile="p1,p2"), config) == [
        "p1",
        "p2",
    ]


def test_agent_class_factory_maps_vendor():
    config = {
        "profiles": {
            "c": {"vendor": "codex", "model": "m"},
            "a": {"vendor": "claude", "model": "m"},
        }
    }
    assert _agent_class(config, "c") is CodexAgent
    assert _agent_class(config, "a") is ClaudeCodeAgent


def test_mcp_profile_is_dku_stripped_and_creds_withheld():
    config = {
        "runner": {},
        "profiles": {
            "codex_mcp": {
                "vendor": "codex",
                "model": "m",
                "max_turns": 5,
                "mcp_servers": {"dataiku": {"command": "uv", "args": []}},
            }
        },
    }
    agent = CodexAgent(config, "codex_mcp")
    assert agent.has_mcp is True
    # MCP implies the dku CLI is never on PATH for that profile.
    assert agent.strip_dku is True


def test_coherence_flags_cross_surface_use():
    from benchmark.analyzer import coherence

    # vanilla legitimately uses raw DSSClient — coherent.
    assert coherence.check("codex_vanilla", ["python -c 'DSSClient(u, k)'"], []) == []
    # mcp profile must not bypass MCP with raw API.
    assert coherence.check("codex_mcp", ["python -c 'DSSClient(u, k)'"], ["dataiku.x"])
    # mcp profile using MCP only — coherent.
    assert coherence.check("codex_mcp", ["ls /work"], ["dataiku.x"]) == []
    # dku profile reaching for MCP — incoherent.
    assert coherence.check("codex_dku", ["dku dataset list"], ["dataiku.x"])
    # any profile reading a baked solution — integrity leak.
    assert coherence.check("codex_dku", ["cat /opt/bench/solution.md"], [])


def test_dku_skills_profile_grants_only_listed_skills():
    config = {
        "runner": {},
        "profiles": {
            "codex_dku_skills": {
                "vendor": "codex",
                "model": "m",
                "max_turns": 5,
                "skills": ["dku-cli", "dataiku"],
            }
        },
    }
    agent = CodexAgent(config, "codex_dku_skills")
    _, names = agent._resolve_skills()
    assert names == ["dku-cli", "dataiku"]
    assert agent.has_mcp is False
    assert agent.strip_dku is False


# ---------------------------------------------------------------------------
# Phase 1 — Data-Level Verification
# ---------------------------------------------------------------------------


class TestNormalizeValue:
    def test_keeps_numbers(self):
        assert _normalize_value(42) == 42
        assert _normalize_value(3.14) == 3.14

    def test_parses_numeric_strings(self):
        assert _normalize_value("42") == 42
        assert _normalize_value("3.14") == 3.14

    def test_strips_strings(self):
        assert _normalize_value("  hello  ") == "hello"


class TestOrderedSampleMismatches:
    def test_exact_match(self):
        actual = [{"a": 1, "b": 2}, {"a": 3, "b": 4}]
        expected = [{"a": 1, "b": 2}, {"a": 3, "b": 4}]
        assert _ordered_sample_mismatches(actual, expected) == []

    def test_reports_mismatch_row(self):
        actual = [{"a": 1, "b": 2}]
        expected = [{"a": 1, "b": 99}]
        result = _ordered_sample_mismatches(actual, expected)
        assert len(result) == 1
        assert "Row 0 col 'b'" in result[0]

    def test_reports_extra_row(self):
        actual = [{"a": 1}, {"a": 2}]
        expected = [{"a": 1}]
        result = _ordered_sample_mismatches(actual, expected)
        assert any("expected <end>" in r for r in result)

    def test_reports_missing_row(self):
        actual = [{"a": 1}]
        expected = [{"a": 1}, {"a": 2}]
        result = _ordered_sample_mismatches(actual, expected)
        assert any("got <end of data>" in r for r in result)

    def test_respects_max_reported(self):
        actual = []
        expected = [{"a": i} for i in range(10)]
        result = _ordered_sample_mismatches(actual, expected, max_reported=3)
        assert len(result) == 3


class TestUnorderedSampleMismatches:
    def test_exact_match(self):
        actual = [{"a": 1}, {"a": 2}]
        expected = [{"a": 2}, {"a": 1}]
        assert _unordered_sample_mismatches(actual, expected) == []

    def test_reports_missing_row(self):
        actual = [{"a": 1}]
        expected = [{"a": 1}, {"a": 2}]
        result = _unordered_sample_mismatches(actual, expected)
        assert len(result) == 1
        assert "not found" in result[0]


class TestKeyedSampleMismatches:
    def test_exact_match(self):
        actual = [{"id": 1, "v": 10}, {"id": 2, "v": 20}]
        expected = [{"id": 1, "v": 10}, {"id": 2, "v": 20}]
        assert _keyed_sample_mismatches(actual, expected, ["id"]) == []

    def test_reports_missing_key(self):
        actual = [{"id": 1, "v": 10}]
        expected = [{"id": 1, "v": 10}, {"id": 2, "v": 20}]
        result = _keyed_sample_mismatches(actual, expected, ["id"])
        assert len(result) == 1
        assert "not found" in result[0]

    def test_reports_value_mismatch(self):
        actual = [{"id": 1, "v": 99}]
        expected = [{"id": 1, "v": 10}]
        result = _keyed_sample_mismatches(actual, expected, ["id"])
        assert len(result) == 1
        assert "expected 10" in result[0]


class TestCheckOutputSchema:
    def test_missing_context_returns_false(self):
        check = Check(run="x", assert_="output_schema", columns=["ds1"])
        passed, msg = check_output_schema("", 0, check, {})
        assert passed is False
        assert "No DSS client" in msg

    def test_missing_dataset_in_expected_outputs(self):
        client = MagicMock()
        ctx = {"client": client, "project_key": "PROJ", "expected_outputs": {}}
        check = Check(run="x", assert_="output_schema", columns=["ds1"])
        passed, _ = check_output_schema("", 0, check, ctx)
        assert passed is False

    def test_schema_matches(self):
        client = MagicMock()
        proj = MagicMock()
        ds = MagicMock()
        ds.get_definition.return_value = {
            "schema": {
                "columns": [
                    {"name": "a", "type": "string"},
                    {"name": "b", "type": "int"},
                ]
            }
        }
        proj.get_dataset.return_value = ds
        client.get_project.return_value = proj

        expected = {
            "ds1": OutputDatasetSpec(
                schema_=[{"name": "a", "type": "string"}, {"name": "b", "type": "int"}],
            )
        }
        ctx = {"client": client, "project_key": "PROJ", "expected_outputs": expected}
        check = Check(run="x", assert_="output_schema", columns=["ds1"])
        passed, msg = check_output_schema("", 0, check, ctx)
        assert passed is True, msg

    def test_schema_mismatch(self):
        client = MagicMock()
        proj = MagicMock()
        ds = MagicMock()
        ds.get_definition.return_value = {
            "schema": {"columns": [{"name": "a", "type": "string"}]}
        }
        proj.get_dataset.return_value = ds
        client.get_project.return_value = proj

        expected = {
            "ds1": OutputDatasetSpec(
                schema_=[{"name": "a", "type": "string"}, {"name": "b", "type": "int"}],
            )
        }
        ctx = {"client": client, "project_key": "PROJ", "expected_outputs": expected}
        check = Check(run="x", assert_="output_schema", columns=["ds1"])
        passed, msg = check_output_schema("", 0, check, ctx)
        assert passed is False
        assert "Missing column" in msg


class TestCheckOutputRows:
    def test_missing_context_returns_false(self):
        check = Check(run="x", assert_="output_rows", columns=["ds1"])
        passed, msg = check_output_rows("", 0, check, {})
        assert passed is False
        assert "No DSS client" in msg

    def test_row_count_mismatch(self):
        client = MagicMock()
        proj = MagicMock()
        ds = MagicMock()
        # 2 actual rows
        ds.iter_rows.return_value = [{"a": 1}, {"a": 2}]
        ds.get_definition.return_value = {
            "schema": {"columns": [{"name": "a", "type": "int"}]}
        }
        proj.get_dataset.return_value = ds
        client.get_project.return_value = proj

        expected = {
            "ds1": OutputDatasetSpec(
                schema_=[{"name": "a", "type": "int"}],
                row_count=3,
                data=[{"a": 1}, {"a": 2}, {"a": 3}],
            )
        }
        ctx = {"client": client, "project_key": "PROJ", "expected_outputs": expected}
        check = Check(run="x", assert_="output_rows", columns=["ds1"])
        passed, msg = check_output_rows("", 0, check, ctx)
        assert passed is False
        assert "expected 3 rows" in msg

    def test_data_matches(self):
        client = MagicMock()
        proj = MagicMock()
        ds = MagicMock()
        ds.iter_rows.return_value = [{"a": 1, "b": "x"}, {"a": 2, "b": "y"}]
        ds.get_definition.return_value = {
            "schema": {
                "columns": [
                    {"name": "a", "type": "int"},
                    {"name": "b", "type": "string"},
                ]
            }
        }
        proj.get_dataset.return_value = ds
        client.get_project.return_value = proj

        expected = {
            "ds1": OutputDatasetSpec(
                schema_=[{"name": "a", "type": "int"}, {"name": "b", "type": "string"}],
                row_count=2,
                data=[{"a": 1, "b": "x"}, {"a": 2, "b": "y"}],
            )
        }
        ctx = {"client": client, "project_key": "PROJ", "expected_outputs": expected}
        check = Check(run="x", assert_="output_rows", columns=["ds1"])
        passed, msg = check_output_rows("", 0, check, ctx)
        assert passed is True, msg

    def test_data_mismatch_reported(self):
        client = MagicMock()
        proj = MagicMock()
        ds = MagicMock()
        ds.iter_rows.return_value = [{"a": 1, "b": "x"}]
        ds.get_definition.return_value = {
            "schema": {
                "columns": [
                    {"name": "a", "type": "int"},
                    {"name": "b", "type": "string"},
                ]
            }
        }
        proj.get_dataset.return_value = ds
        client.get_project.return_value = proj

        expected = {
            "ds1": OutputDatasetSpec(
                schema_=[{"name": "a", "type": "int"}, {"name": "b", "type": "string"}],
                data=[{"a": 99, "b": "x"}],
            )
        }
        ctx = {"client": client, "project_key": "PROJ", "expected_outputs": expected}
        check = Check(run="x", assert_="output_rows", columns=["ds1"])
        passed, msg = check_output_rows("", 0, check, ctx)
        assert passed is False
        assert "Data mismatch" in msg


# ---------------------------------------------------------------------------
# Phase 2 — Flow-Shape Matching
# ---------------------------------------------------------------------------


def _make_mock_client(
    project_key: str, datasets: list[dict], recipes: list[dict]
) -> MagicMock:
    """Build a mock DSS client with the given datasets and recipes."""
    client = MagicMock()
    proj = MagicMock()
    proj.list_datasets.return_value = datasets

    def _get_dataset(name: str):
        ds = MagicMock()
        for d in datasets:
            if d["name"] == name:
                ds.get_definition.return_value = {
                    "schema": {"columns": d.get("columns", [])}
                }
                return ds
        return ds

    proj.get_dataset.side_effect = _get_dataset
    proj.list_recipes.return_value = recipes

    flow = MagicMock()
    graph = MagicMock()
    graph.get = lambda k, d=None: d
    graph.nodes = {}
    flow.get_graph.return_value = graph
    proj.get_flow.return_value = flow

    client.get_project.return_value = proj
    return client


class TestSchemaSignature:
    def test_from_columns(self):
        cols = [{"name": "a", "type": "string"}, {"name": "b", "type": "int"}]
        sig = _schema_signature(cols)
        assert ("a", "string") in sig
        assert ("b", "int") in sig

    def test_empty_columns(self):
        assert _schema_signature([]) == frozenset()


class TestFindAliasAssignment:
    def test_simple_match(self):
        expected_nodes = {
            "source": {"schema_": [{"name": "a", "type": "string"}]},
            "output": {"schema_": [{"name": "b", "type": "int"}]},
        }
        expected_recipes = [
            {"type": "Filter", "inputs": ["source"], "outputs": ["output"]}
        ]
        actual_datasets = {
            "ds_a": {"columns": [{"name": "a", "type": "string"}]},
            "ds_b": {"columns": [{"name": "b", "type": "int"}]},
        }

        # Recipe connectivity will fail without recipe graph edges — minimal test
        actual_recipes = {
            "r1": {
                "name": "r1",
                "type": "Filter",
                "inputs": ["ds_a"],
                "outputs": ["ds_b"],
            }
        }

        result = _find_alias_assignment(
            expected_nodes, expected_recipes, actual_datasets, actual_recipes
        )
        assert result is not None
        assert result["source"] == "ds_a"
        assert result["output"] == "ds_b"

    def test_no_match_returns_none(self):
        expected_nodes = {"output": {"schema_": [{"name": "x", "type": "string"}]}}
        expected_recipes = []
        actual_datasets = {}
        actual_recipes = {}

        result = _find_alias_assignment(
            expected_nodes, expected_recipes, actual_datasets, actual_recipes
        )
        assert result is None


class TestCheckFlowShape:
    def test_missing_context_returns_false(self):
        check = Check(run="x", assert_="flow_shape")
        passed, msg = check_flow_shape("", 0, check, {})
        assert passed is False
        assert "No DSS client" in msg

    def test_no_expected_flow_returns_false(self):
        client = MagicMock()
        ctx = {"client": client, "project_key": "PROJ"}
        check = Check(run="x", assert_="flow_shape")
        passed, msg = check_flow_shape("", 0, check, ctx)
        assert passed is False
        assert "No expected_flow" in msg

    def test_matching_flow(self):
        datasets = [
            {"name": "src", "columns": [{"name": "a", "type": "string"}]},
            {"name": "out", "columns": [{"name": "b", "type": "int"}]},
        ]
        recipes = [
            {"name": "r1", "type": "Filter"},
        ]
        client = _make_mock_client("PROJ", datasets, recipes)

        # Wire up the flow graph
        flow = client.get_project("PROJ").get_flow()
        graph = flow.get_graph()
        graph.nodes = {
            "src": {
                "type": "DATASET",
                "ref": "src",
                "predecessors": [],
                "successors": ["r1"],
            },
            "r1": {
                "type": "RUNNABLE_RECIPE",
                "ref": "r1",
                "predecessors": ["src"],
                "successors": ["out"],
            },
            "out": {
                "type": "DATASET",
                "ref": "out",
                "predecessors": ["r1"],
                "successors": [],
            },
        }

        expected_flow = FlowShapeSpec(
            nodes={
                "source": FlowNode(
                    type="source",
                    schema_=[{"name": "a", "type": "string"}],
                ),
                "output": FlowNode(
                    type="output",
                    schema_=[{"name": "b", "type": "int"}],
                ),
            },
            recipes=[
                FlowRecipe(type="Filter", inputs=["source"], outputs=["output"]),
            ],
            exact_recipe_count=True,
        )

        ctx = {"client": client, "project_key": "PROJ", "expected_flow": expected_flow}
        check = Check(run="x", assert_="flow_shape")
        passed, msg = check_flow_shape("", 0, check, ctx)
        assert passed is True, msg


# ---------------------------------------------------------------------------
# Schema helpers
# ---------------------------------------------------------------------------


class TestScenarioWithNewFields:
    """Test that NewScenario loads expected_outputs and expected_flow from YAML."""

    def test_expected_outputs_loaded(self, tmp_path: Path):
        task_dir = tmp_path / "data_prep" / "test_scenario"
        task_dir.mkdir(parents=True)
        task_file = task_dir / "task.yaml"
        task_file.write_text(
            yaml.safe_dump(
                {
                    "id": "test_scenario",
                    "domain": "data_prep",
                    "difficulty": "easy",
                    "prompt": "Do it",
                    "expected_outputs": {
                        "result": {
                            "schema": [{"name": "a", "type": "string"}],
                            "row_count": 5,
                            "data": [{"a": "hello"}, {"a": "world"}],
                        }
                    },
                }
            )
        )
        scenarios = load_new_scenarios(tmp_path)
        assert len(scenarios) == 1
        s = scenarios[0]
        assert "result" in s.expected_outputs
        assert s.expected_outputs["result"].schema_[0].name == "a"
        assert s.expected_outputs["result"].row_count == 5
        assert len(s.expected_outputs["result"].data) == 2

    def test_expected_flow_loaded(self, tmp_path: Path):
        task_dir = tmp_path / "data_prep" / "test_scenario"
        task_dir.mkdir(parents=True)
        task_file = task_dir / "task.yaml"
        task_file.write_text(
            yaml.safe_dump(
                {
                    "id": "test_scenario",
                    "domain": "data_prep",
                    "difficulty": "easy",
                    "prompt": "Do it",
                    "expected_flow": {
                        "nodes": {
                            "src": {
                                "type": "source",
                                "schema": [{"name": "a", "type": "string"}],
                            },
                            "out": {
                                "type": "output",
                                "schema": [{"name": "b", "type": "int"}],
                            },
                        },
                        "recipes": [
                            {"type": "Filter", "inputs": ["src"], "outputs": ["out"]},
                        ],
                        "exact_recipe_count": True,
                    },
                }
            )
        )
        scenarios = load_new_scenarios(tmp_path)
        assert len(scenarios) == 1
        s = scenarios[0]
        assert s.expected_flow is not None
        assert "src" in s.expected_flow.nodes
        assert s.expected_flow.nodes["src"].type == "source"
        assert len(s.expected_flow.recipes) == 1
        assert s.expected_flow.recipes[0].type == "Filter"

    def test_optional_fields_default(self, tmp_path: Path):
        task_dir = tmp_path / "data_prep" / "test_scenario"
        task_dir.mkdir(parents=True)
        task_file = task_dir / "task.yaml"
        task_file.write_text(
            yaml.safe_dump(
                {
                    "id": "test_scenario",
                    "domain": "data_prep",
                    "difficulty": "easy",
                    "prompt": "Do it",
                }
            )
        )
        scenarios = load_new_scenarios(tmp_path)
        assert len(scenarios) == 1
        s = scenarios[0]
        assert s.expected_outputs == {}
        assert s.expected_flow is None


class TestNeedsDSSClient:
    def test_deterministic_scenario_needs_client(self):
        scenario = NewScenario(
            id="test",
            domain="d",
            difficulty="easy",
            prompt="p",
            expected_outputs={"ds": OutputDatasetSpec()},
        )
        assert _needs_dss_client(scenario) is True

    def test_plain_scenario_does_not(self):
        scenario = NewScenario(id="test", domain="d", difficulty="easy", prompt="p")
        assert _needs_dss_client(scenario) is False


# ---------------------------------------------------------------------------
# Float tolerance + row-count enforcement
# ---------------------------------------------------------------------------


class TestValuesEqual:
    def test_float_within_tolerance(self):
        assert _values_equal(11574.7, 11574.700001) is True

    def test_float_string_vs_number(self):
        assert _values_equal("11574.7", 11574.7) is True

    def test_int_equals_float(self):
        assert _values_equal(47, 47.0) is True

    def test_distinct_floats_differ(self):
        assert _values_equal(11574.7, 11575.9) is False

    def test_strings_compared_exactly(self):
        assert _values_equal("East", "East") is True
        assert _values_equal("East", "West") is False


def _mock_rows_client(rows: list[dict]) -> MagicMock:
    client = MagicMock()
    proj = MagicMock()
    ds = MagicMock()
    ds.iter_rows.return_value = rows
    ds.get_definition.return_value = {"schema": {"columns": []}}
    proj.get_dataset.return_value = ds
    client.get_project.return_value = proj
    return client


class TestRowCountEnforcedWithoutSampleData:
    """row_count must gate even when expected_outputs has no `data` block (bug 1)."""

    def _ctx(self, rows):
        return {
            "client": _mock_rows_client(rows),
            "project_key": "PROJ",
            "expected_outputs": {
                "ds1": OutputDatasetSpec(row_count=3)  # no data rows
            },
        }

    def test_passes_on_matching_count(self):
        check = Check(run="x", assert_="output_rows", columns=["ds1"])
        passed, msg = check_output_rows("", 0, check, self._ctx([{"a": 1}] * 3))
        assert passed is True, msg

    def test_fails_on_count_mismatch(self):
        check = Check(run="x", assert_="output_rows", columns=["ds1"])
        passed, msg = check_output_rows("", 0, check, self._ctx([{"a": 1}] * 5))
        assert passed is False
        assert "expected 3 rows" in msg

    def test_float_tolerant_data_match(self):
        ctx = {
            "client": _mock_rows_client(
                [{"region": "East", "amount_sum": 11262.180001}]
            ),
            "project_key": "PROJ",
            "expected_outputs": {
                "ds1": OutputDatasetSpec(
                    row_count=1, data=[{"region": "East", "amount_sum": 11262.18}]
                )
            },
        }
        check = Check(run="x", assert_="output_rows", columns=["ds1"])
        passed, msg = check_output_rows("", 0, check, ctx)
        assert passed is True, msg


# ---------------------------------------------------------------------------
# Scoped scenario-wiring assertions
# ---------------------------------------------------------------------------


class TestTriggerWatches:
    def _defn(self, item_id):
        return json.dumps(
            {
                "triggers": [
                    {
                        "type": "ds_modified",
                        "params": {"watches": [{"type": "DATASET", "itemId": item_id}]},
                    }
                ]
            }
        )

    def test_matches_watched_dataset(self):
        check = Check(
            run="x",
            assert_="trigger_watches",
            trigger_type="ds_modified",
            dataset="orders",
        )
        passed, _ = check_trigger_watches(self._defn("orders"), 0, check)
        assert passed is True

    def test_rejects_wrong_dataset(self):
        check = Check(
            run="x",
            assert_="trigger_watches",
            trigger_type="ds_modified",
            dataset="orders",
        )
        passed, msg = check_trigger_watches(self._defn("customers"), 0, check)
        assert passed is False
        assert "watching dataset 'orders'" in msg

    def test_not_fooled_by_dataset_name_in_step(self):
        # 'orders' appears in a step name but no trigger watches it.
        defn = json.dumps(
            {
                "triggers": [],
                "params": {"steps": [{"name": "build orders"}]},
            }
        )
        check = Check(
            run="x",
            assert_="trigger_watches",
            trigger_type="ds_modified",
            dataset="orders",
        )
        passed, _ = check_trigger_watches(defn, 0, check)
        assert passed is False


class TestReporterSendsEmail:
    def _defn(self, email):
        return json.dumps(
            {"reporters": [{"messaging": {"type": "mail-scenario", "to": email}}]}
        )

    def test_matches_reporter_email(self):
        check = Check(
            run="x",
            assert_="reporter_sends_email",
            reporter_type="mail-scenario",
            email="alerts@example.com",
        )
        passed, _ = check_reporter_sends_email(
            self._defn("alerts@example.com"), 0, check
        )
        assert passed is True

    def test_rejects_missing_email(self):
        check = Check(
            run="x",
            assert_="reporter_sends_email",
            reporter_type="mail-scenario",
            email="alerts@example.com",
        )
        passed, msg = check_reporter_sends_email(
            self._defn("other@example.com"), 0, check
        )
        assert passed is False
        assert "reporter sending to 'alerts@example.com'" in msg
