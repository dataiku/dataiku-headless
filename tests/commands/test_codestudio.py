"""Tests for code-studio commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


# --- list ---


def test_list(patch_client):
    result = runner.invoke(app, ["code-studio", "list", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "cs1" in result.output
    assert "My Studio" in result.output


def test_list_json(patch_client):
    result = runner.invoke(
        app, ["code-studio", "list", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["id"] == "cs1"
    assert parsed[0]["name"] == "My Studio"
    assert parsed[0]["owner"] == "testuser"
    assert parsed[0]["template_id"] == "tpl1"


# --- create ---


def test_create(patch_client):
    result = runner.invoke(
        app,
        [
            "code-studio",
            "create",
            "New Studio",
            "--template",
            "tpl1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created" in result.output
    assert "New Studio" in result.output
    patch_client.get_project("PROJ1").create_code_studio.assert_called_once_with(
        "New Studio", "tpl1"
    )


# --- get ---


def test_get(patch_client):
    result = runner.invoke(
        app, ["code-studio", "get", "cs1", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["id"] == "cs1"
    assert parsed["name"] == "My Studio"


# --- delete ---


def test_delete(patch_client):
    result = runner.invoke(app, ["code-studio", "delete", "cs1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "Deleted" in result.output
    patch_client.get_project("PROJ1").get_code_studio("cs1").delete.assert_called_once()


# --- status ---


def test_status(patch_client):
    result = runner.invoke(
        app, ["code-studio", "status", "cs1", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["state"] == "STOPPED"


# --- start ---


def test_start_wait(patch_client):
    result = runner.invoke(app, ["code-studio", "start", "cs1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "started" in result.output
    cs = patch_client.get_project("PROJ1").get_code_studio("cs1")
    cs.restart.assert_called_once()
    cs.restart().wait_for_result.assert_called_once()


def test_start_no_wait(patch_client):
    result = runner.invoke(
        app, ["code-studio", "start", "cs1", "--no-wait", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "initiated" in result.output
    cs = patch_client.get_project("PROJ1").get_code_studio("cs1")
    cs.restart.assert_called_once()
    cs.restart.return_value.wait_for_result.assert_not_called()


# --- stop ---


def test_stop_wait(patch_client):
    result = runner.invoke(app, ["code-studio", "stop", "cs1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "stopped" in result.output
    cs = patch_client.get_project("PROJ1").get_code_studio("cs1")
    cs.stop.assert_called_once()
    cs.stop().wait_for_result.assert_called_once()


def test_stop_no_wait(patch_client):
    result = runner.invoke(
        app, ["code-studio", "stop", "cs1", "--no-wait", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "initiated" in result.output
    cs = patch_client.get_project("PROJ1").get_code_studio("cs1")
    cs.stop.assert_called_once()
    cs.stop.return_value.wait_for_result.assert_not_called()


# --- change-owner ---


def test_change_owner(patch_client):
    result = runner.invoke(
        app,
        [
            "code-studio",
            "change-owner",
            "cs1",
            "--owner",
            "newuser",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "newuser" in result.output
    patch_client.get_project("PROJ1").get_code_studio(
        "cs1"
    ).change_owner.assert_called_once_with("newuser")


# --- templates ---


def test_templates(patch_client):
    result = runner.invoke(app, ["code-studio", "templates"])
    assert result.exit_code == 0
    assert "tpl1" in result.output
    assert "Python Notebook" in result.output


def test_templates_json(patch_client):
    result = runner.invoke(app, ["code-studio", "templates", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["id"] == "tpl1"
    assert parsed[0]["label"] == "Python Notebook"
