"""Tests for agent commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_agent_list(patch_client):
    result = runner.invoke(app, ["agent", "list", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "agent1" in result.output


def test_agent_list_json(patch_client):
    result = runner.invoke(app, ["agent", "list", "--project", "PROJ1", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["id"] == "agent1"
    assert parsed[0]["name"] == "My Agent"


def test_agent_create(patch_client):
    result = runner.invoke(app, ["agent", "create", "My Agent", "--project", "PROJ1"])
    assert result.exit_code == 0
    patch_client.get_project("PROJ1").create_agent.assert_called_once_with(
        "My Agent", type="TOOLS_USING_AGENT"
    )


def test_agent_create_custom_type(patch_client):
    result = runner.invoke(
        app,
        ["agent", "create", "My Agent", "--type", "PYTHON_AGENT", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    patch_client.get_project("PROJ1").create_agent.assert_called_once_with(
        "My Agent", type="PYTHON_AGENT"
    )


def test_agent_get(patch_client):
    result = runner.invoke(app, ["agent", "get", "agent1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "agent1" in result.output


def test_agent_get_json(patch_client):
    result = runner.invoke(
        app, ["agent", "get", "agent1", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["id"] == "agent1"


def test_agent_delete(patch_client):
    result = runner.invoke(app, ["agent", "delete", "agent1", "--project", "PROJ1"])
    assert result.exit_code == 0
    patch_client.get_project("PROJ1").get_agent("agent1").delete.assert_called_once()


def test_agent_wake_up(patch_client):
    result = runner.invoke(app, ["agent", "wake-up", "agent1", "--project", "PROJ1"])
    assert result.exit_code == 0
    patch_client.get_project("PROJ1").get_agent("agent1").wake_up.assert_called_once()


def test_agent_shutdown(patch_client):
    result = runner.invoke(app, ["agent", "shutdown", "agent1", "--project", "PROJ1"])
    assert result.exit_code == 0
    patch_client.get_project("PROJ1").get_agent("agent1").shutdown.assert_called_once()


def test_agent_status(patch_client):
    result = runner.invoke(app, ["agent", "status", "agent1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "RUNNING" in result.output


def test_agent_status_json(patch_client):
    result = runner.invoke(
        app, ["agent", "status", "agent1", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["state"] == "RUNNING"


def test_agent_add_tool(patch_client):
    result = runner.invoke(
        app, ["agent", "add-tool", "agent1", "--tool", "new_tool", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    # Verify tool was added via version settings API (toolRef, not toolId)
    settings = patch_client.get_project("PROJ1").get_agent("agent1").get_settings()
    settings.save.assert_called_once()
    ver_settings = settings.get_version_settings("v1")
    raw = ver_settings.get_raw()
    tools = raw["toolsUsingAgentSettings"]["tools"]
    assert any(t["toolRef"] == "new_tool" for t in tools)


def test_agent_set_llm(patch_client):
    result = runner.invoke(
        app, ["agent", "set-llm", "agent1", "--llm-id", "gpt4", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    # Verify LLM was set via version settings API (toolsUsingAgentSettings.llmId)
    settings = patch_client.get_project("PROJ1").get_agent("agent1").get_settings()
    settings.save.assert_called()
    ver_settings = settings.get_version_settings("v1")
    raw = ver_settings.get_raw()
    assert raw["toolsUsingAgentSettings"]["llmId"] == "gpt4"


def test_agent_set_prompt(patch_client):
    result = runner.invoke(
        app,
        [
            "agent",
            "set-prompt",
            "agent1",
            "--prompt",
            "You are a helpful analyst.",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Set system prompt" in result.output
    # Verify prompt was set on version settings
    settings = patch_client.get_project("PROJ1").get_agent("agent1").get_settings()
    settings.save.assert_called()
    ver_settings = settings.get_version_settings("v1")
    raw = ver_settings.get_raw()
    assert (
        raw["toolsUsingAgentSettings"]["systemPrompt"] == "You are a helpful analyst."
    )


def test_agent_set_prompt_from_file(patch_client, tmp_path):
    prompt_file = tmp_path / "prompt.txt"
    prompt_file.write_text("You are a financial analyst.")
    result = runner.invoke(
        app,
        [
            "agent",
            "set-prompt",
            "agent1",
            "--prompt",
            f"@{prompt_file}",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    settings = patch_client.get_project("PROJ1").get_agent("agent1").get_settings()
    ver_settings = settings.get_version_settings("v1")
    raw = ver_settings.get_raw()
    assert (
        raw["toolsUsingAgentSettings"]["systemPrompt"] == "You are a financial analyst."
    )


def test_agent_resolve_by_name(patch_client):
    """Agent commands accept name in addition to ID."""
    result = runner.invoke(app, ["agent", "get", "My Agent", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "agent1" in result.output


def test_agent_set_llm_by_name(patch_client):
    """set-llm works with agent name, not just ID."""
    result = runner.invoke(
        app, ["agent", "set-llm", "My Agent", "--llm-id", "gpt4", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "Set LLM" in result.output


def test_agent_status_calls_status_not_get_status(patch_client):
    """Verify we call agent.status() (correct API) not agent.get_status()."""
    result = runner.invoke(app, ["agent", "status", "agent1", "--project", "PROJ1"])
    assert result.exit_code == 0
    patch_client.get_project("PROJ1").get_agent("agent1").status.assert_called_once()
