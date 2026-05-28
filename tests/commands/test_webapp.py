"""Tests for webapp commands."""

from __future__ import annotations

import json

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


def test_webapp_restart(patch_client):
    result = runner.invoke(app, ["webapp", "restart", "webapp1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "Restarted" in result.output


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
    """Prescriptive error when backend is stopped (no currentLogTail)."""
    # Override the webapp state for this test: no currentLogTail, not running.
    proj = patch_client.get_project("PROJ1")
    webapp = proj.get_webapp("webapp1")
    state = webapp.get_state()
    state.running = False
    state.state = {
        "projectKey": "PROJ1",
        "webAppId": "webapp1",
        "hasExposedEndpoint": False,
        # NOTE: no `currentLogTail` — mirrors real DSS behavior when stopped.
    }
    result = runner.invoke(app, ["webapp", "logs", "webapp1", "-P", "PROJ1"])
    assert result.exit_code != 0
    assert "backend is not running" in result.output
    assert "dku webapp start webapp1 -P PROJ1" in result.output


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
