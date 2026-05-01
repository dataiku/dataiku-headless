"""Tests for agent-tool commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_agent_tool_list(patch_client):
    """Default list includes shared tools from other projects."""
    result = runner.invoke(app, ["agent-tool", "list", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "tool1" in result.output
    assert "shared_tool" in result.output


def test_agent_tool_list_json(patch_client):
    result = runner.invoke(
        app, ["agent-tool", "list", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 2
    by_id = {row["id"]: row for row in parsed}
    assert by_id["tool1"]["projectKey"] == "PROJ1"
    assert by_id["shared_tool"]["projectKey"] == "OTHER_PROJ"


def test_agent_tool_list_own_only(patch_client):
    result = runner.invoke(
        app,
        ["agent-tool", "list", "--project", "PROJ1", "--own-only", "-o", "json"],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 1
    assert parsed[0]["id"] == "tool1"


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
    result = runner.invoke(
        app, ["agent-tool", "delete", "tool1", "--project", "PROJ1", "--yes"]
    )
    assert result.exit_code == 0
    patch_client.get_project("PROJ1").get_agent_tool(
        "tool1"
    ).delete.assert_called_once()


def test_agent_tool_create(patch_client):
    result = runner.invoke(
        app,
        [
            "agent-tool",
            "create",
            "my_lookup",
            "--type",
            "DatasetRowLookup",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created agent tool" in result.output
    patch_client.get_project("PROJ1").new_agent_tool.assert_called_once_with(
        "DatasetRowLookup", name="my_lookup"
    )


def test_agent_tool_create_vector_search(patch_client):
    result = runner.invoke(
        app,
        [
            "agent-tool",
            "create",
            "my_search",
            "--type",
            "VectorStoreSearch",
            "--kb",
            "my_kb",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    builder = proj.new_agent_tool.return_value
    # The CLI resolves NAME → ID via resolve_knowledge_bank.
    # With the default MagicMock, get_knowledge_bank("my_kb").get_settings()
    # succeeds without raising, so resolution returns the same handle and
    # with_knowledge_bank is called with that handle's .id attribute.
    expected_id = proj.get_knowledge_bank("my_kb").id
    builder.with_knowledge_bank.assert_called_once_with(expected_id)
    builder.create.assert_called_once()


def test_agent_tool_create_vector_search_no_kb(patch_client):
    """VectorStoreSearch without --knowledge-bank should fail with prescriptive error."""
    result = runner.invoke(
        app,
        [
            "agent-tool",
            "create",
            "my_search",
            "--type",
            "VectorStoreSearch",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0


def test_agent_tool_types(patch_client):
    result = runner.invoke(app, ["agent-tool", "types"])
    assert result.exit_code == 0
    assert "DatasetRowLookup" in result.output
    assert "VectorStoreSearch" in result.output
    assert "LLMMeshLLMQuery" in result.output


def test_agent_tool_types_json(patch_client):
    result = runner.invoke(app, ["agent-tool", "types", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    type_names = [t["type"] for t in parsed]
    assert "DatasetRowLookup" in type_names
    assert "VectorStoreSearch" in type_names


def test_agent_tool_create_with_dataset(patch_client):
    """DatasetRowLookup with --dataset writes to both fields when neither exists."""
    result = runner.invoke(
        app,
        [
            "agent-tool",
            "create",
            "my_lookup",
            "--type",
            "DatasetRowLookup",
            "--dataset",
            "customers",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created agent tool" in result.output
    new_tool = patch_client.get_project("PROJ1").new_agent_tool.return_value.create()
    new_tool.get_settings.assert_called()
    settings = new_tool.get_settings.return_value
    # When neither field exists, writes both for version compat
    assert settings.params["datasetSmartName"] == "customers"
    assert settings.params["datasetRef"] == "customers"
    settings.save.assert_called()


def test_agent_tool_create_with_dataset_wrong_type(patch_client):
    """--dataset on non-DatasetRowLookup should fail."""
    result = runner.invoke(
        app,
        [
            "agent-tool",
            "create",
            "my_search",
            "--type",
            "VectorStoreSearch",
            "--kb",
            "my_kb",
            "--dataset",
            "customers",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0


def test_agent_tool_create_with_llm(patch_client):
    """LLMMeshLLMQuery with --llm should set llmId in params."""
    result = runner.invoke(
        app,
        [
            "agent-tool",
            "create",
            "my_llm",
            "--type",
            "LLMMeshLLMQuery",
            "--llm",
            "openai:conn:gpt-4o",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created agent tool" in result.output
    new_tool = patch_client.get_project("PROJ1").new_agent_tool.return_value.create()
    new_tool.get_settings.assert_called()
    settings = new_tool.get_settings.return_value
    assert settings.params["llmId"] == "openai:conn:gpt-4o"
    settings.save.assert_called()


def test_agent_tool_create_with_llm_wrong_type(patch_client):
    """--llm on non-LLMMeshLLMQuery should fail."""
    result = runner.invoke(
        app,
        [
            "agent-tool",
            "create",
            "my_lookup",
            "--type",
            "DatasetRowLookup",
            "--llm",
            "openai:conn:gpt-4o",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0


def test_agent_tool_types_no_python_function(patch_client):
    """PythonFunction, SQLQuery, RetrieveDatasetSchema should NOT be in types."""
    result = runner.invoke(app, ["agent-tool", "types"])
    assert result.exit_code == 0
    assert "PythonFunction" not in result.output
    assert "SQLQuery" not in result.output
    assert "RetrieveDatasetSchema" not in result.output


def test_agent_tool_create_with_dataset_detects_datasetRef(patch_client):
    """When tool already has datasetRef key (DSS 14.5+), write to that field only."""
    # Pre-populate params with DSS 14.5 field name
    new_tool = patch_client.get_project("PROJ1").new_agent_tool.return_value.create()
    new_tool.get_settings.return_value.params = {"datasetRef": ""}
    result = runner.invoke(
        app,
        [
            "agent-tool",
            "create",
            "my_lookup",
            "--type",
            "DatasetRowLookup",
            "--dataset",
            "customers",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    settings = new_tool.get_settings.return_value
    assert settings.params["datasetRef"] == "customers"
    assert "datasetSmartName" not in settings.params


def test_agent_tool_create_with_dataset_detects_datasetSmartName(patch_client):
    """When tool already has datasetSmartName key (DSS 13.x), write to that field only."""
    new_tool = patch_client.get_project("PROJ1").new_agent_tool.return_value.create()
    new_tool.get_settings.return_value.params = {"datasetSmartName": ""}
    result = runner.invoke(
        app,
        [
            "agent-tool",
            "create",
            "my_lookup",
            "--type",
            "DatasetRowLookup",
            "--dataset",
            "customers",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    settings = new_tool.get_settings.return_value
    assert settings.params["datasetSmartName"] == "customers"
    assert "datasetRef" not in settings.params


def test_agent_tool_set_definition(patch_client):
    result = runner.invoke(
        app,
        [
            "agent-tool",
            "set-definition",
            "tool1",
            "--definition",
            '{"params": {"apiKey": "secret"}}',
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    tool = patch_client.get_project("PROJ1").get_agent_tool("tool1")
    tool.get_settings.assert_called()
    tool.get_settings.return_value.save.assert_called_once()
    # Verify the update was actually applied to the raw dict
    raw = tool.get_settings.return_value.get_raw.return_value
    assert raw["params"] == {"apiKey": "secret"}


def test_agent_tool_set_definition_from_file(patch_client, tmp_path):
    config = tmp_path / "tool-config.json"
    config.write_text('{"params": {"model": "gpt-4"}}')
    result = runner.invoke(
        app,
        [
            "agent-tool",
            "set-definition",
            "tool1",
            "--definition",
            f"@{config}",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    tool = patch_client.get_project("PROJ1").get_agent_tool("tool1")
    tool.get_settings.return_value.save.assert_called_once()


# ── plugin tool error handling ───────────────────────────────────────────


def test_agent_tool_run_plugin_tool_failure(patch_client):
    """Plugin tools that fail should get a prescriptive error about agent context."""
    from unittest.mock import MagicMock

    plugin_tool = MagicMock()
    plugin_tool.run.side_effect = Exception("KeyError: 'apiKey'")
    patch_client.get_project("PROJ1").get_agent_tool.return_value = plugin_tool

    result = runner.invoke(
        app,
        [
            "agent-tool",
            "run",
            "Custom_agent_tool_my_plugin_my_tool",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "Plugin tool" in result.output
    assert "agent execution" in result.output


def test_agent_tool_run_regular_tool_failure_no_plugin_warning(patch_client):
    """Non-plugin tools should NOT get the plugin-specific error message."""
    from unittest.mock import MagicMock

    tool = MagicMock()
    tool.run.side_effect = Exception("Some other error")
    patch_client.get_project("PROJ1").get_agent_tool.return_value = tool

    result = runner.invoke(
        app,
        ["agent-tool", "run", "tool1", "--project", "PROJ1"],
    )
    assert result.exit_code != 0
    assert "Plugin tool" not in result.output
