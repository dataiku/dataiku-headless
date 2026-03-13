"""Tests for api-service commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_api_service_list(patch_client):
    result = runner.invoke(app, ["api-service", "list", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "myservice" in result.output


def test_api_service_list_json(patch_client):
    result = runner.invoke(
        app, ["api-service", "list", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 1
    assert parsed[0]["id"] == "myservice"


def test_api_service_create(patch_client):
    result = runner.invoke(
        app, ["api-service", "create", "newsvc", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    proj.create_api_service.assert_called_once_with("newsvc")


def test_api_service_get(patch_client):
    result = runner.invoke(
        app, ["api-service", "get", "myservice", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "myservice" in result.output


def test_api_service_get_json(patch_client):
    result = runner.invoke(
        app, ["api-service", "get", "myservice", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["id"] == "myservice"
    assert "endpoints" in parsed


def test_api_service_create_package(patch_client):
    result = runner.invoke(
        app, ["api-service", "create-package", "myservice", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    svc = proj.get_api_service("myservice")
    svc.create_package.assert_called_once()


def test_api_service_list_packages(patch_client):
    result = runner.invoke(
        app, ["api-service", "list-packages", "myservice", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "pkg1" in result.output


def test_api_service_list_packages_json(patch_client):
    result = runner.invoke(
        app,
        ["api-service", "list-packages", "myservice", "--project", "PROJ1", "-o", "json"],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 1
    assert parsed[0]["id"] == "pkg1"
    assert parsed[0]["created_on"] == "2025-01-01"
