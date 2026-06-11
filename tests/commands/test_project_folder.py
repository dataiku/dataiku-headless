"""Tests for project folder commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_project_folder_list_table(patch_client):
    result = runner.invoke(app, ["project-folder", "list"])
    assert result.exit_code == 0
    assert "Analytics" in result.output
    assert "PROJ1" in result.output


def test_project_folder_list_json(patch_client):
    result = runner.invoke(app, ["--format", "json", "project-folder", "list"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 2  # root + 1 child
    assert parsed[0]["id"] == "ROOT"
    assert parsed[1]["id"] == "folder1"
    assert parsed[1]["name"] == "Analytics"


def test_project_folder_create(patch_client):
    result = runner.invoke(app, ["project-folder", "create", "ML Models"])
    assert result.exit_code == 0
    assert "Created" in result.output
    # create calls get_project_folder("ROOT") then create_sub_folder
    patch_client.get_project_folder.return_value.create_sub_folder.assert_called_once_with(
        "ML Models"
    )


def test_project_folder_create_json(patch_client):
    result = runner.invoke(
        app, ["--format", "json", "project-folder", "create", "Test"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["name"] == "Test"


def test_project_folder_move_project(patch_client):
    result = runner.invoke(
        app,
        ["project-folder", "move-project", "PROJ1", "--folder", "folder1"],
    )
    assert result.exit_code == 0
    assert "Moved" in result.output
    proj = patch_client.get_project("PROJ1")
    proj.move_to_folder.assert_called_once()
