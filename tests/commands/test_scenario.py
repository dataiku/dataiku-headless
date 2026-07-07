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
        app, ["--format", "json", "scenario", "list", "--project", "PROJ1"]
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
        app, ["--format", "json", "scenario", "status", "scen1", "--project", "PROJ1"]
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
        app,
        [
            "--format",
            "json",
            "scenario",
            "get-definition",
            "scen1",
            "--project",
            "PROJ1",
        ],
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


# ── set-active tests ─────────────────────────────────────────────────────


def test_scenario_set_active_enables_scenario_and_triggers(patch_client):
    """set-active --active (default) flips scenario.active AND every trigger."""
    proj = patch_client.get_project("PROJ1")
    scenario = proj.get_scenario("scen1")
    raw = scenario.get_settings().get_raw()
    raw["active"] = False
    raw["triggers"] = [
        {"id": "t1", "type": "temporal", "active": False},
        {"id": "t2", "type": "dataset_modified", "active": False},
    ]

    result = runner.invoke(
        app,
        ["scenario", "set-active", "scen1", "--project", "PROJ1"],
    )
    assert result.exit_code == 0, result.output
    assert raw["active"] is True
    assert all(t["active"] is True for t in raw["triggers"])
    scenario.get_settings().save.assert_called()


def test_scenario_set_active_inactive_drops_both(patch_client):
    """set-active --inactive flips both off."""
    proj = patch_client.get_project("PROJ1")
    scenario = proj.get_scenario("scen1")
    raw = scenario.get_settings().get_raw()
    raw["active"] = True
    raw["triggers"] = [{"id": "t1", "active": True}]

    result = runner.invoke(
        app,
        ["scenario", "set-active", "scen1", "--inactive", "--project", "PROJ1"],
    )
    assert result.exit_code == 0, result.output
    assert raw["active"] is False
    assert raw["triggers"][0]["active"] is False


def test_scenario_set_active_skip_triggers(patch_client):
    """--skip-triggers leaves trigger.active untouched."""
    proj = patch_client.get_project("PROJ1")
    scenario = proj.get_scenario("scen1")
    raw = scenario.get_settings().get_raw()
    raw["active"] = False
    raw["triggers"] = [{"id": "t1", "active": False}]

    result = runner.invoke(
        app,
        [
            "scenario",
            "set-active",
            "scen1",
            "--skip-triggers",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert raw["active"] is True
    # trigger left at its previous False — agents flipping just the top
    # flag should still see "1/1 → 0/1 active" semantics in the message.
    assert raw["triggers"][0]["active"] is False


# ── run --wait tests ─────────────────────────────────────────────────────


def _wait_mocks(scenario, outcome):
    """Wire scenario.run() → trigger fire → a completed run with `outcome`."""
    from unittest.mock import MagicMock

    run_done = MagicMock()
    run_done.outcome = outcome
    trigger = MagicMock()
    trigger.wait_for_scenario_run.return_value = run_done
    scenario.run.return_value = trigger
    return trigger, run_done


def test_scenario_run_wait_success(patch_client):
    """--wait waits on the run the trigger fire started and reports SUCCESS."""
    proj = patch_client.get_project("PROJ1")
    scenario = proj.get_scenario("scen1")
    _wait_mocks(scenario, "SUCCESS")

    result = runner.invoke(
        app, ["scenario", "run", "scen1", "--project", "PROJ1", "--wait"]
    )
    assert result.exit_code == 0
    assert "SUCCESS" in result.output


def test_scenario_run_wait_uses_trigger_fire_not_last_runs(patch_client):
    """Regression: --wait must resolve the run via the trigger fire, NOT
    get_last_runs(), which can return a previously-finished run and report a
    stale outcome for a run this call never started."""
    proj = patch_client.get_project("PROJ1")
    scenario = proj.get_scenario("scen1")
    trigger, run_done = _wait_mocks(scenario, "SUCCESS")

    result = runner.invoke(
        app, ["scenario", "run", "scen1", "--project", "PROJ1", "--wait"]
    )
    assert result.exit_code == 0
    trigger.wait_for_scenario_run.assert_called_once()
    run_done.wait_for_completion.assert_called_once()
    scenario.get_last_runs.assert_not_called()


def test_scenario_run_wait_failure(patch_client):
    """--wait on a FAILED outcome must exit NON-ZERO so chained `&&` steps stop.

    Regression: this used to exit 0 (error() only writes stderr), letting an
    agent chaining `scenario run --wait && next-step` march on past a failed
    scenario.
    """
    proj = patch_client.get_project("PROJ1")
    scenario = proj.get_scenario("scen1")
    _wait_mocks(scenario, "FAILED")

    result = runner.invoke(
        app, ["scenario", "run", "scen1", "--project", "PROJ1", "--wait"]
    )
    assert result.exit_code != 0, result.output
    assert "FAILED" in result.output


def test_scenario_run_wait_aborted_exits_nonzero(patch_client):
    """--wait on an ABORTED outcome must also exit non-zero."""
    proj = patch_client.get_project("PROJ1")
    scenario = proj.get_scenario("scen1")
    _wait_mocks(scenario, "ABORTED")

    result = runner.invoke(
        app, ["scenario", "run", "scen1", "--project", "PROJ1", "--wait"]
    )
    assert result.exit_code != 0, result.output
    assert "ABORTED" in result.output


def test_scenario_run_wait_warning_exits_zero(patch_client):
    """--wait on a WARNING outcome is a successful terminal state — exit 0,
    but the output distinguishes it from a clean SUCCESS."""
    proj = patch_client.get_project("PROJ1")
    scenario = proj.get_scenario("scen1")
    _wait_mocks(scenario, "WARNING")

    result = runner.invoke(
        app, ["scenario", "run", "scen1", "--project", "PROJ1", "--wait"]
    )
    assert result.exit_code == 0, result.output
    assert "WARNING" in result.output


def test_scenario_run_wait_cancelled_exits_nonzero(patch_client):
    """If the trigger fire is cancelled (scenario already running, or a later
    trigger superseded it), no run was started — --wait must exit non-zero
    instead of reporting a misleading success."""
    from unittest.mock import MagicMock

    proj = patch_client.get_project("PROJ1")
    scenario = proj.get_scenario("scen1")
    trigger = MagicMock()
    trigger.wait_for_scenario_run.return_value = None  # cancelled
    scenario.run.return_value = trigger

    result = runner.invoke(
        app, ["scenario", "run", "scen1", "--project", "PROJ1", "--wait"]
    )
    assert result.exit_code != 0, result.output
    assert "CANCELLED" in result.output


def test_scenario_run_wait_survives_unavailable_outcome(patch_client):
    """Defensive: if .outcome still raises ValueError after wait_for_completion
    (odd mock/shape), --wait reports UNKNOWN and exits non-zero rather than
    leaking a raw stack trace."""
    from unittest.mock import MagicMock, PropertyMock

    proj = patch_client.get_project("PROJ1")
    scenario = proj.get_scenario("scen1")
    run_done = MagicMock()
    type(run_done).outcome = PropertyMock(
        side_effect=ValueError("outcome not available for this scenario run.")
    )
    trigger = MagicMock()
    trigger.wait_for_scenario_run.return_value = run_done
    scenario.run.return_value = trigger

    result = runner.invoke(
        app, ["scenario", "run", "scen1", "--project", "PROJ1", "--wait"]
    )
    assert result.exit_code != 0, result.output
    assert "UNKNOWN" in result.output
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
        app, ["--format", "json", "scenario", "last-run", "scen1", "--project", "PROJ1"]
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
        app, ["--format", "json", "scenario", "runs", "scen1", "--project", "PROJ1"]
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
        app, ["--format", "json", "scenario", "runs", "scen1", "--project", "PROJ1"]
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
        app, ["--format", "json", "scenario", "runs", "scen1", "--project", "PROJ1"]
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
        ["--format", "json", "scenario", "avg-duration", "scen1", "--project", "PROJ1"],
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
        [
            "--format",
            "json",
            "scenario",
            "list-triggers",
            "scen1",
            "--project",
            "PROJ1",
        ],
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


def test_scenario_add_trigger_time_daily(patch_client):
    proj = patch_client.get_project("PROJ1")
    scenario = proj.get_scenario("scen1")
    settings = scenario.get_settings()
    initial_count = len(settings.raw_triggers)

    result = runner.invoke(
        app,
        [
            "scenario",
            "add-trigger-time",
            "scen1",
            "--frequency",
            "Daily",
            "--hour",
            "3",
            "--minute",
            "30",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "temporal" in result.output
    assert len(settings.raw_triggers) == initial_count + 1
    added = settings.raw_triggers[-1]
    assert added["type"] == "temporal"
    assert added["active"] is True
    p = added["params"]
    assert p["frequency"] == "Daily"
    assert p["hour"] == 3
    assert p["minute"] == 30
    assert p["repeatFrequency"] == 1
    assert p["timezone"] == "SERVER"
    assert "daysOfWeek" not in p


def test_scenario_add_trigger_time_weekly(patch_client):
    proj = patch_client.get_project("PROJ1")
    scenario = proj.get_scenario("scen1")
    settings = scenario.get_settings()

    result = runner.invoke(
        app,
        [
            "scenario",
            "add-trigger-time",
            "scen1",
            "--frequency",
            "Weekly",
            "--days",
            "Monday,Wednesday,Friday",
            "--hour",
            "6",
            "--minute",
            "0",
            "--timezone",
            "Europe/Paris",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    p = settings.raw_triggers[-1]["params"]
    assert p["frequency"] == "Weekly"
    assert p["daysOfWeek"] == ["Monday", "Wednesday", "Friday"]
    assert p["timezone"] == "Europe/Paris"


def test_scenario_add_trigger_time_minutely(patch_client):
    proj = patch_client.get_project("PROJ1")
    scenario = proj.get_scenario("scen1")
    settings = scenario.get_settings()

    result = runner.invoke(
        app,
        [
            "scenario",
            "add-trigger-time",
            "scen1",
            "--frequency",
            "Minutely",
            "--repeat-every",
            "15",
            "--inactive",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    added = settings.raw_triggers[-1]
    assert added["active"] is False
    p = added["params"]
    assert p["frequency"] == "Minutely"
    assert p["repeatFrequency"] == 15
    # Minutely should not include hour/minute
    assert "hour" not in p
    assert "minute" not in p


def test_scenario_add_trigger_time_monthly_last_day(patch_client):
    proj = patch_client.get_project("PROJ1")
    scenario = proj.get_scenario("scen1")
    settings = scenario.get_settings()

    result = runner.invoke(
        app,
        [
            "scenario",
            "add-trigger-time",
            "scen1",
            "--frequency",
            "Monthly",
            "--monthly-run-on",
            "LAST_DAY_OF_THE_MONTH",
            "--hour",
            "3",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    p = settings.raw_triggers[-1]["params"]
    assert p["monthlyRunOn"] == "LAST_DAY_OF_THE_MONTH"
    assert p["hour"] == 3


def test_scenario_add_trigger_time_invalid_frequency(patch_client):
    result = runner.invoke(
        app,
        [
            "scenario",
            "add-trigger-time",
            "scen1",
            "--frequency",
            "Hourlyish",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "Invalid --frequency" in result.output


def test_scenario_add_trigger_time_weekly_requires_days(patch_client):
    result = runner.invoke(
        app,
        [
            "scenario",
            "add-trigger-time",
            "scen1",
            "--frequency",
            "Weekly",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "--days is required" in result.output


def test_scenario_add_trigger_time_weekly_invalid_day(patch_client):
    result = runner.invoke(
        app,
        [
            "scenario",
            "add-trigger-time",
            "scen1",
            "--frequency",
            "Weekly",
            "--days",
            "Monday,Funday",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "Invalid day" in result.output


def test_scenario_add_trigger_python_uses_canonical_env_mode(patch_client):
    proj = patch_client.get_project("PROJ1")
    scenario = proj.get_scenario("scen1")
    settings = scenario.get_settings()

    result = runner.invoke(
        app,
        [
            "scenario",
            "add-trigger-python",
            "scen1",
            "--code",
            "from dataiku.scenario import Trigger\nTrigger().fire()",
            "--env-mode",
            "USE_BUILTIN_MODE",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    added = settings.raw_triggers[-1]
    assert added["type"] == "custom_python"
    assert added["params"]["envSelection"] == {"envMode": "USE_BUILTIN_MODE"}


def test_scenario_add_trigger_python_rejects_old_invalid_env_mode(patch_client):
    result = runner.invoke(
        app,
        [
            "scenario",
            "add-trigger-python",
            "scen1",
            "--code",
            "print('noop')",
            "--env-mode",
            "USE_BUILTIN_ENV",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 2
    assert "use_builtin_mode" in result.output


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


def _patch_step_scenario(patch_client):
    """Configure the scenario_settings mock to expose a real raw_steps list."""
    proj = patch_client.get_project("PROJ1")
    scenario = proj.get_scenario("scen1")
    settings = scenario.get_settings.return_value
    steps: list[dict] = []
    type(settings).raw_steps = property(lambda self: steps)
    return steps


def test_add_step_python_uses_canonical_env_mode(patch_client):
    steps = _patch_step_scenario(patch_client)
    result = runner.invoke(
        app,
        [
            "scenario",
            "add-step-python",
            "scen1",
            "--name",
            "Inline Python",
            "--code",
            "print(1)",
            "--env-mode",
            "USE_BUILTIN_MODE",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    step = steps[0]
    assert step["type"] == "custom_python"
    assert step["params"]["envSelection"] == {"envMode": "USE_BUILTIN_MODE"}


def test_add_step_python_rejects_old_invalid_env_mode(patch_client):
    _patch_step_scenario(patch_client)
    result = runner.invoke(
        app,
        [
            "scenario",
            "add-step-python",
            "scen1",
            "--name",
            "Inline Python",
            "--code",
            "print(1)",
            "--env-mode",
            "USE_BUILTIN_ENV",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 2
    assert "use_builtin_mode" in result.output


def test_add_step_build_with_retry_and_warnings(patch_client):
    """--max-retries / --delay-between-retries / --handle-warnings-as land in payload."""
    steps = _patch_step_scenario(patch_client)
    result = runner.invoke(
        app,
        [
            "scenario",
            "add-step-build",
            "scen1",
            "--name",
            "Build core",
            "--build",
            "sales_clean",
            "--max-retries",
            "3",
            "--delay-between-retries",
            "60",
            "--handle-warnings-as",
            "FAILED",
            "--refresh-metastore",
            "--stop-at-zone-boundary",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert len(steps) == 1
    step = steps[0]
    assert step["type"] == "build_flowitem"
    assert step["maxRetriesOnFail"] == 3
    assert step["delayBetweenRetries"] == 60
    assert step["params"]["handleWarningsAs"] == "FAILED"
    assert step["params"]["refreshHiveMetastore"] is True
    assert step["params"]["stopAtFlowZoneBoundary"] is True


def test_add_step_build_run_condition_expression_implies_type(patch_client):
    """--run-condition-expression alone implies type RUN_CONDITIONALLY."""
    steps = _patch_step_scenario(patch_client)
    result = runner.invoke(
        app,
        [
            "scenario",
            "add-step-build",
            "scen1",
            "--name",
            "Conditional",
            "--build",
            "sales_clean",
            "--run-condition-expression",
            "stepOutcome('previous') == 'SUCCESS'",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    step = steps[0]
    assert step["runConditionType"] == "RUN_CONDITIONALLY"
    assert "stepOutcome" in step["runConditionExpression"]


def test_add_step_build_delay_without_retries_errors(patch_client):
    """--delay-between-retries requires --max-retries."""
    _patch_step_scenario(patch_client)
    result = runner.invoke(
        app,
        [
            "scenario",
            "add-step-build",
            "scen1",
            "--name",
            "Bad",
            "--build",
            "ds",
            "--delay-between-retries",
            "30",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "max-retries" in result.output.lower()


def test_add_step_build_invalid_handle_warnings_errors(patch_client):
    _patch_step_scenario(patch_client)
    result = runner.invoke(
        app,
        [
            "scenario",
            "add-step-build",
            "scen1",
            "--name",
            "Bad",
            "--build",
            "ds",
            "--handle-warnings-as",
            "BOGUS",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "BOGUS" in result.output


def test_add_step_build_invalid_job_type_rejected_with_suggestion(patch_client):
    """A bogus jobType saves as null and NPEs at run time — reject client-side
    and suggest the correct value."""
    _patch_step_scenario(patch_client)
    result = runner.invoke(
        app,
        [
            "scenario",
            "add-step-build",
            "scen1",
            "--name",
            "Bad",
            "--build",
            "ds",
            "--job-type",
            "FORCED_RECURSIVE_BUILD",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "Invalid --job-type" in result.output
    assert "RECURSIVE_FORCED_BUILD" in result.output


def test_add_step_build_valid_job_type_accepted(patch_client):
    steps = _patch_step_scenario(patch_client)
    result = runner.invoke(
        app,
        [
            "scenario",
            "add-step-build",
            "scen1",
            "--name",
            "Good",
            "--build",
            "ds",
            "--job-type",
            "RECURSIVE_FORCED_BUILD",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert steps[-1]["params"]["jobType"] == "RECURSIVE_FORCED_BUILD"


def test_add_step_clear_items(patch_client):
    """clear_items step writes clears[] (NOT items[]) and type=clear_items."""
    steps = _patch_step_scenario(patch_client)
    result = runner.invoke(
        app,
        [
            "scenario",
            "add-step-clear-items",
            "scen1",
            "--name",
            "Wipe staging",
            "--clear",
            "staging_orders",
            "--clear",
            "OTHER_PROJ.shared_dim",
            "--clear-folder",
            "REPORTS",
            "--clear-model",
            "abc123",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert len(steps) == 1
    step = steps[0]
    assert step["type"] == "clear_items"
    # DSS uses params.clears[] for clear_items, not params.items[]
    assert "items" not in step["params"]
    clears = step["params"]["clears"]
    assert clears[0] == {
        "type": "DATASET",
        "itemId": "staging_orders",
        "partitionsSpec": "",
    }
    assert clears[1] == {
        "type": "DATASET",
        "projectKey": "OTHER_PROJ",
        "itemId": "shared_dim",
        "partitionsSpec": "",
    }
    assert clears[2] == {
        "type": "MANAGED_FOLDER",
        "itemId": "REPORTS",
        "partitionsSpec": "",
    }
    assert clears[3] == {
        "type": "SAVED_MODEL",
        "itemId": "abc123",
        "partitionsSpec": "",
    }


def test_add_step_propagate_schema(patch_client):
    """schema_propagation params nest under options (PropagateSchemaTile shape)."""
    steps = _patch_step_scenario(patch_client)
    result = runner.invoke(
        app,
        [
            "scenario",
            "add-step-propagate-schema",
            "scen1",
            "--name",
            "Propagate",
            "--dataset",
            "raw_orders",
            "--behavior",
            "AUTO_WITH_BUILDS",
            "--exclude-recipe",
            "drop_pii",
            "--mark-as-ok-recipe",
            "legacy_join",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    step = steps[0]
    assert step["type"] == "schema_propagation"
    opts = step["params"]["options"]
    assert opts["datasetName"] == "raw_orders"
    assert opts["behavior"] == "AUTO_WITH_BUILDS"
    assert opts["excludedRecipes"] == ["drop_pii"]
    assert opts["markAsOkRecipes"] == ["legacy_join"]


def test_add_step_propagate_schema_invalid_behavior(patch_client):
    _patch_step_scenario(patch_client)
    result = runner.invoke(
        app,
        [
            "scenario",
            "add-step-propagate-schema",
            "scen1",
            "--name",
            "Bad",
            "--dataset",
            "x",
            "--behavior",
            "BOGUS",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "Invalid --behavior" in result.output


def test_add_step_prepare_lambda_package(patch_client):
    steps = _patch_step_scenario(patch_client)
    result = runner.invoke(
        app,
        [
            "scenario",
            "add-step-prepare-lambda-package",
            "scen1",
            "--name",
            "Build pkg",
            "--api-service",
            "fraud_score",
            "--package-id",
            "v42",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    step = steps[0]
    assert step["type"] == "prepare_lambda_package"
    assert step["params"]["serviceId"] == "fraud_score"
    assert step["params"]["packageId"] == "v42"


def test_add_step_update_deployment(patch_client):
    steps = _patch_step_scenario(patch_client)
    result = runner.invoke(
        app,
        [
            "scenario",
            "add-step-update-deployment",
            "scen1",
            "--name",
            "Roll forward",
            "--deployment-id",
            "fraud_v1",
            "--package-id",
            "v42",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    step = steps[0]
    assert step["type"] == "update_apideployer_deployment"
    assert step["params"]["deploymentId"] == "fraud_v1"
    assert step["params"]["newVersionId"] == "v42"


def test_add_step_refresh_chart_cache_item_shape(patch_client):
    """dashboards/datasets are List<RefreshItem> ({smartName, name}), not strings."""
    steps = _patch_step_scenario(patch_client)
    result = runner.invoke(
        app,
        [
            "scenario",
            "add-step-refresh-chart-cache",
            "scen1",
            "--name",
            "Warm cache",
            "--dashboard",
            "exec_kpis",
            "--dataset",
            "sales_clean",
            "--force",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    step = steps[0]
    assert step["type"] == "refresh_chart_cache"
    assert step["params"]["dashboards"] == [
        {"smartName": "exec_kpis", "name": "exec_kpis"}
    ]
    assert step["params"]["datasets"] == [
        {"smartName": "sales_clean", "name": "sales_clean"}
    ]
    assert step["params"]["force"] is True


def test_add_step_build_run_condition_type_alias_suggestion(patch_client):
    """Legacy/invented run-condition values are rejected, real enum suggested."""
    _patch_step_scenario(patch_client)
    result = runner.invoke(
        app,
        [
            "scenario",
            "add-step-build",
            "scen1",
            "--name",
            "Bad",
            "--build",
            "ds",
            "--run-condition-type",
            "ALWAYS",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "RUN_ALWAYS" in result.output


def test_add_step_build_handle_warnings_alias_suggestion(patch_client):
    """AS_FAILURE (not a real Outcome) is rejected with FAILED suggested."""
    _patch_step_scenario(patch_client)
    result = runner.invoke(
        app,
        [
            "scenario",
            "add-step-build",
            "scen1",
            "--name",
            "Bad",
            "--build",
            "ds",
            "--handle-warnings-as",
            "AS_FAILURE",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "FAILED" in result.output


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
        [
            "--format",
            "json",
            "scenario",
            "list-reporters",
            "nightly",
            "--project",
            "PROJ1",
        ],
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


def test_scenario_add_reporter_custom_expression(patch_client):
    """A non-keyword expression becomes the raw runCondition."""
    settings = _set_reporters(patch_client, [])
    expr = 'outcome == "SUCCESS" && parseInt(variables["fraud_count"]) > 0'
    result = runner.invoke(
        app,
        [
            "scenario",
            "add-reporter",
            "alerts",
            "--recipient",
            "ops@example.com",
            "--condition",
            expr,
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "custom-condition" in result.output
    reporter = settings.raw_reporters[0]
    assert reporter["runCondition"] == expr
    assert reporter["runConditionEnabled"] is True


def test_scenario_add_reporter_bare_word_typo_still_errors(patch_client):
    """Typo protection: a single bare word that isn't a keyword stays an error."""
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
            "succes",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "Unknown condition" in result.output
    assert "raw run-condition expression" in result.output
    settings.save.assert_not_called()


# ── set-code on step-based scenarios (#266) ─────────────────────────────


def _steps_scenario(patch_client, steps):
    proj = patch_client.get_project("PROJ1")
    settings = proj.get_scenario("scen1").get_settings.return_value
    type(settings).raw_steps = property(lambda self: steps)
    return settings


def _script_scenario(patch_client):
    proj = patch_client.get_project("PROJ1")
    scenario = proj.get_scenario("scen1")
    del scenario.get_settings.return_value.raw_steps
    return scenario


def test_set_code_bare_on_step_based_errors(patch_client):
    settings = _steps_scenario(
        patch_client, [{"type": "custom_python", "name": "s0", "params": {}}]
    )
    result = runner.invoke(
        app,
        ["scenario", "set-code", "scen1", "--code", "print(1)", "--project", "PROJ1"],
    )
    assert result.exit_code != 0
    assert "step-based" in result.output
    assert "--step" in result.output
    settings.save.assert_not_called()


def test_set_code_step_by_index_writes_script(patch_client):
    steps = [{"type": "custom_python", "name": "s0", "params": {"script": "old"}}]
    settings = _steps_scenario(patch_client, steps)
    result = runner.invoke(
        app,
        [
            "scenario",
            "set-code",
            "scen1",
            "--step",
            "0",
            "--code",
            "print(2)",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert steps[0]["params"]["script"] == "print(2)"
    settings.save.assert_called_once()


def test_set_code_step_by_name_writes_script(patch_client):
    steps = [
        {"type": "build_flowitem", "name": "build", "params": {}},
        {"type": "custom_python", "name": "notify", "params": {}},
    ]
    _steps_scenario(patch_client, steps)
    result = runner.invoke(
        app,
        [
            "scenario",
            "set-code",
            "scen1",
            "--step",
            "notify",
            "--code",
            "print(3)",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert steps[1]["params"]["script"] == "print(3)"


def test_set_code_step_wrong_type_errors(patch_client):
    steps = [{"type": "build_flowitem", "name": "build", "params": {}}]
    settings = _steps_scenario(patch_client, steps)
    result = runner.invoke(
        app,
        [
            "scenario",
            "set-code",
            "scen1",
            "--step",
            "build",
            "--code",
            "x",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "custom_python" in result.output
    settings.save.assert_not_called()


def test_set_code_step_index_out_of_range(patch_client):
    _steps_scenario(patch_client, [])
    result = runner.invoke(
        app,
        [
            "scenario",
            "set-code",
            "scen1",
            "--step",
            "3",
            "--code",
            "x",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "out of range" in result.output


def test_set_code_step_unknown_name(patch_client):
    _steps_scenario(
        patch_client, [{"type": "custom_python", "name": "s0", "params": {}}]
    )
    result = runner.invoke(
        app,
        [
            "scenario",
            "set-code",
            "scen1",
            "--step",
            "nope",
            "--code",
            "x",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "No step named 'nope'" in result.output
    assert "list-steps" in result.output


def test_set_code_step_on_script_scenario_errors(patch_client):
    scenario = _script_scenario(patch_client)
    result = runner.invoke(
        app,
        [
            "scenario",
            "set-code",
            "scen1",
            "--step",
            "0",
            "--code",
            "x",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "script-based" in result.output
    scenario.set_payload.assert_not_called()


def test_set_code_bare_on_script_scenario_ok(patch_client):
    scenario = _script_scenario(patch_client)
    result = runner.invoke(
        app,
        ["scenario", "set-code", "scen1", "--code", "print(9)", "--project", "PROJ1"],
    )
    assert result.exit_code == 0, result.output
    scenario.set_payload.assert_called_once_with("print(9)")


# ── add-step fail-fast on plugin step types (#267) ──────────────────────


def test_add_step_plugin_type_fails_fast(patch_client):
    steps = _patch_step_scenario(patch_client)
    result = runner.invoke(
        app,
        [
            "scenario",
            "add-step",
            "scen1",
            "--type",
            "pystep_myplugin_dostuff",
            "--name",
            "Plug",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "plugin-provided" in result.output
    assert "dku plugin components" in result.output
    assert "add-step-python" in result.output
    assert steps == []


def test_add_step_unknown_nonplugin_type_still_warns_and_proceeds(patch_client):
    steps = _patch_step_scenario(patch_client)
    result = runner.invoke(
        app,
        [
            "scenario",
            "add-step",
            "scen1",
            "--type",
            "mystery_step",
            "--name",
            "Odd",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "proceeding anyway" in result.output
    assert steps[0]["type"] == "mystery_step"
