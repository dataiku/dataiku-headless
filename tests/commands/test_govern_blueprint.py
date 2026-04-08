"""Tests for dku govern-blueprint commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_blueprint_list(patch_client):
    result = runner.invoke(app, ["govern", "blueprint", "list"])
    assert result.exit_code == 0
    assert "govern_project" in result.output


def test_blueprint_list_json(patch_client):
    result = runner.invoke(app, ["govern", "blueprint", "list", "-o", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 1
    assert data[0]["id"] == "bp.system.govern_project"


def test_blueprint_get(patch_client):
    result = runner.invoke(
        app, ["govern", "blueprint", "get", "bp.system.govern_project"]
    )
    assert result.exit_code == 0
    assert "govern_project" in result.output


def test_blueprint_get_json(patch_client):
    result = runner.invoke(
        app, ["govern", "blueprint", "get", "bp.system.govern_project", "-o", "json"]
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["id"] == "bp.system.govern_project"


def test_blueprint_list_versions(patch_client):
    result = runner.invoke(
        app, ["govern", "blueprint", "list-versions", "bp.system.govern_project"]
    )
    assert result.exit_code == 0
    assert "ACTIVE" in result.output or "Default" in result.output


def test_blueprint_list_versions_json(patch_client):
    result = runner.invoke(
        app,
        [
            "govern",
            "blueprint",
            "list-versions",
            "bp.system.govern_project",
            "-o",
            "json",
        ],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 1
    assert data[0]["version_id"] == "bv.system.default"


def test_blueprint_get_version(patch_client):
    result = runner.invoke(
        app,
        [
            "govern",
            "blueprint",
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
            "govern",
            "blueprint",
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


def test_blueprint_fields(patch_client):
    """Test fields command shows field schema."""
    result = runner.invoke(
        app, ["govern", "blueprint", "fields", "bp.system.govern_project"]
    )
    assert result.exit_code == 0
    assert "description" in result.output
    assert "TEXT" in result.output
    assert "cost_rating" in result.output
    assert "CATEGORY" in result.output


def test_blueprint_fields_json(patch_client):
    """Test fields command in JSON output."""
    result = runner.invoke(
        app,
        ["govern", "blueprint", "fields", "bp.system.govern_project", "-o", "json"],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    field_ids = [f["field"] for f in data]
    assert "description" in field_ids
    assert "cost_rating" in field_ids
    # COMPUTE fields should be excluded
    assert "govern_models" not in field_ids


def test_blueprint_fields_shows_list_marker(patch_client):
    """Test that list fields are marked with * in the LIST column."""
    result = runner.invoke(
        app,
        ["govern", "blueprint", "fields", "bp.system.govern_project", "-o", "json"],
    )
    data = json.loads(result.output)
    countries = next(f for f in data if f["field"] == "countries")
    assert countries["list"] == "*"
    description = next(f for f in data if f["field"] == "description")
    assert description["list"] == ""


def test_blueprint_fields_shows_categories(patch_client):
    """Test that category values are shown."""
    result = runner.invoke(
        app,
        ["govern", "blueprint", "fields", "bp.system.govern_project", "-o", "json"],
    )
    data = json.loads(result.output)
    cost = next(f for f in data if f["field"] == "cost_rating")
    assert "Low" in cost["values"]
    assert "High" in cost["values"]


def test_blueprint_fields_shows_allowed_refs(patch_client):
    """Test that REFERENCE fields show allowed blueprints."""
    result = runner.invoke(
        app,
        ["govern", "blueprint", "fields", "bp.system.govern_project", "-o", "json"],
    )
    data = json.loads(result.output)
    bi = next(f for f in data if f["field"] == "business_initiative")
    assert "bp.system.business_initiative" in bi["values"]
