"""Tests for analysis commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_analysis_list(patch_client):
    result = runner.invoke(app, ["analysis", "list", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "a1" in result.output


def test_analysis_list_json(patch_client):
    result = runner.invoke(
        app, ["--format", "json", "analysis", "list", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["analysis_id"] == "a1"
    assert parsed[0]["dataset"] == "ds1"


def test_analysis_create(patch_client):
    result = runner.invoke(app, ["analysis", "create", "ds1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "Created analysis" in result.output
    patch_client.get_project("PROJ1").create_analysis.assert_called_once_with("ds1")


def test_analysis_get(patch_client):
    result = runner.invoke(
        app, ["--format", "json", "analysis", "get", "a1", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["analysisId"] == "a1"


def test_analysis_get_table(patch_client):
    result = runner.invoke(app, ["analysis", "get", "a1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "analysisId" in result.output


def test_analysis_delete(patch_client):
    result = runner.invoke(
        app, ["analysis", "delete", "a1", "--project", "PROJ1", "--yes"]
    )
    assert result.exit_code == 0
    assert "Deleted analysis" in result.output


def test_analysis_tasks(patch_client):
    result = runner.invoke(app, ["analysis", "tasks", "a1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "t1" in result.output


def test_analysis_tasks_json(patch_client):
    result = runner.invoke(
        app, ["--format", "json", "analysis", "tasks", "a1", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["mltask_id"] == "t1"
