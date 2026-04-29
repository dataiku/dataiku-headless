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
