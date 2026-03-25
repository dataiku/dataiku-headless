"""Tests for model commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_model_list(patch_client):
    result = runner.invoke(app, ["model", "list", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "model1" in result.output


def test_model_list_json(patch_client):
    result = runner.invoke(app, ["model", "list", "--project", "PROJ1", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["id"] == "model1"


def test_model_get(patch_client):
    result = runner.invoke(app, ["model", "get", "model1", "--project", "PROJ1"])
    assert result.exit_code == 0


def test_model_get_json(patch_client):
    result = runner.invoke(
        app, ["model", "get", "model1", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["active_version"] == "v1"


def test_model_versions(patch_client):
    result = runner.invoke(app, ["model", "versions", "model1", "--project", "PROJ1"])
    assert result.exit_code == 0


def test_model_versions_json(patch_client):
    result = runner.invoke(
        app, ["model", "versions", "model1", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["id"] == "v1"
    assert parsed[0]["algorithm"] == "RandomForest"
