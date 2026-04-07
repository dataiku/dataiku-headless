"""Tests for scenario commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


# ── Existing tests ──────────────────────────────────────────────────────


def test_scenario_list(patch_client):
    result = runner.invoke(app, ["scenario", "list", "--project", "PROJ1"])
    assert result.exit_code == 0


def test_scenario_list_json(patch_client):
    result = runner.invoke(
        app, ["scenario", "list", "--project", "PROJ1", "-o", "json"]
    )
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
    result = runner.invoke(
        app, ["scenario", "status", "scen1", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["run_id"] == "run1"


# ── Phase 4: create, delete, get/set-definition ────────────────────────


def test_scenario_create(patch_client):
    result = runner.invoke(
        app, ["scenario", "create", "My New Scenario", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "Created scenario" in result.output
    assert "new_scen" in result.output
    proj = patch_client.get_project("PROJ1")
    proj.create_scenario.assert_called_once_with(
        scenario_name="My New Scenario", type="step_based"
    )


def test_scenario_create_with_definition(patch_client):
    defn = json.dumps({"steps": [{"type": "build_flowitem"}]})
    result = runner.invoke(
        app,
        [
            "scenario",
            "create",
            "Custom Scenario",
            "--project",
            "PROJ1",
            "--definition",
            defn,
        ],
    )
    assert result.exit_code == 0
    assert "Created scenario" in result.output
    proj = patch_client.get_project("PROJ1")
    call_kwargs = proj.create_scenario.call_args[1]
    assert call_kwargs["scenario_name"] == "Custom Scenario"
    assert call_kwargs["type"] == "step_based"
    assert call_kwargs["definition"] == {"steps": [{"type": "build_flowitem"}]}


def test_scenario_create_custom_type(patch_client):
    result = runner.invoke(
        app,
        [
            "scenario",
            "create",
            "Custom Type",
            "--project",
            "PROJ1",
            "--type",
            "custom_python",
        ],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    call_kwargs = proj.create_scenario.call_args[1]
    assert call_kwargs["type"] == "custom_python"


def test_scenario_create_if_not_exists(patch_client):
    """--if-not-exists suppresses already-exists errors."""
    proj = patch_client.get_project("PROJ1")
    proj.create_scenario.side_effect = Exception(
        "409 Conflict: scenario already exists"
    )
    result = runner.invoke(
        app,
        ["scenario", "create", "Existing", "--project", "PROJ1", "--if-not-exists"],
    )
    assert result.exit_code == 0
    assert "already exists" in result.output


def test_scenario_create_already_exists_fails(patch_client):
    """Without --if-not-exists, already-exists errors propagate."""
    proj = patch_client.get_project("PROJ1")
    proj.create_scenario.side_effect = Exception(
        "409 Conflict: scenario already exists"
    )
    result = runner.invoke(
        app,
        ["scenario", "create", "Existing", "--project", "PROJ1"],
    )
    assert result.exit_code != 0


def test_scenario_delete(patch_client):
    result = runner.invoke(app, ["scenario", "delete", "scen1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "Deleted scenario" in result.output
    proj = patch_client.get_project("PROJ1")
    scenario = proj.get_scenario("scen1")
    scenario.delete.assert_called_once()


def test_scenario_get_definition(patch_client):
    result = runner.invoke(
        app, ["scenario", "get-definition", "scen1", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["type"] == "step_based"
    assert parsed["name"] == "Build All"
    assert parsed["params"] == {}


def test_scenario_get_definition_with_output_flag(patch_client):
    result = runner.invoke(
        app, ["scenario", "get-definition", "scen1", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["name"] == "Build All"


def test_scenario_set_definition(patch_client):
    new_def = json.dumps({"type": "step_based", "name": "Updated", "params": {"x": 1}})
    result = runner.invoke(
        app,
        [
            "scenario",
            "set-definition",
            "scen1",
            "--project",
            "PROJ1",
            "--definition",
            new_def,
        ],
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
        [
            "scenario",
            "set-definition",
            "scen1",
            "--project",
            "PROJ1",
            "--definition",
            f"@{defn_file}",
        ],
    )
    assert result.exit_code == 0
    assert "Updated definition" in result.output
    proj = patch_client.get_project("PROJ1")
    scenario = proj.get_scenario("scen1")
    scenario.set_definition.assert_called_once_with(
        {"type": "step_based", "name": "FromFile"}
    )


# ── run --wait polling tests ─────────────────────────────────────────────


def test_scenario_run_wait_polls(patch_client):
    """--wait polls get_last_runs when trigger lacks wait_for_result."""
    from unittest.mock import patch as mock_patch, MagicMock

    proj = patch_client.get_project("PROJ1")
    scenario = proj.get_scenario("scen1")
    # Trigger has no wait_for_result (spec=[] in conftest)
    trigger = MagicMock(spec=[])
    scenario.run.return_value = trigger
    # First poll: outcome is None (still running), second: SUCCESS
    run_in_progress = MagicMock()
    run_in_progress.outcome = None
    run_done = MagicMock()
    run_done.outcome = "SUCCESS"
    scenario.get_last_runs.side_effect = [[run_in_progress], [run_done]]

    with mock_patch("dku_cli.commands.scenario.time.sleep"):
        result = runner.invoke(
            app, ["scenario", "run", "scen1", "--project", "PROJ1", "--wait"]
        )
    assert result.exit_code == 0
    assert "SUCCESS" in result.output


def test_scenario_run_wait_failure(patch_client):
    """--wait reports non-SUCCESS outcomes."""
    from unittest.mock import patch as mock_patch, MagicMock

    proj = patch_client.get_project("PROJ1")
    scenario = proj.get_scenario("scen1")
    trigger = MagicMock(spec=[])
    scenario.run.return_value = trigger
    run_done = MagicMock()
    run_done.outcome = "FAILED"
    scenario.get_last_runs.return_value = [run_done]

    with mock_patch("dku_cli.commands.scenario.time.sleep"):
        result = runner.invoke(
            app, ["scenario", "run", "scen1", "--project", "PROJ1", "--wait"]
        )
    assert result.exit_code == 0
    assert "FAILED" in result.output


# ── Trigger commands ────────────────────────────────────────────────────


def test_scenario_list_triggers(patch_client):
    result = runner.invoke(
        app, ["scenario", "list-triggers", "scen1", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "temporal" in result.output
    assert "Daily at 02:00" in result.output


def test_scenario_list_triggers_json(patch_client):
    result = runner.invoke(
        app,
        ["scenario", "list-triggers", "scen1", "--project", "PROJ1", "-o", "json"],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert isinstance(parsed, list)
    assert parsed[0]["type"] == "temporal"


def test_scenario_list_triggers_empty(patch_client):
    proj = patch_client.get_project("PROJ1")
    scenario = proj.get_scenario("scen1")
    settings = scenario.get_settings()
    # Clear triggers
    settings.raw_triggers.clear()
    result = runner.invoke(
        app, ["scenario", "list-triggers", "scen1", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "No triggers" in result.output


def test_scenario_add_trigger_generic(patch_client):
    proj = patch_client.get_project("PROJ1")
    scenario = proj.get_scenario("scen1")
    settings = scenario.get_settings()
    initial_count = len(settings.raw_triggers)

    trigger_json = json.dumps(
        {
            "type": "temporal",
            "params": {"frequency": "Minutely", "repeatFrequency": 10},
        }
    )
    result = runner.invoke(
        app,
        [
            "scenario",
            "add-trigger",
            "scen1",
            "--trigger",
            trigger_json,
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Added temporal trigger" in result.output
    assert len(settings.raw_triggers) == initial_count + 1
    added = settings.raw_triggers[-1]
    assert added["type"] == "temporal"
    assert added["active"] is True  # defaulted
    settings.save.assert_called()


def test_scenario_add_trigger_missing_type(patch_client):
    result = runner.invoke(
        app,
        [
            "scenario",
            "add-trigger",
            "scen1",
            "--trigger",
            '{"params":{}}',
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "type" in result.output


def test_scenario_add_trigger_dataset(patch_client):
    proj = patch_client.get_project("PROJ1")
    scenario = proj.get_scenario("scen1")
    settings = scenario.get_settings()
    initial_count = len(settings.raw_triggers)

    result = runner.invoke(
        app,
        [
            "scenario",
            "add-trigger-dataset",
            "scen1",
            "--dataset",
            "adult_census",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "ds_modified" in result.output
    assert len(settings.raw_triggers) == initial_count + 1
    added = settings.raw_triggers[-1]
    assert added["type"] == "ds_modified"
    assert added["params"]["watches"][0]["itemId"] == "adult_census"
    assert added["delay"] == 900  # default — root level, not in params
    assert added["graceDelaySettings"]["delay"] == 120  # default — root level
    settings.save.assert_called()


def test_scenario_add_trigger_dataset_custom_delays(patch_client):
    proj = patch_client.get_project("PROJ1")
    scenario = proj.get_scenario("scen1")
    settings = scenario.get_settings()

    result = runner.invoke(
        app,
        [
            "scenario",
            "add-trigger-dataset",
            "scen1",
            "--dataset",
            "sales",
            "--delay",
            "600",
            "--grace-delay",
            "60",
            "--no-check-again",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    added = settings.raw_triggers[-1]
    assert added["delay"] == 600  # root level
    assert added["graceDelaySettings"]["delay"] == 60  # root level
    assert added["graceDelaySettings"]["checkAgainAfterGraceDelay"] is False


def test_scenario_remove_trigger(patch_client):
    proj = patch_client.get_project("PROJ1")
    scenario = proj.get_scenario("scen1")
    settings = scenario.get_settings()
    initial_count = len(settings.raw_triggers)

    result = runner.invoke(
        app,
        [
            "scenario",
            "remove-trigger",
            "scen1",
            "--index",
            "0",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Removed" in result.output
    assert len(settings.raw_triggers) == initial_count - 1
    settings.save.assert_called()


def test_scenario_remove_trigger_invalid_index(patch_client):
    result = runner.invoke(
        app,
        [
            "scenario",
            "remove-trigger",
            "scen1",
            "--index",
            "99",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "out of range" in result.output
