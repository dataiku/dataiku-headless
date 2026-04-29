"""Tests for dku govern-role commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_role_list(patch_client):
    result = runner.invoke(app, ["govern", "role", "list"])
    assert result.exit_code == 0
    assert "project_manager" in result.output


def test_role_list_json(patch_client):
    result = runner.invoke(app, ["govern", "role", "list", "-o", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 1
    assert data[0]["id"] == "ro.project_manager"
    assert data[0]["label"] == "Project manager"


def test_role_get(patch_client):
    result = runner.invoke(app, ["govern", "role", "get", "ro.project_manager"])
    assert result.exit_code == 0
    assert "project_manager" in result.output


def test_role_get_json(patch_client):
    result = runner.invoke(
        app, ["govern", "role", "get", "ro.project_manager", "-o", "json"]
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["id"] == "ro.project_manager"
    assert data["label"] == "Project manager"
