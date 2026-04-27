"""Tests for model comparison commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_model_comparison_list_table(patch_client):
    result = runner.invoke(app, ["model-comparison", "list", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "mec1" in result.output
    assert "Churn Models" in result.output


def test_model_comparison_list_json(patch_client):
    result = runner.invoke(
        app, ["model-comparison", "list", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 1
    assert parsed[0]["id"] == "mec1"
    assert parsed[0]["name"] == "Churn Models"


def test_model_comparison_list_empty(patch_client):
    proj = patch_client.get_project("PROJ1")
    proj.list_model_comparisons.return_value = []
    result = runner.invoke(app, ["model-comparison", "list", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "no model comparisons" in result.output.lower()


def test_model_comparison_create(patch_client):
    result = runner.invoke(
        app,
        [
            "model-comparison",
            "create",
            "Test Compare",
            "-t",
            "BINARY_CLASSIFICATION",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created" in result.output
    proj = patch_client.get_project("PROJ1")
    proj.create_model_comparison.assert_called_once_with(
        "Test Compare", "BINARY_CLASSIFICATION"
    )


def test_model_comparison_create_json(patch_client):
    result = runner.invoke(
        app,
        [
            "model-comparison",
            "create",
            "Test",
            "-t",
            "REGRESSION",
            "--project",
            "PROJ1",
            "-o",
            "json",
        ],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["id"] == "mec1"


def test_model_comparison_get(patch_client):
    result = runner.invoke(
        app, ["model-comparison", "get", "mec1", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["displayName"] == "Churn Models"


def test_model_comparison_add_model(patch_client):
    result = runner.invoke(
        app,
        [
            "model-comparison",
            "add-model",
            "mec1",
            "--model",
            "S-PROJ1-model2-v1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Added" in result.output
    mc = patch_client.get_project("PROJ1").get_model_comparison("mec1")
    mc.get_settings().add_compared_item.assert_called_once_with("S-PROJ1-model2-v1")
    mc.get_settings().save.assert_called()


def test_model_comparison_remove_model(patch_client):
    result = runner.invoke(
        app,
        [
            "model-comparison",
            "remove-model",
            "mec1",
            "--model",
            "S-PROJ1-model1-v1",
            "--project",
            "PROJ1",
            "--yes",
        ],
    )
    assert result.exit_code == 0
    assert "Removed" in result.output


def test_model_comparison_delete(patch_client):
    result = runner.invoke(
        app,
        ["model-comparison", "delete", "mec1", "--yes", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    assert "Deleted" in result.output
    mc = patch_client.get_project("PROJ1").get_model_comparison("mec1")
    mc.delete.assert_called_once()
