"""Tests for scenario commands."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from dku_cli.main import app
from dku_cli.output import set_quiet

runner = CliRunner()


@pytest.fixture(autouse=True)
def _reset_quiet():
    """Ensure quiet mode is off before each test (global state leak fix)."""
    set_quiet(False)
    yield
    set_quiet(False)


# ── Existing tests ──────────────────────────────────────────────────────


def test_scenario_list(patch_client):
    result = runner.invoke(app, ["scenario", "list", "--project", "PROJ1"])
    assert result.exit_code == 0


def test_scenario_list_json(patch_client):
    result = runner.invoke(app, ["scenario", "list", "--project", "PROJ1", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert isinstance(parsed, list)


def test_scenario_run(patch_client):
    result = runner.invoke(app, ["scenario", "run", "scen1", "--project", "PROJ1"])
    assert result.exit_code == 0


def test_scenario_abort(patch_client):
    result = runner.invoke(app, ["scenario", "abort", "scen1", "--project", "PROJ1"])
    assert result.exit_code == 0


def test_scenario_status(patch_client):
    result = runner.invoke(app, ["scenario", "status", "scen1", "--project", "PROJ1"])
    assert result.exit_code == 0


def test_scenario_status_json(patch_client):
    result = runner.invoke(app, ["scenario", "status", "scen1", "--project", "PROJ1", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["run_id"] == "run1"


# ── Phase 4: create, delete, get/set-definition ────────────────────────


def test_scenario_create(patch_client):
    result = runner.invoke(app, ["scenario", "create", "My New Scenario", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "Created scenario" in result.output
    assert "new_scen" in result.output
    proj = patch_client.get_project("PROJ1")
    proj.create_scenario.assert_called_once_with(name="My New Scenario", type="step_based")


def test_scenario_create_with_definition(patch_client):
    defn = json.dumps({"steps": [{"type": "build_flowitem"}]})
    result = runner.invoke(
        app,
        ["scenario", "create", "Custom Scenario", "--project", "PROJ1", "--definition", defn],
    )
    assert result.exit_code == 0
    assert "Created scenario" in result.output
    proj = patch_client.get_project("PROJ1")
    call_kwargs = proj.create_scenario.call_args[1]
    assert call_kwargs["name"] == "Custom Scenario"
    assert call_kwargs["type"] == "step_based"
    assert call_kwargs["definition"] == {"steps": [{"type": "build_flowitem"}]}


def test_scenario_create_custom_type(patch_client):
    result = runner.invoke(
        app,
        ["scenario", "create", "Custom Type", "--project", "PROJ1", "--type", "custom_python"],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    call_kwargs = proj.create_scenario.call_args[1]
    assert call_kwargs["type"] == "custom_python"


def test_scenario_delete(patch_client):
    result = runner.invoke(app, ["scenario", "delete", "scen1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "Deleted scenario" in result.output
    proj = patch_client.get_project("PROJ1")
    scenario = proj.get_scenario("scen1")
    scenario.delete.assert_called_once()


def test_scenario_get_definition(patch_client):
    result = runner.invoke(app, ["scenario", "get-definition", "scen1", "--project", "PROJ1"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["type"] == "step_based"
    assert parsed["name"] == "Build All"
    assert parsed["params"] == {}


def test_scenario_get_definition_with_output_flag(patch_client):
    result = runner.invoke(app, ["scenario", "get-definition", "scen1", "--project", "PROJ1", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["name"] == "Build All"


def test_scenario_set_definition(patch_client):
    new_def = json.dumps({"type": "step_based", "name": "Updated", "params": {"x": 1}})
    result = runner.invoke(
        app,
        ["scenario", "set-definition", "scen1", "--project", "PROJ1", "--definition", new_def],
    )
    assert result.exit_code == 0
    assert "Updated definition" in result.output
    proj = patch_client.get_project("PROJ1")
    scenario = proj.get_scenario("scen1")
    scenario.set_definition.assert_called_once_with(
        {"type": "step_based", "name": "Updated", "params": {"x": 1}}
    )


def test_scenario_set_definition_from_file(tmp_path, patch_client):
    defn_file = tmp_path / "def.json"
    defn_file.write_text(json.dumps({"type": "step_based", "name": "FromFile"}))
    result = runner.invoke(
        app,
        ["scenario", "set-definition", "scen1", "--project", "PROJ1", "--definition", f"@{defn_file}"],
    )
    assert result.exit_code == 0
    assert "Updated definition" in result.output
    proj = patch_client.get_project("PROJ1")
    scenario = proj.get_scenario("scen1")
    scenario.set_definition.assert_called_once_with({"type": "step_based", "name": "FromFile"})
