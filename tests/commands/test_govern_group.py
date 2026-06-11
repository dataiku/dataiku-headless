"""Tests for dku govern-group commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_group_list(patch_client):
    result = runner.invoke(app, ["govern", "group", "list"])
    assert result.exit_code == 0
    assert "data_team" in result.output


def test_group_list_json(patch_client):
    result = runner.invoke(app, ["--format", "json", "govern", "group", "list"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 1
    assert data[0]["name"] == "data_team"


def test_group_get(patch_client):
    result = runner.invoke(app, ["govern", "group", "get", "data_team"])
    assert result.exit_code == 0
    assert "data_team" in result.output


def test_group_get_json(patch_client):
    result = runner.invoke(
        app, ["--format", "json", "govern", "group", "get", "data_team"]
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["name"] == "data_team"


def test_group_create(patch_client):
    result = runner.invoke(
        app,
        [
            "govern",
            "group",
            "create",
            "new_group",
            "--description",
            "A new group",
        ],
    )
    assert result.exit_code == 0
    gov = patch_client.get_govern_client()
    gov.create_group.assert_called_once_with(
        "new_group", description="A new group", source_type="LOCAL"
    )


def test_group_delete_requires_confirm(patch_client):
    result = runner.invoke(app, ["govern", "group", "delete", "data_team"])
    assert result.exit_code != 0


def test_group_delete(patch_client):
    result = runner.invoke(app, ["govern", "group", "delete", "data_team", "--confirm"])
    assert result.exit_code == 0
    gov = patch_client.get_govern_client()
    gov.get_group.return_value.delete.assert_called_once()
