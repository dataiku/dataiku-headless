"""Tests for workspace commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_workspace_list_table(patch_client):
    result = runner.invoke(app, ["workspace", "list"])
    assert result.exit_code == 0
    assert "ANALYTICS" in result.output
    assert "Analytics Hub" in result.output


def test_workspace_list_json(patch_client):
    result = runner.invoke(app, ["--format", "json", "workspace", "list"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 1
    assert parsed[0]["workspaceKey"] == "ANALYTICS"


def test_workspace_list_empty(patch_client):
    patch_client.list_workspaces.return_value = []
    result = runner.invoke(app, ["workspace", "list"])
    assert result.exit_code == 0
    assert "no workspaces" in result.output.lower()


def test_workspace_create(patch_client):
    result = runner.invoke(
        app, ["workspace", "create", "TEAM_DS", "--name", "Data Science"]
    )
    assert result.exit_code == 0
    assert "Created" in result.output
    patch_client.create_workspace.assert_called_once_with(
        "TEAM_DS", "Data Science", description=None, color=None
    )


def test_workspace_create_json(patch_client):
    result = runner.invoke(
        app, ["--format", "json", "workspace", "create", "TEST", "--name", "Test"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["key"] == "TEST"


def test_workspace_get(patch_client):
    result = runner.invoke(app, ["workspace", "get", "ANALYTICS"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["displayName"] == "Analytics Hub"


def test_workspace_list_objects_table(patch_client):
    result = runner.invoke(app, ["workspace", "list-objects", "ANALYTICS"])
    assert result.exit_code == 0
    assert "DATASET" in result.output
    assert "sales_data" in result.output


def test_workspace_list_objects_json(patch_client):
    result = runner.invoke(
        app, ["--format", "json", "workspace", "list-objects", "ANALYTICS"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 1
    assert parsed[0]["reference"]["type"] == "DATASET"


def test_workspace_list_objects_empty(patch_client):
    ws = patch_client.get_workspace("ANALYTICS")
    ws.list_objects.return_value = []
    result = runner.invoke(app, ["workspace", "list-objects", "ANALYTICS"])
    assert result.exit_code == 0
    assert "no objects" in result.output.lower()


def test_workspace_delete(patch_client):
    result = runner.invoke(app, ["workspace", "delete", "ANALYTICS", "--yes"])
    assert result.exit_code == 0
    assert "Deleted" in result.output
    ws = patch_client.get_workspace("ANALYTICS")
    ws.delete.assert_called_once()
