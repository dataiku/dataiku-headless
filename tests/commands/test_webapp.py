"""Tests for webapp commands."""

from __future__ import annotations

import json
from types import SimpleNamespace

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


# ── create ─────────────────────────────────────────────────────────────


def test_webapp_create_default_type(patch_client):
    result = runner.invoke(app, ["webapp", "create", "MyApp", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "Created STANDARD web app 'MyApp'" in result.output
    assert "newWebApp1" in result.output
    patch_client.get_project("PROJ1").create_webapp.assert_called_once_with(
        "MyApp", webapp_type="STANDARD"
    )


def test_webapp_create_dash(patch_client):
    result = runner.invoke(
        app, ["webapp", "create", "DashApp", "--project", "PROJ1", "--type", "DASH"]
    )
    assert result.exit_code == 0
    assert "Created DASH web app 'DashApp'" in result.output
    patch_client.get_project("PROJ1").create_webapp.assert_called_once_with(
        "DashApp", webapp_type="DASH"
    )


def test_webapp_create_streamlit(patch_client):
    result = runner.invoke(
        app, ["webapp", "create", "StreamApp", "-P", "PROJ1", "-t", "streamlit"]
    )
    assert result.exit_code == 0
    assert "STREAMLIT" in result.output


def test_webapp_create_invalid_type(patch_client):
    result = runner.invoke(
        app, ["webapp", "create", "BadApp", "--project", "PROJ1", "--type", "INVALID"]
    )
    assert result.exit_code != 0
    assert "Unsupported web app type" in result.output


# ── list ───────────────────────────────────────────────────────────────


def test_webapp_list(patch_client):
    result = runner.invoke(app, ["webapp", "list", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "webapp1" in result.output


def test_webapp_list_json(patch_client):
    result = runner.invoke(app, ["webapp", "list", "--project", "PROJ1", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["id"] == "webapp1"


def test_webapp_start(patch_client):
    result = runner.invoke(app, ["webapp", "start", "webapp1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "Started" in result.output


def test_webapp_start_crash_surfaces_error(patch_client):
    """start exits non-zero and prints crash reason when the boot future fails."""
    from dataikuapi.utils import DataikuException

    proj = patch_client.get_project("PROJ1")
    webapp = proj.get_webapp("webapp1")
    future = webapp.start_or_restart_backend()
    future.wait_for_result.side_effect = DataikuException(
        "BackendStartFailedException: No module named 'uvicorn_worker'"
    )
    # Also give the webapp a lastCrashLogTail so _print_crash_tail can fire.
    webapp.get_state().state = {
        "projectKey": "PROJ1",
        "webAppId": "webapp1",
        "lastCrashLogTail": {
            "totalLines": 3,
            "lines": [
                "ERROR Backend main loop failed",
                "ModuleNotFoundError: No module named 'uvicorn_worker'",
            ],
        },
    }
    webapp.get_state().running = False
    result = runner.invoke(app, ["webapp", "start", "webapp1", "--project", "PROJ1"])
    assert result.exit_code != 0
    assert "failed to start" in result.output
    assert "uvicorn_worker" in result.output


def test_webapp_restart(patch_client):
    result = runner.invoke(app, ["webapp", "restart", "webapp1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "Restarted" in result.output


def test_webapp_restart_crash_surfaces_error(patch_client):
    """restart exits non-zero and prints crash reason when the boot future fails."""
    from dataikuapi.utils import DataikuException

    proj = patch_client.get_project("PROJ1")
    webapp = proj.get_webapp("webapp1")
    future = webapp.start_or_restart_backend()
    future.wait_for_result.side_effect = DataikuException(
        "BackendStartFailedException: No module named 'uvicorn_worker'"
    )
    webapp.get_state().running = False
    result = runner.invoke(app, ["webapp", "restart", "webapp1", "--project", "PROJ1"])
    assert result.exit_code != 0
    assert "failed to start" in result.output
    assert "uvicorn_worker" in result.output


def test_webapp_stop(patch_client):
    result = runner.invoke(app, ["webapp", "stop", "webapp1", "--project", "PROJ1"])
    assert result.exit_code == 0


def test_webapp_status(patch_client):
    result = runner.invoke(app, ["webapp", "status", "webapp1", "--project", "PROJ1"])
    assert result.exit_code == 0


def test_webapp_status_json(patch_client):
    result = runner.invoke(
        app, ["webapp", "status", "webapp1", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert any(d["value"] == "True" for d in parsed)


# ── get-definition / set-definition ─────────────────────────────────────


def test_webapp_get_definition(patch_client):
    result = runner.invoke(
        app, ["webapp", "get-definition", "webapp1", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["type"] == "STANDARD"
    assert parsed["params"]["html"] == "<h1>Hello</h1>"


def test_webapp_get_definition_json_flag(patch_client):
    result = runner.invoke(
        app, ["webapp", "get-definition", "webapp1", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["name"] == "Dashboard"


def test_webapp_set_definition(patch_client):
    new_def = json.dumps(
        {"type": "STANDARD", "name": "Updated", "params": {"html": "<h2>New</h2>"}}
    )
    result = runner.invoke(
        app,
        [
            "webapp",
            "set-definition",
            "webapp1",
            "--project",
            "PROJ1",
            "--definition",
            new_def,
        ],
    )
    assert result.exit_code == 0
    assert "Updated definition" in result.output
    proj = patch_client.get_project("PROJ1")
    webapp = proj.get_webapp("webapp1")
    webapp.get_settings().save.assert_called_once()


def test_webapp_set_definition_from_file(tmp_path, patch_client):
    defn_file = tmp_path / "webapp_def.json"
    defn_file.write_text(
        json.dumps({"type": "STANDARD", "name": "FromFile", "params": {}})
    )
    result = runner.invoke(
        app,
        [
            "webapp",
            "set-definition",
            "webapp1",
            "--project",
            "PROJ1",
            "--definition",
            f"@{defn_file}",
        ],
    )
    assert result.exit_code == 0
    assert "Updated definition" in result.output
    proj = patch_client.get_project("PROJ1")
    webapp = proj.get_webapp("webapp1")
    webapp.get_settings().save.assert_called_once()


# ── logs ───────────────────────────────────────────────────────────────


def test_webapp_logs_default_text(patch_client):
    """Default output is plain text, one line per row, no decoration."""
    result = runner.invoke(app, ["webapp", "logs", "webapp1", "-P", "PROJ1"])
    assert result.exit_code == 0
    assert "[2026-05-28 12:00:00] INFO startup" in result.output
    assert "[2026-05-28 12:00:01] INFO listening on 5000" in result.output
    assert "[2026-05-28 12:00:02] ERROR something broke" in result.output


def test_webapp_logs_tail_limit(patch_client):
    """--tail N keeps only the last N lines."""
    result = runner.invoke(
        app, ["webapp", "logs", "webapp1", "-P", "PROJ1", "--tail", "1"]
    )
    assert result.exit_code == 0
    assert "[2026-05-28 12:00:02] ERROR something broke" in result.output
    # The earlier two lines must be filtered out.
    assert "INFO startup" not in result.output
    assert "INFO listening" not in result.output


def test_webapp_logs_tail_rejects_zero(patch_client):
    """--tail 0 is a usage error — prescriptive guidance, non-zero exit."""
    result = runner.invoke(
        app, ["webapp", "logs", "webapp1", "-P", "PROJ1", "--tail", "0"]
    )
    assert result.exit_code != 0
    assert "must be a positive integer" in result.output


def test_webapp_logs_json_output(patch_client):
    """-o json emits the structured payload with all metadata."""
    result = runner.invoke(
        app, ["webapp", "logs", "webapp1", "-P", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["webappId"] == "webapp1"
    assert payload["projectKey"] == "PROJ1"
    assert payload["running"] is True
    assert payload["totalLines"] == 120
    assert payload["returnedLines"] == 3
    assert payload["serverTailSize"] == 3
    assert len(payload["lines"]) == 3


def test_webapp_logs_json_with_tail(patch_client):
    """--tail filters the JSON lines too; serverTailSize stays accurate."""
    result = runner.invoke(
        app, ["webapp", "logs", "webapp1", "-P", "PROJ1", "-o", "json", "--tail", "2"]
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["returnedLines"] == 2
    assert payload["serverTailSize"] == 3  # full tail received before trim
    assert payload["lines"][-1] == "[2026-05-28 12:00:02] ERROR something broke"


def test_webapp_logs_follow_rejects_json(patch_client):
    """--follow cannot combine with -o json (text-only streaming)."""
    result = runner.invoke(
        app, ["webapp", "logs", "webapp1", "-P", "PROJ1", "-f", "-o", "json"]
    )
    assert result.exit_code != 0
    assert "cannot be combined" in result.output


def test_webapp_logs_backend_not_running(patch_client):
    """Prescriptive error when backend is stopped and there are no crash logs either."""
    proj = patch_client.get_project("PROJ1")
    webapp = proj.get_webapp("webapp1")
    state = webapp.get_state()
    state.running = False
    state.state = {
        "projectKey": "PROJ1",
        "webAppId": "webapp1",
        "hasExposedEndpoint": False,
        # NOTE: neither currentLogTail nor lastCrashLogTail — mirrors DSS
        # behaviour for a backend that was stopped cleanly (never crashed).
    }
    result = runner.invoke(app, ["webapp", "logs", "webapp1", "-P", "PROJ1"])
    assert result.exit_code != 0
    assert "backend is not running" in result.output
    assert "dku webapp start webapp1 -P PROJ1" in result.output


def test_webapp_logs_shows_crash_tail(patch_client):
    """Falls back to lastCrashLogTail and prints a warning banner (text mode)."""
    proj = patch_client.get_project("PROJ1")
    webapp = proj.get_webapp("webapp1")
    state = webapp.get_state()
    state.running = False
    state.state = {
        "projectKey": "PROJ1",
        "webAppId": "webapp1",
        # No currentLogTail (backend died), but lastCrashLogTail is present.
        "lastCrashLogTail": {
            "totalLines": 2,
            "lines": [
                "ERROR Backend main loop failed",
                "ModuleNotFoundError: No module named 'uvicorn_worker'",
            ],
        },
    }
    result = runner.invoke(app, ["webapp", "logs", "webapp1", "-P", "PROJ1"])
    assert result.exit_code == 0
    assert "crash log" in result.output.lower()
    assert "ModuleNotFoundError" in result.output
    assert "uvicorn_worker" in result.output


def test_webapp_logs_crash_tail_json(patch_client):
    """lastCrashLogTail is flagged with crashed=true and source in -o json output."""
    proj = patch_client.get_project("PROJ1")
    webapp = proj.get_webapp("webapp1")
    state = webapp.get_state()
    state.running = False
    state.state = {
        "projectKey": "PROJ1",
        "webAppId": "webapp1",
        "lastCrashLogTail": {
            "totalLines": 1,
            "lines": ["ModuleNotFoundError: No module named 'uvicorn_worker'"],
        },
    }
    result = runner.invoke(
        app, ["webapp", "logs", "webapp1", "-P", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["crashed"] is True
    assert payload["source"] == "lastCrashLogTail"
    assert payload["running"] is False
    assert "uvicorn_worker" in payload["lines"][0]


def test_webapp_logs_follow_refuses_crash_tail(patch_client):
    """--follow exits non-zero when backend has a crash tail (can't stream stopped)."""
    proj = patch_client.get_project("PROJ1")
    webapp = proj.get_webapp("webapp1")
    state = webapp.get_state()
    state.running = False
    state.state = {
        "projectKey": "PROJ1",
        "webAppId": "webapp1",
        "lastCrashLogTail": {
            "totalLines": 1,
            "lines": ["ModuleNotFoundError: No module named 'uvicorn_worker'"],
        },
    }
    result = runner.invoke(
        app, ["webapp", "logs", "webapp1", "-P", "PROJ1", "--follow"]
    )
    assert result.exit_code != 0
    assert "not running" in result.output.lower()


def test_webapp_logs_follow_exits_if_backend_crashes_during_poll(
    patch_client, monkeypatch
):
    """--follow exits when a live backend switches to lastCrashLogTail."""
    proj = patch_client.get_project("PROJ1")
    webapp = proj.get_webapp("webapp1")
    webapp.get_state.side_effect = [
        SimpleNamespace(
            running=True,
            state={
                "projectKey": "PROJ1",
                "webAppId": "webapp1",
                "currentLogTail": {
                    "totalLines": 1,
                    "lines": ["INFO startup"],
                },
            },
        ),
        SimpleNamespace(
            running=False,
            state={
                "projectKey": "PROJ1",
                "webAppId": "webapp1",
                "lastCrashLogTail": {
                    "totalLines": 2,
                    "lines": [
                        "ERROR Backend main loop failed",
                        "ModuleNotFoundError: No module named 'uvicorn_worker'",
                    ],
                },
            },
        ),
    ]
    monkeypatch.setattr("dku_cli.commands.webapp.time.sleep", lambda _seconds: None)

    result = runner.invoke(
        app, ["webapp", "logs", "webapp1", "-P", "PROJ1", "--follow"]
    )

    assert result.exit_code != 0
    assert "INFO startup" in result.output
    assert "cannot follow logs" in result.output
    assert "without --follow" in result.output


def test_webapp_logs_running_but_no_tail_yet(patch_client):
    """Just-started backend may be running with no tail yet — empty success."""
    proj = patch_client.get_project("PROJ1")
    webapp = proj.get_webapp("webapp1")
    state = webapp.get_state()
    state.running = True
    state.state = {"projectKey": "PROJ1", "webAppId": "webapp1"}
    result = runner.invoke(
        app, ["webapp", "logs", "webapp1", "-P", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["totalLines"] == 0
    assert payload["lines"] == []
    assert payload["running"] is True


def test_webapp_logs_grep_filter(patch_client):
    """--grep keeps only matching lines (case-insensitive)."""
    result = runner.invoke(
        app, ["webapp", "logs", "webapp1", "-P", "PROJ1", "--grep", "error"]
    )
    assert result.exit_code == 0
    assert "[2026-05-28 12:00:02] ERROR something broke" in result.output
    assert "INFO startup" not in result.output
    assert "INFO listening" not in result.output


def test_webapp_logs_grep_json(patch_client):
    """--grep narrows the JSON lines; serverTailSize reflects the full tail."""
    result = runner.invoke(
        app,
        ["webapp", "logs", "webapp1", "-P", "PROJ1", "-o", "json", "--grep", "INFO"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["returnedLines"] == 2
    assert payload["serverTailSize"] == 3
    assert all("INFO" in line for line in payload["lines"])


def test_webapp_logs_follow_streams_seed(patch_client, monkeypatch):
    """--follow prints the seed tail, then stops cleanly on Ctrl-C."""

    def _stop(_seconds):
        raise KeyboardInterrupt

    monkeypatch.setattr("dku_cli.commands.webapp.time.sleep", _stop)
    result = runner.invoke(
        app, ["webapp", "logs", "webapp1", "-P", "PROJ1", "--follow"]
    )
    assert result.exit_code == 0
    assert "[2026-05-28 12:00:00] INFO startup" in result.output
    assert "[2026-05-28 12:00:02] ERROR something broke" in result.output
    assert "Following webapp1" in result.output
    assert "Stopped." in result.output


def test_webapp_logs_follow_with_grep(patch_client, monkeypatch):
    """--follow honors --grep on the seeded tail."""

    def _stop(_seconds):
        raise KeyboardInterrupt

    monkeypatch.setattr("dku_cli.commands.webapp.time.sleep", _stop)
    result = runner.invoke(
        app,
        ["webapp", "logs", "webapp1", "-P", "PROJ1", "--follow", "--grep", "error"],
    )
    assert result.exit_code == 0
    assert "ERROR something broke" in result.output
    assert "INFO startup" not in result.output
