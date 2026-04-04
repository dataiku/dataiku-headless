"""Tests for agent-hub commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


def test_list(patch_client):
    result = runner.invoke(app, ["agent-hub", "list", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "hub1" in result.output
    assert "Agent Hub" in result.output
    # Standard webapp should be filtered out
    assert "Dashboard" not in result.output


def test_list_json(patch_client):
    result = runner.invoke(
        app, ["agent-hub", "list", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 1
    assert parsed[0]["id"] == "hub1"


# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------


def test_config(patch_client):
    result = runner.invoke(app, ["agent-hub", "config", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "gpt-4o" in result.output


def test_config_json(patch_client):
    result = runner.invoke(
        app, ["agent-hub", "config", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["default_llm_id"] == "openai:conn:gpt-4o"
    assert "tool_agent_configurations" in parsed


def test_config_explicit_hub(patch_client):
    """--hub flag selects a specific hub."""
    result = runner.invoke(
        app, ["agent-hub", "config", "--hub", "hub1", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "gpt-4o" in result.output


# ---------------------------------------------------------------------------
# set-config
# ---------------------------------------------------------------------------


def test_set_config(patch_client):
    result = runner.invoke(
        app,
        [
            "agent-hub",
            "set-config",
            "--definition",
            '{"enable_quick_agents": false}',
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    hub = patch_client.get_project("PROJ1").get_webapp("hub1")
    hub.get_settings().save.assert_called()


# ---------------------------------------------------------------------------
# list-agents
# ---------------------------------------------------------------------------


def test_list_agents(patch_client):
    result = runner.invoke(app, ["agent-hub", "list-agents", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "Sales Agent" in result.output
    assert "PROJ1:agent:a1" in result.output


def test_list_agents_json(patch_client):
    result = runner.invoke(
        app, ["agent-hub", "list-agents", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["agent_id"] == "PROJ1:agent:a1"
    assert parsed[0]["name"] == "Sales Agent"


# ---------------------------------------------------------------------------
# add-agent
# ---------------------------------------------------------------------------


def test_add_agent(patch_client):
    result = runner.invoke(
        app,
        [
            "agent-hub",
            "add-agent",
            "--agent-id",
            "PROJ2:agent:b1",
            "--name",
            "Support Agent",
            "--description",
            "Handles support tickets",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Added agent" in result.output

    # Verify config was updated
    hub = patch_client.get_project("PROJ1").get_webapp("hub1")
    settings = hub.get_settings()
    raw = settings.get_raw()
    config = raw["config"]
    assert "PROJ2:agent:b1" in config["agents_ids"]
    assert "PROJ2" in config["projects_keys"]
    configs = config["tool_agent_configurations"]
    added = [c for c in configs if c["agent_id"] == "PROJ2:agent:b1"]
    assert len(added) == 1
    assert added[0]["tool_agent_display_name"] == "Support Agent"
    settings.save.assert_called()


def test_add_agent_already_exists(patch_client):
    """Adding an agent that's already in the hub warns and skips."""
    result = runner.invoke(
        app,
        [
            "agent-hub",
            "add-agent",
            "--agent-id",
            "PROJ1:agent:a1",
            "--name",
            "Sales Agent",
            "--description",
            "Duplicate",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "already in" in result.output.lower()


# ---------------------------------------------------------------------------
# remove-agent
# ---------------------------------------------------------------------------


def test_remove_agent(patch_client):
    result = runner.invoke(
        app,
        [
            "agent-hub",
            "remove-agent",
            "--agent-id",
            "PROJ1:agent:a1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Removed" in result.output

    hub = patch_client.get_project("PROJ1").get_webapp("hub1")
    settings = hub.get_settings()
    raw = settings.get_raw()
    config = raw["config"]
    assert "PROJ1:agent:a1" not in config["agents_ids"]
    remaining = [
        c
        for c in config["tool_agent_configurations"]
        if c["agent_id"] == "PROJ1:agent:a1"
    ]
    assert len(remaining) == 0
    settings.save.assert_called()


def test_remove_agent_not_found(patch_client):
    result = runner.invoke(
        app,
        [
            "agent-hub",
            "remove-agent",
            "--agent-id",
            "PROJ1:agent:nonexistent",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "not found" in result.output.lower()


# ---------------------------------------------------------------------------
# set-agent
# ---------------------------------------------------------------------------


def test_set_agent_description(patch_client):
    result = runner.invoke(
        app,
        [
            "agent-hub",
            "set-agent",
            "--agent-id",
            "PROJ1:agent:a1",
            "--description",
            "Updated description",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0

    hub = patch_client.get_project("PROJ1").get_webapp("hub1")
    config = hub.get_settings().get_raw()["config"]
    agent_cfg = config["tool_agent_configurations"][0]
    assert agent_cfg["tool_agent_description"] == "Updated description"


def test_set_agent_name(patch_client):
    result = runner.invoke(
        app,
        [
            "agent-hub",
            "set-agent",
            "--agent-id",
            "PROJ1:agent:a1",
            "--name",
            "Renamed Agent",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0

    hub = patch_client.get_project("PROJ1").get_webapp("hub1")
    config = hub.get_settings().get_raw()["config"]
    agent_cfg = config["tool_agent_configurations"][0]
    assert agent_cfg["tool_agent_display_name"] == "Renamed Agent"


def test_set_agent_examples(patch_client):
    result = runner.invoke(
        app,
        [
            "agent-hub",
            "set-agent",
            "--agent-id",
            "PROJ1:agent:a1",
            "--examples",
            '["Q1 revenue?", "Top customers"]',
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0

    hub = patch_client.get_project("PROJ1").get_webapp("hub1")
    config = hub.get_settings().get_raw()["config"]
    agent_cfg = config["tool_agent_configurations"][0]
    assert agent_cfg["agent_example_queries"] == ["Q1 revenue?", "Top customers"]


def test_set_agent_not_found(patch_client):
    result = runner.invoke(
        app,
        [
            "agent-hub",
            "set-agent",
            "--agent-id",
            "PROJ1:agent:nonexistent",
            "--description",
            "test",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "not found" in result.output.lower()


# ---------------------------------------------------------------------------
# set-llm
# ---------------------------------------------------------------------------


def test_set_llm(patch_client):
    result = runner.invoke(
        app,
        [
            "agent-hub",
            "set-llm",
            "openai:conn:gpt-4o-mini",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0

    hub = patch_client.get_project("PROJ1").get_webapp("hub1")
    config = hub.get_settings().get_raw()["config"]
    assert config["default_llm_id"] == "openai:conn:gpt-4o-mini"


# ---------------------------------------------------------------------------
# start / stop
# ---------------------------------------------------------------------------


def test_start(patch_client):
    result = runner.invoke(app, ["agent-hub", "start", "--project", "PROJ1"])
    assert result.exit_code == 0
    patch_client.get_project("PROJ1").get_webapp(
        "hub1"
    ).start_or_restart_backend.assert_called_once()


def test_stop(patch_client):
    result = runner.invoke(app, ["agent-hub", "stop", "--project", "PROJ1"])
    assert result.exit_code == 0
    patch_client.get_project("PROJ1").get_webapp(
        "hub1"
    ).stop_backend.assert_called_once()


# ---------------------------------------------------------------------------
# Auto-resolve edge cases
# ---------------------------------------------------------------------------


def test_no_hub_found(patch_client):
    """Error when no Agent Hub webapp exists in project."""
    proj = patch_client.get_project("PROJ1")
    proj.list_webapps.return_value = [
        {"id": "webapp1", "name": "Dashboard", "type": "STANDARD"},
    ]
    result = runner.invoke(app, ["agent-hub", "config", "--project", "PROJ1"])
    assert result.exit_code != 0
    assert "No Agent Hub" in result.output


def test_multiple_hubs_no_flag(patch_client):
    """Error when multiple hubs exist and --hub not provided."""
    proj = patch_client.get_project("PROJ1")
    proj.list_webapps.return_value = [
        {"id": "hub1", "name": "Hub 1", "type": "webapp_agent-hub_agent-hub"},
        {"id": "hub2", "name": "Hub 2", "type": "webapp_agent-hub_agent-hub"},
    ]
    result = runner.invoke(app, ["agent-hub", "config", "--project", "PROJ1"])
    assert result.exit_code != 0
    assert "--hub" in result.output
