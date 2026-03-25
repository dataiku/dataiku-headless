"""Tests for agent-tool commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_agent_tool_list(patch_client):
    result = runner.invoke(app, ["agent-tool", "list", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "tool1" in result.output


def test_agent_tool_list_json(patch_client):
    result = runner.invoke(
        app, ["agent-tool", "list", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["id"] == "tool1"
    assert parsed[0]["name"] == "My Tool"
    assert parsed[0]["type"] == "python"


def test_agent_tool_get(patch_client):
    result = runner.invoke(app, ["agent-tool", "get", "tool1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "tool1" in result.output


def test_agent_tool_get_json(patch_client):
    result = runner.invoke(
        app, ["agent-tool", "get", "tool1", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["id"] == "tool1"


def test_agent_tool_run(patch_client):
    result = runner.invoke(
        app,
        [
            "agent-tool",
            "run",
            "tool1",
            "--project",
            "PROJ1",
            "--input",
            '{"key": "val"}',
        ],
    )
    assert result.exit_code == 0
    assert "success" in result.output


def test_agent_tool_run_no_input(patch_client):
    result = runner.invoke(app, ["agent-tool", "run", "tool1", "--project", "PROJ1"])
    assert result.exit_code == 0
    patch_client.get_project("PROJ1").get_agent_tool(
        "tool1"
    ).run.assert_called_once_with({})


def test_agent_tool_delete(patch_client):
    result = runner.invoke(app, ["agent-tool", "delete", "tool1", "--project", "PROJ1"])
    assert result.exit_code == 0
    patch_client.get_project("PROJ1").get_agent_tool(
        "tool1"
    ).delete.assert_called_once()
