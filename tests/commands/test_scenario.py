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
    result = runner.invoke(
        app, ["scenario", "delete", "scen1", "--project", "PROJ1", "--yes"]
    )
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
    # params.steps comes from get_settings().get_raw(), not the legacy /light endpoint
    assert parsed["params"] == {"steps": []}


def test_scenario_get_definition_with_output_flag(patch_client):
    result = runner.invoke(
        app, ["scenario", "get-definition", "scen1", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["name"] == "Build All"


def test_scenario_set_definition_persists_steps(patch_client):
    """Regression: legacy set_definition hit /light and silently dropped params.steps.

    The CLI must now go through DSSScenarioSettings.save() so step-based
    scenarios actually keep their steps after set-definition.
    """
    steps = [
        {
            "id": "s1",
            "name": "Build X",
            "type": "build_flowitem",
            "params": {
                "builds": [{"type": "DATASET", "itemId": "ds_x", "partitionsSpec": ""}],
                "buildMode": "RECURSIVE_BUILD",
            },
        }
    ]
    new_def = json.dumps(
        {"type": "step_based", "name": "Updated", "params": {"steps": steps}}
    )
    proj = patch_client.get_project("PROJ1")
    scenario = proj.get_scenario("scen1")
    # Simulate the server persisting what save() pushed.
    raw = scenario.get_settings().get_raw()

    def _save_side_effect():
        raw["params"]["steps"] = list(raw["params"].get("steps", []))

    scenario.get_settings().save.side_effect = _save_side_effect

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
    assert result.exit_code == 0, result.output
    assert "Updated definition" in result.output
    scenario.get_settings().save.assert_called()
    # The legacy header-only endpoint must NOT be called.
    scenario.set_definition.assert_not_called()
    assert raw["params"]["steps"] == steps
    assert raw["name"] == "Updated"


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
    scenario.get_settings().save.assert_called()
    assert scenario.get_settings().get_raw()["name"] == "FromFile"


def test_scenario_set_definition_warns_on_step_count_mismatch(patch_client):
    """If the server silently drops steps (past regression), the CLI must fail loudly."""
    new_def = json.dumps(
        {
            "params": {
                "steps": [
                    {"id": "s1", "name": "A", "type": "build_flowitem", "params": {}},
                    {"id": "s2", "name": "B", "type": "build_flowitem", "params": {}},
                ]
            }
        }
    )
    proj = patch_client.get_project("PROJ1")
    scenario = proj.get_scenario("scen1")
    raw = scenario.get_settings().get_raw()

    # Simulate the old legacy-endpoint bug: save() accepts the payload but
    # persists 0 steps (the /light endpoint drops params.steps).
    def _save_drops_steps():
        raw["params"]["steps"] = []

    scenario.get_settings().save.side_effect = _save_drops_steps

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
    assert result.exit_code != 0
    assert "Save incomplete" in result.output
    assert "sent 2 step" in result.output
    assert "server persisted 0" in result.output


# ── run --wait polling tests ─────────────────────────────────────────────


def test_scenario_run_wait_polls(patch_client):
    """--wait polls get_last_runs until run.running() is False."""
    from unittest.mock import patch as mock_patch, MagicMock

    proj = patch_client.get_project("PROJ1")
    scenario = proj.get_scenario("scen1")
    trigger = MagicMock(spec=[])
    scenario.run.return_value = trigger
    # First poll: still running. Second poll: done with SUCCESS.
    run_in_progress = MagicMock()
    run_in_progress.running.return_value = True
    run_done = MagicMock()
    run_done.running.return_value = False
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
    run_done.running.return_value = False
    run_done.outcome = "FAILED"
    scenario.get_last_runs.return_value = [run_done]

    with mock_patch("dku_cli.commands.scenario.time.sleep"):
        result = runner.invoke(
            app, ["scenario", "run", "scen1", "--project", "PROJ1", "--wait"]
        )
    assert result.exit_code == 0
    assert "FAILED" in result.output


def test_scenario_run_wait_survives_transient_outcome_value_error(patch_client):
    """Regression: DSSScenarioRun.outcome RAISES ValueError until result is populated.

    The poll loop used to call `run.outcome` behind a `hasattr(run, 'outcome')`
    gate — but the property descriptor exists on the class, so hasattr returned
    True and the ValueError escaped, turning successful runs into "DSS API
    error: outcome not available for this scenario run".
    """
    from unittest.mock import patch as mock_patch, MagicMock, PropertyMock

    proj = patch_client.get_project("PROJ1")
    scenario = proj.get_scenario("scen1")
    trigger = MagicMock(spec=[])
    scenario.run.return_value = trigger

    # Run #1: still running. .outcome would raise if accessed.
    run_in_progress = MagicMock()
    run_in_progress.running.return_value = True
    type(run_in_progress).outcome = PropertyMock(
        side_effect=ValueError(
            "outcome not available for this scenario run. Maybe still running?"
        )
    )
    # Run #2: done, SUCCESS.
    run_done = MagicMock()
    run_done.running.return_value = False
    run_done.outcome = "SUCCESS"
    scenario.get_last_runs.side_effect = [[run_in_progress], [run_done]]

    with mock_patch("dku_cli.commands.scenario.time.sleep"):
        result = runner.invoke(
            app, ["scenario", "run", "scen1", "--project", "PROJ1", "--wait"]
        )
    assert result.exit_code == 0, result.output
    assert "SUCCESS" in result.output
    assert "outcome not available" not in result.output


# ── Trigger commands ────────────────────────────────────────────────────


def test_scenario_list_triggers(patch_client):
    result = runner.invoke(
        app, ["scenario", "list-triggers", "scen1", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "temporal" in result.output


# ── last-run and runs tests ─────────────────────────────────────────────


def test_scenario_last_run(patch_client):
    result = runner.invoke(app, ["scenario", "last-run", "scen1", "--project", "PROJ1"])
    assert result.exit_code == 0


def test_scenario_last_run_json(patch_client):
    result = runner.invoke(
        app, ["scenario", "last-run", "scen1", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["id"] == "run1"
    assert parsed["state"] == "SUCCESS"


def test_scenario_last_run_none(patch_client):
    """No finished runs returns prescriptive error."""
    proj = patch_client.get_project("PROJ1")
    scenario = proj.get_scenario("scen1")
    scenario.get_last_finished_run.side_effect = ValueError("No scenario run completed")
    result = runner.invoke(app, ["scenario", "last-run", "scen1", "--project", "PROJ1"])
    assert result.exit_code != 0
    assert "No finished runs" in result.output


def test_scenario_runs(patch_client):
    result = runner.invoke(app, ["scenario", "runs", "scen1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "run1" in result.output


def test_scenario_runs_json(patch_client):
    result = runner.invoke(
        app, ["scenario", "runs", "scen1", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 1
    assert parsed[0]["id"] == "run1"
    assert parsed[0]["state"] == "SUCCESS"


def test_scenario_runs_custom_limit(patch_client):
    result = runner.invoke(
        app, ["scenario", "runs", "scen1", "--limit", "5", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    scenario = proj.get_scenario("scen1")
    scenario.get_last_runs.assert_called_with(limit=5)


def test_scenario_runs_json_still_running(patch_client):
    """Regression: a fresh run with no result raises ValueError on .outcome.

    The CLI must catch it and label the state RUNNING so `-o json` emits a
    valid array; otherwise jq sees a partial Rich traceback ("Invalid numeric
    literal at line 1, column 4").
    """
    from unittest.mock import MagicMock, PropertyMock

    proj = patch_client.get_project("PROJ1")
    scenario = proj.get_scenario("scen1")
    running = MagicMock()
    running.id = "run_in_flight"
    type(running).outcome = PropertyMock(
        side_effect=ValueError(
            "outcome not available for this scenario run. Maybe still running?"
        )
    )
    running.get_start_time.return_value = "2026-05-27 10:00:00"
    running.get_duration.return_value = None
    scenario.get_last_runs.return_value = [running]

    result = runner.invoke(
        app, ["scenario", "runs", "scen1", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output)
    assert parsed[0]["id"] == "run_in_flight"
    assert parsed[0]["state"] == "RUNNING"


def test_scenario_runs_json_empty(patch_client):
    """No runs ⇒ `-o json` emits `[]`, not a malformed table-shaped object."""
    proj = patch_client.get_project("PROJ1")
    scenario = proj.get_scenario("scen1")
    scenario.get_last_runs.return_value = []

    result = runner.invoke(
        app, ["scenario", "runs", "scen1", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output)
    assert parsed == []


# --- last-run --successful ---


def test_scenario_last_run_successful(patch_client):
    """--successful calls get_last_successful_run."""
    result = runner.invoke(
        app,
        ["scenario", "last-run", "scen1", "--successful", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    scenario = proj.get_scenario("scen1")
    scenario.get_last_successful_run.assert_called_once()


def test_scenario_last_run_successful_none(patch_client):
    """No successful runs gives prescriptive error."""
    proj = patch_client.get_project("PROJ1")
    scenario = proj.get_scenario("scen1")
    scenario.get_last_successful_run.side_effect = ValueError(
        "No scenario run completed successfully"
    )
    result = runner.invoke(
        app,
        ["scenario", "last-run", "scen1", "--successful", "--project", "PROJ1"],
    )
    assert result.exit_code != 0
    assert "successful" in result.output.lower()


# --- runs --from/--to ---


def test_scenario_runs_by_date(patch_client):
    """--from triggers get_runs_by_date."""
    result = runner.invoke(
        app,
        [
            "scenario",
            "runs",
            "scen1",
            "--from",
            "2026-04-01",
            "--to",
            "2026-04-08",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "run1" in result.output
    proj = patch_client.get_project("PROJ1")
    scenario = proj.get_scenario("scen1")
    scenario.get_runs_by_date.assert_called_once_with("2026-04-01", "2026-04-08")


def test_scenario_runs_by_date_from_only(patch_client):
    """--from without --to uses from_date as to_date."""
    result = runner.invoke(
        app,
        ["scenario", "runs", "scen1", "--from", "2026-04-01", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    scenario = proj.get_scenario("scen1")
    scenario.get_runs_by_date.assert_called_once_with("2026-04-01", "2026-04-01")


# --- avg-duration ---


def test_scenario_avg_duration(patch_client):
    """Shows average duration."""
    result = runner.invoke(
        app, ["scenario", "avg-duration", "scen1", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "42.5" in result.output


def test_scenario_avg_duration_json(patch_client):
    """JSON output returns structured result."""
    result = runner.invoke(
        app,
        ["scenario", "avg-duration", "scen1", "--project", "PROJ1", "-o", "json"],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["avg_duration_seconds"] == 42.5
    assert parsed["limit"] == 3


def test_scenario_avg_duration_not_enough_runs(patch_client):
    """Returns None when not enough runs."""
    proj = patch_client.get_project("PROJ1")
    scenario = proj.get_scenario("scen1")
    scenario.get_average_duration.return_value = None
    result = runner.invoke(
        app, ["scenario", "avg-duration", "scen1", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "not enough" in result.output.lower()


def test_scenario_avg_duration_custom_limit(patch_client):
    """--limit passes through to dataikuapi."""
    result = runner.invoke(
        app,
        ["scenario", "avg-duration", "scen1", "--limit", "5", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    scenario = proj.get_scenario("scen1")
    scenario.get_average_duration.assert_called_once_with(limit=5)


# --- run-log ---


def test_scenario_run_log(patch_client):
    """Gets logs for a specific run."""
    result = runner.invoke(
        app,
        ["scenario", "run-log", "scen1", "--run", "run1", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    assert "Step 1 completed" in result.output
    proj = patch_client.get_project("PROJ1")
    scenario = proj.get_scenario("scen1")
    scenario.get_run.assert_called_once_with("run1")
    run = scenario.get_run.return_value
    run.get_log.assert_called_once_with(step_id=None)


def test_scenario_run_log_with_step(patch_client):
    """--step scopes logs to a single step."""
    result = runner.invoke(
        app,
        [
            "scenario",
            "run-log",
            "scen1",
            "--run",
            "run1",
            "--step",
            "step1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    run = patch_client.get_project("PROJ1").get_scenario("scen1").get_run.return_value
    run.get_log.assert_called_once_with(step_id="step1")


def test_scenario_run_log_requires_run(patch_client):
    """--run is required."""
    result = runner.invoke(app, ["scenario", "run-log", "scen1", "--project", "PROJ1"])
    assert result.exit_code != 0


def test_scenario_run_log_grep_match(patch_client):
    """--grep shows only matching lines."""
    result = runner.invoke(
        app,
        [
            "scenario",
            "run-log",
            "scen1",
            "--run",
            "run1",
            "--grep",
            "completed",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Step 1 completed" in result.output
    assert "Done" not in result.output


def test_scenario_run_log_grep_no_match(patch_client):
    """--grep with no matching line warns and returns early."""
    result = runner.invoke(
        app,
        [
            "scenario",
            "run-log",
            "scen1",
            "--run",
            "run1",
            "--grep",
            "nonexistent",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "No lines matching 'nonexistent' found" in result.output
    assert "Step 1 completed" not in result.output


def test_scenario_run_log_tail(patch_client):
    """--tail shows only the last N lines."""
    result = runner.invoke(
        app,
        [
            "scenario",
            "run-log",
            "scen1",
            "--run",
            "run1",
            "--tail",
            "1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Done" in result.output
    assert "Step 1 completed" not in result.output


# --- set-metadata ---


def test_scenario_set_metadata_description(patch_client):
    result = runner.invoke(
        app,
        [
            "scenario",
            "set-metadata",
            "scen1",
            "--description",
            "Nightly ETL build",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Updated metadata" in result.output
    scenario = patch_client.get_project("PROJ1").get_scenario("scen1")
    scenario.set_definition.assert_called_once()
    defn = scenario.set_definition.call_args[0][0]
    assert defn["description"] == "Nightly ETL build"


def test_scenario_set_metadata_tags(patch_client):
    result = runner.invoke(
        app,
        [
            "scenario",
            "set-metadata",
            "scen1",
            "--tags",
            "etl,nightly",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    scenario = patch_client.get_project("PROJ1").get_scenario("scen1")
    defn = scenario.set_definition.call_args[0][0]
    assert defn["tags"] == ["etl", "nightly"]


def test_scenario_set_metadata_no_args(patch_client):
    result = runner.invoke(
        app, ["scenario", "set-metadata", "scen1", "--project", "PROJ1"]
    )
    assert result.exit_code != 0


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
            "--yes",
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
            "--yes",
        ],
    )
    assert result.exit_code != 0
    assert "out of range" in result.output


# --- list-reporters / add-reporter ---


def _set_reporters(patch_client, reporters):
    proj = patch_client.get_project("PROJ1")
    scenario = proj.get_scenario("nightly")
    settings = scenario.get_settings()
    settings.raw_reporters = reporters
    return settings


def test_scenario_list_reporters_table(patch_client):
    _set_reporters(
        patch_client,
        [
            {
                "messaging": {
                    "type": "mail-scenario",
                    "configuration": {"recipient": "ops@example.com"},
                },
                "runCondition": "outcome != 'SUCCESS'",
            },
            {
                "messaging": {
                    "type": "slack-scenario",
                    "configuration": {"recipient": "#alerts"},
                },
                "runCondition": "",
            },
        ],
    )
    result = runner.invoke(
        app, ["scenario", "list-reporters", "nightly", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "Reporters: nightly" in result.output
    assert "mail-scenario" in result.output
    assert "ops@example.com" in result.output
    assert "outcome != 'SUCCESS'" in result.output
    # Empty runCondition renders as the (always) sentinel.
    assert "(always)" in result.output


def test_scenario_list_reporters_json(patch_client):
    _set_reporters(
        patch_client,
        [
            {
                "messaging": {
                    "type": "mail-scenario",
                    "configuration": {"recipient": "ops@example.com"},
                },
                "runCondition": "outcome != 'SUCCESS'",
            }
        ],
    )
    result = runner.invoke(
        app,
        ["scenario", "list-reporters", "nightly", "--project", "PROJ1", "-o", "json"],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["messaging"]["type"] == "mail-scenario"
    assert parsed[0]["messaging"]["configuration"]["recipient"] == "ops@example.com"


def test_scenario_list_reporters_empty(patch_client):
    _set_reporters(patch_client, [])
    result = runner.invoke(
        app, ["scenario", "list-reporters", "nightly", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "No reporters on scenario 'nightly'" in result.output
    assert "dku scenario add-reporter nightly" in result.output


def test_scenario_add_reporter_failure(patch_client):
    settings = _set_reporters(patch_client, [])
    result = runner.invoke(
        app,
        [
            "scenario",
            "add-reporter",
            "nightly",
            "--recipient",
            "ops@example.com",
            "--condition",
            "failure",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Added 'failure' email reporter to 'ops@example.com'" in result.output
    assert "index 0" in result.output
    settings.save.assert_called_once()
    assert len(settings.raw_reporters) == 1
    reporter = settings.raw_reporters[0]
    assert reporter["runCondition"] == "outcome != 'SUCCESS'"
    assert reporter["runConditionEnabled"] is True
    assert reporter["messaging"]["type"] == "mail-scenario"
    assert reporter["messaging"]["configuration"]["recipient"] == "ops@example.com"


def test_scenario_add_reporter_always_disables_condition(patch_client):
    settings = _set_reporters(patch_client, [])
    result = runner.invoke(
        app,
        [
            "scenario",
            "add-reporter",
            "nightly",
            "--recipient",
            "team@example.com",
            "--condition",
            "always",
            "--channel",
            "smtp-prod",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    reporter = settings.raw_reporters[0]
    assert reporter["runCondition"] == ""
    assert reporter["runConditionEnabled"] is False
    assert reporter["messaging"]["configuration"]["channelId"] == "smtp-prod"


def test_scenario_add_reporter_invalid_condition(patch_client):
    settings = _set_reporters(patch_client, [])
    result = runner.invoke(
        app,
        [
            "scenario",
            "add-reporter",
            "nightly",
            "--recipient",
            "ops@example.com",
            "--condition",
            "sometimes",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "Unknown condition 'sometimes'" in result.output
    assert "failure, success, always" in result.output
    settings.save.assert_not_called()
