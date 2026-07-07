"""Tests for agent-hub commands.

Scope is intentionally narrow: list / config / set-config / start / stop.

The pre-existing `set-llm`, `add-agent`, `remove-agent`, `set-agent`,
`list-agents` verbs were removed because they wrote/read schema keys
(`default_llm_id`, `agents_ids`, `tool_agent_configurations`, ...) that
the agent-hub plugin does NOT actually read on real DSS — the plugin
stores its UI configuration in a private SQLite store, not the webapp
`config` field. Verified live against DSS 14.5.1 + agent-hub v1.2.4 / v1.3.2.
"""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


def test_list(patch_client):
    result = runner.invoke(app, ["agent-hub", "list", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "hub1" in result.output
    assert "Agent Hub" in result.output
    # Standard webapp should be filtered out
    assert "Dashboard" not in result.output


def test_list_json(patch_client):
    result = runner.invoke(
        app, ["--format", "json", "agent-hub", "list", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 1
    assert parsed[0]["id"] == "hub1"


# ---------------------------------------------------------------------------
# config — real schema is just {log_level, storage_type}
# ---------------------------------------------------------------------------


def test_config(patch_client):
    result = runner.invoke(app, ["agent-hub", "config", "--project", "PROJ1"])
    assert result.exit_code == 0
    # The output shows the plugin-runtime config keys only.
    assert "log_level" in result.output


def test_config_json(patch_client):
    result = runner.invoke(
        app, ["--format", "json", "agent-hub", "config", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    # Real hubs (verified on DSS 14.5.1) expose exactly these two keys here.
    assert "log_level" in parsed
    assert "storage_type" in parsed


def test_config_explicit_hub(patch_client):
    """--hub flag selects a specific hub."""
    result = runner.invoke(
        app, ["agent-hub", "config", "--hub", "hub1", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "log_level" in result.output


# ---------------------------------------------------------------------------
# set-config — only useful for plugin-runtime knobs (log_level, storage_type)
# ---------------------------------------------------------------------------


def test_set_config(patch_client):
    result = runner.invoke(
        app,
        [
            "agent-hub",
            "set-config",
            "--definition",
            '{"log_level": "DEBUG"}',
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    hub = patch_client.get_project("PROJ1").get_webapp("hub1")
    hub.get_settings().save.assert_called()


# ---------------------------------------------------------------------------
# start / stop
# ---------------------------------------------------------------------------


def test_start(patch_client):
    result = runner.invoke(app, ["agent-hub", "start", "--project", "PROJ1"])
    assert result.exit_code == 0
    hub = patch_client.get_project("PROJ1").get_webapp("hub1")
    hub.start_or_restart_backend.assert_called()
    # Fixture hub has storage_type=LOCAL — start must warn about containerized
    # instances requiring REMOTE storage.
    assert "REMOTE" in result.output


def test_start_waits_for_boot(patch_client):
    """start must wait on the backend future, not fire-and-forget."""
    hub = patch_client.get_project("PROJ1").get_webapp("hub1")
    result = runner.invoke(app, ["agent-hub", "start", "--project", "PROJ1"])
    assert result.exit_code == 0
    hub.start_or_restart_backend.return_value.wait_for_result.assert_called()


def test_start_boot_failure_remote_db(patch_client):
    """Boot exception mentioning the remote-db requirement gets the fix."""
    from dataikuapi.utils import DataikuException

    hub = patch_client.get_project("PROJ1").get_webapp("hub1")
    hub.start_or_restart_backend.return_value.wait_for_result.side_effect = (
        DataikuException("running backend in a docker container requires a remote db")
    )
    result = runner.invoke(app, ["agent-hub", "start", "--project", "PROJ1"])
    assert result.exit_code != 0
    assert "storage_type" in result.output
    assert "REMOTE" in result.output


def test_start_crash_loop_detected(patch_client):
    """Backend 'starts' but crash-loops — the crash tail is surfaced."""
    hub = patch_client.get_project("PROJ1").get_webapp("hub1")
    hub.get_state.return_value.state = {
        "lastCrashLogTail": {
            "lines": [
                "ERROR Running backend in a Docker container requires a remote db",
            ]
        }
    }
    result = runner.invoke(app, ["agent-hub", "start", "--project", "PROJ1"])
    assert result.exit_code != 0
    assert "crash-looping" in result.output
    assert "REMOTE" in result.output


def test_stop(patch_client):
    result = runner.invoke(app, ["agent-hub", "stop", "--project", "PROJ1"])
    assert result.exit_code == 0
    hub = patch_client.get_project("PROJ1").get_webapp("hub1")
    hub.stop_backend.assert_called()


# ---------------------------------------------------------------------------
# hub resolution edge cases
# ---------------------------------------------------------------------------


def test_no_hub_found(patch_client):
    """Error when no Agent Hub webapp exists in the project."""
    proj = patch_client.get_project("PROJ1")
    proj.list_webapps.return_value = [
        {"id": "webapp1", "name": "Dashboard", "type": "STANDARD"},
    ]
    result = runner.invoke(app, ["agent-hub", "config", "--project", "PROJ1"])
    assert result.exit_code != 0
    assert "No Agent Hub" in result.output


def test_multiple_hubs_no_flag(patch_client):
    """Error when multiple hubs exist and --hub not provided."""
    proj = patch_client.get_project("PROJ1")
    proj.list_webapps.return_value = [
        {"id": "hub1", "name": "Hub 1", "type": "webapp_agent-hub_agent-hub"},
        {"id": "hub2", "name": "Hub 2", "type": "webapp_agent-hub_agent-hub"},
    ]
    result = runner.invoke(app, ["agent-hub", "config", "--project", "PROJ1"])
    assert result.exit_code != 0
    assert "--hub" in result.output
