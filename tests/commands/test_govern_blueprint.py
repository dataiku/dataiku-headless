"""Tests for dku govern-blueprint commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_blueprint_list(patch_client):
    result = runner.invoke(app, ["govern-blueprint", "list"])
    assert result.exit_code == 0
    assert "govern_project" in result.output


def test_blueprint_list_json(patch_client):
    result = runner.invoke(app, ["govern-blueprint", "list", "-o", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 1
    assert data[0]["id"] == "bp.system.govern_project"


def test_blueprint_get(patch_client):
    result = runner.invoke(app, ["govern-blueprint", "get", "bp.system.govern_project"])
    assert result.exit_code == 0
    assert "govern_project" in result.output


def test_blueprint_get_json(patch_client):
    result = runner.invoke(
        app, ["govern-blueprint", "get", "bp.system.govern_project", "-o", "json"]
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["id"] == "bp.system.govern_project"


def test_blueprint_list_versions(patch_client):
    result = runner.invoke(
        app, ["govern-blueprint", "list-versions", "bp.system.govern_project"]
    )
    assert result.exit_code == 0
    assert "ACTIVE" in result.output or "Default" in result.output


def test_blueprint_list_versions_json(patch_client):
    result = runner.invoke(
        app,
        ["govern-blueprint", "list-versions", "bp.system.govern_project", "-o", "json"],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 1
    assert data[0]["version_id"] == "bv.system.default"


def test_blueprint_get_version(patch_client):
    result = runner.invoke(
        app,
        [
            "govern-blueprint",
            "get-version",
            "bp.system.govern_project",
            "bv.system.default",
        ],
    )
    assert result.exit_code == 0
    assert "govern_project" in result.output or "Default" in result.output


def test_blueprint_get_version_json(patch_client):
    result = runner.invoke(
        app,
        [
            "govern-blueprint",
            "get-version",
            "bp.system.govern_project",
            "bv.system.default",
            "-o",
            "json",
        ],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["name"] == "Default"
