"""Tests for app commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


def test_app_list(patch_client):
    result = runner.invoke(app, ["app", "list"])
    assert result.exit_code == 0
    assert "PROJECT_PROJ1" in result.output


def test_app_list_json(patch_client):
    result = runner.invoke(app, ["app", "list", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["app_id"] == "PROJECT_PROJ1"
    assert parsed[0]["label"] == "My Test App"


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------


def test_app_get(patch_client):
    result = runner.invoke(app, ["app", "get", "PROJECT_PROJ1"])
    assert result.exit_code == 0
    assert "My Test App" in result.output


def test_app_get_json(patch_client):
    result = runner.invoke(app, ["app", "get", "PROJECT_PROJ1", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["useAppHomepage"] is True
    assert parsed["label"] == "My Test App"


# ---------------------------------------------------------------------------
# list-instances
# ---------------------------------------------------------------------------


def test_app_list_instances(patch_client):
    result = runner.invoke(app, ["app", "list-instances", "PROJECT_PROJ1"])
    assert result.exit_code == 0
    assert "PROJ1_INST1" in result.output
    assert "PROJ1_INST2" in result.output


def test_app_list_instances_json(patch_client):
    result = runner.invoke(
        app, ["app", "list-instances", "PROJECT_PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 2
    assert parsed[0]["project_key"] == "PROJ1_INST1"


# ---------------------------------------------------------------------------
# create-instance
# ---------------------------------------------------------------------------


def test_app_create_instance(patch_client):
    result = runner.invoke(
        app,
        [
            "app",
            "create-instance",
            "PROJECT_PROJ1",
            "--key",
            "NEW_INST",
            "--name",
            "New Instance",
        ],
    )
    assert result.exit_code == 0
    assert "Created app instance" in result.output
    assert "NEW_INSTANCE" in result.output
    patch_client.get_app("PROJECT_PROJ1").create_instance.assert_called_once_with(
        "NEW_INST", "New Instance", wait=True
    )


def test_app_create_instance_no_wait(patch_client):
    result = runner.invoke(
        app,
        [
            "app",
            "create-instance",
            "PROJECT_PROJ1",
            "--key",
            "NEW_INST",
            "--name",
            "New Instance",
            "--no-wait",
        ],
    )
    assert result.exit_code == 0
    assert "Instance creation started" in result.output
    patch_client.get_app("PROJECT_PROJ1").create_instance.assert_called_once_with(
        "NEW_INST", "New Instance", wait=False
    )
