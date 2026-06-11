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
        app, ["--format", "json", "agent-tool", "list", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["id"] == "tool1"
    assert parsed[0]["name"] == "My Tool"
    assert parsed[0]["type"] == "DatasetRowLookup"


def test_agent_tool_get(patch_client):
    result = runner.invoke(app, ["agent-tool", "get", "tool1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "tool1" in result.output


def test_agent_tool_get_json(patch_client):
    result = runner.invoke(
        app, ["--format", "json", "agent-tool", "get", "tool1", "--project", "PROJ1"]
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
    result = runner.invoke(app, ["--format", "json", "agent-tool", "types"])
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


def test_agent_tool_create_with_params_plugin_type(patch_client):
    """--params merges arbitrary fields into a plugin tool's settings.params."""
    result = runner.invoke(
        app,
        [
            "agent-tool",
            "create",
            "sm_query",
            "--type",
            "Custom_agent_tool_semantic-models-lab_semantic-model-query",
            "--params",
            '{"semanticModelId":"sm123","activeVersionOnly":true}',
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    new_tool = patch_client.get_project("PROJ1").new_agent_tool.return_value.create()
    settings = new_tool.get_settings.return_value
    assert settings.params["semanticModelId"] == "sm123"
    assert settings.params["activeVersionOnly"] is True
    settings.save.assert_called()


def test_agent_tool_create_with_params_invalid_json(patch_client):
    """Bad --params payload rejected up-front so no orphan tool is created."""
    result = runner.invoke(
        app,
        [
            "agent-tool",
            "create",
            "sm_query",
            "--type",
            "Custom_agent_tool_x_y",
            "--params",
            "not json",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    # No tool was created — the rejection happens before new_agent_tool().
    patch_client.get_project("PROJ1").new_agent_tool.assert_not_called()


def test_agent_tool_create_atomic_cleanup_on_params_failure(patch_client):
    """If --params save raises, the orphan tool is deleted before the error propagates."""
    proj = patch_client.get_project("PROJ1")
    new_tool = proj.new_agent_tool.return_value.create()
    settings = new_tool.get_settings.return_value
    settings.save.side_effect = RuntimeError("server rejected params")

    result = runner.invoke(
        app,
        [
            "agent-tool",
            "create",
            "sm_query",
            "--type",
            "Custom_agent_tool_x_y",
            "--params",
            '{"foo": "bar"}',
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    # Tool was deleted on failure so the user can re-run with the same name.
    new_tool.delete.assert_called()


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


# ── DSS 14.6 catalog + Model Predict ergonomics ──────────────────────────


def test_agent_tool_types_includes_dss14_catalog(patch_client):
    """The catalog must include the live-verified DSS 14.6 built-ins —
    missing entries cost agents dozens of blind type guesses."""
    result = runner.invoke(app, ["--format", "json", "agent-tool", "types"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    type_names = [t["type"] for t in parsed]
    for expected in (
        "DatasetRowLookup",
        "DatasetRowAppend",
        "VectorStoreSearch",
        "LLMMeshLLMQuery",
        "ClassicalPredictionModelPredict",
        "ApiEndpoint",
        "ImageGeneration",
        "GenerateArtifact",
    ):
        assert expected in type_names


def test_agent_tool_create_with_saved_model_sets_smref(patch_client):
    """--saved-model must write params.smRef (NOT savedModelId/modelId)."""
    result = runner.invoke(
        app,
        [
            "agent-tool",
            "create",
            "churn_predict",
            "--type",
            "ClassicalPredictionModelPredict",
            "--saved-model",
            "model1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created agent tool" in result.output
    proj = patch_client.get_project("PROJ1")
    new_tool = proj.new_agent_tool.return_value.create()
    settings = new_tool.get_settings.return_value
    assert settings.params["smRef"] == proj.get_saved_model.return_value.sm_id
    settings.save.assert_called()


def test_agent_tool_create_with_saved_model_wrong_type(patch_client):
    """--saved-model on a non-ModelPredict type should fail and clean up."""
    result = runner.invoke(
        app,
        [
            "agent-tool",
            "create",
            "bad_tool",
            "--type",
            "DatasetRowLookup",
            "--saved-model",
            "model1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "ClassicalPredictionModelPredict" in result.output
    new_tool = patch_client.get_project("PROJ1").new_agent_tool.return_value.create()
    new_tool.delete.assert_called()


def test_agent_tool_create_dataset_row_append_accepts_dataset(patch_client):
    """--dataset works for DatasetRowAppend (same ref fields as lookup)."""
    result = runner.invoke(
        app,
        [
            "agent-tool",
            "create",
            "appender",
            "--type",
            "DatasetRowAppend",
            "--dataset",
            "target_ds",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created agent tool" in result.output


def test_agent_tool_set_definition_params_only(patch_client):
    """--params merges into settings.params without restating the definition."""
    result = runner.invoke(
        app,
        [
            "agent-tool",
            "set-definition",
            "tool1",
            "--params",
            '{"smRef": "model_abc"}',
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    tool = patch_client.get_project("PROJ1").get_agent_tool("tool1")
    raw = tool.get_settings.return_value.get_raw.return_value
    assert raw["params"]["smRef"] == "model_abc"
    tool.get_settings.return_value.save.assert_called_once()


def test_agent_tool_set_definition_requires_definition_or_params(patch_client):
    """Neither --definition nor --params → prescriptive error."""
    result = runner.invoke(
        app,
        ["agent-tool", "set-definition", "tool1", "--project", "PROJ1"],
    )
    assert result.exit_code != 0
    assert "--params" in result.output
