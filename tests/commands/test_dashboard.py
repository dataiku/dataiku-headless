"""Tests for dashboard commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_dashboard_list(patch_client):
    result = runner.invoke(app, ["dashboard", "list", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "dashboard1" in result.output


def test_dashboard_list_json(patch_client):
    result = runner.invoke(app, ["dashboard", "list", "--project", "PROJ1", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["id"] == "dashboard1"
    assert parsed[0]["name"] == "Sales Dashboard"


def test_dashboard_get(patch_client):
    result = runner.invoke(app, ["dashboard", "get", "dashboard1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "dashboard1" in result.output


def test_dashboard_get_tile_count(patch_client):
    """Tile count must read from pages[i].grid.tiles (real DSS structure)."""
    result = runner.invoke(app, ["dashboard", "get", "dashboard1", "--project", "PROJ1"])
    assert result.exit_code == 0
    # conftest fixture has 1 tile in grid.tiles
    assert "1" in result.output


def test_dashboard_get_json(patch_client):
    result = runner.invoke(app, ["dashboard", "get", "dashboard1", "--project", "PROJ1", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["id"] == "dashboard1"
    assert parsed["name"] == "Sales Dashboard"


def test_dashboard_create(patch_client):
    result = runner.invoke(app, ["dashboard", "create", "New Dashboard", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "Created dashboard" in result.output
    assert "new_dashboard_1" in result.output
    proj = patch_client.get_project("PROJ1")
    proj.create_dashboard.assert_called_once_with(dashboard_name="New Dashboard")


def test_dashboard_create_with_definition(patch_client):
    defn = json.dumps({"pages": [{"title": "Page 1"}]})
    result = runner.invoke(
        app,
        ["dashboard", "create", "Custom Dashboard", "--project", "PROJ1", "--definition", defn],
    )
    assert result.exit_code == 0
    assert "Created dashboard" in result.output
    proj = patch_client.get_project("PROJ1")
    call_kwargs = proj.create_dashboard.call_args[1]
    assert call_kwargs["dashboard_name"] == "Custom Dashboard"
    assert call_kwargs["settings"] == {"pages": [{"title": "Page 1"}]}


def test_dashboard_create_if_not_exists(patch_client):
    proj = patch_client.get_project("PROJ1")
    proj.create_dashboard.side_effect = Exception("409 Conflict: dashboard already exists")
    result = runner.invoke(
        app,
        ["dashboard", "create", "Existing", "--project", "PROJ1", "--if-not-exists"],
    )
    assert result.exit_code == 0
    assert "already exists" in result.output


def test_dashboard_create_already_exists_fails(patch_client):
    proj = patch_client.get_project("PROJ1")
    proj.create_dashboard.side_effect = Exception("409 Conflict: dashboard already exists")
    result = runner.invoke(
        app,
        ["dashboard", "create", "Existing", "--project", "PROJ1"],
    )
    assert result.exit_code != 0


def test_dashboard_delete(patch_client):
    result = runner.invoke(app, ["dashboard", "delete", "dashboard1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "Deleted dashboard" in result.output
    proj = patch_client.get_project("PROJ1")
    dashboard = proj.get_dashboard("dashboard1")
    dashboard.delete.assert_called_once()


def test_dashboard_get_definition(patch_client):
    result = runner.invoke(app, ["dashboard", "get-definition", "dashboard1", "--project", "PROJ1"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["id"] == "dashboard1"
    assert parsed["name"] == "Sales Dashboard"
    assert len(parsed["pages"]) == 1


def test_dashboard_set_definition(patch_client):
    new_def = json.dumps({"id": "dashboard1", "name": "Updated", "pages": []})
    result = runner.invoke(
        app,
        ["dashboard", "set-definition", "dashboard1", "--project", "PROJ1", "--definition", new_def],
    )
    assert result.exit_code == 0
    assert "Updated definition" in result.output
    proj = patch_client.get_project("PROJ1")
    dashboard = proj.get_dashboard("dashboard1")
    dashboard.get_settings().save.assert_called_once()


def test_dashboard_set_definition_from_file(tmp_path, patch_client):
    defn_file = tmp_path / "dashboard_def.json"
    defn_file.write_text(json.dumps({"id": "dashboard1", "name": "FromFile", "pages": []}))
    result = runner.invoke(
        app,
        ["dashboard", "set-definition", "dashboard1", "--project", "PROJ1", "--definition", f"@{defn_file}"],
    )
    assert result.exit_code == 0
    assert "Updated definition" in result.output
    proj = patch_client.get_project("PROJ1")
    dashboard = proj.get_dashboard("dashboard1")
    dashboard.get_settings().save.assert_called_once()
