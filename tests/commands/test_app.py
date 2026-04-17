"""Tests for app commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_app_list_table(patch_client):
    result = runner.invoke(app, ["app", "list"])
    assert result.exit_code == 0
    assert "PROJECT_MYAPP" in result.output
    assert "My App" in result.output


def test_app_list_json(patch_client):
    result = runner.invoke(app, ["app", "list", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 1
    assert parsed[0]["id"] == "PROJECT_MYAPP"


def test_app_list_empty(patch_client):
    patch_client.list_apps.return_value = []
    result = runner.invoke(app, ["app", "list"])
    assert result.exit_code == 0
    assert "no applications" in result.output.lower()


def test_app_get(patch_client):
    result = runner.invoke(app, ["app", "get", "PROJECT_MYAPP", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["appId"] == "PROJECT_MYAPP"


def test_app_list_instances(patch_client):
    result = runner.invoke(app, ["app", "list-instances", "PROJECT_MYAPP"])
    assert result.exit_code == 0
    assert "MYAPP_INST1" in result.output
    assert "Production" in result.output


def test_app_list_instances_json(patch_client):
    result = runner.invoke(
        app, ["app", "list-instances", "PROJECT_MYAPP", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 1
    assert parsed[0]["projectKey"] == "MYAPP_INST1"


def test_app_list_instances_empty(patch_client):
    patch_client.get_app("PROJECT_MYAPP").list_instances.return_value = []
    result = runner.invoke(app, ["app", "list-instances", "PROJECT_MYAPP"])
    assert result.exit_code == 0
    assert "no instances" in result.output.lower()


def test_app_create_instance(patch_client):
    result = runner.invoke(
        app,
        [
            "app",
            "create-instance",
            "PROJECT_MYAPP",
            "--key",
            "MYAPP_NEW",
            "--name",
            "New Instance",
        ],
    )
    assert result.exit_code == 0
    assert "Created" in result.output
    patch_client.get_app("PROJECT_MYAPP").create_instance.assert_called_once_with(
        "MYAPP_NEW", "New Instance", wait=True
    )
