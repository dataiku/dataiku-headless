"""Tests for llm commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_llm_list(patch_client):
    result = runner.invoke(app, ["llm", "list", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "llm1" in result.output


def test_llm_list_json(patch_client):
    result = runner.invoke(app, ["llm", "list", "--project", "PROJ1", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["id"] == "llm1"


def test_llm_list_with_purpose(patch_client):
    result = runner.invoke(app, [
        "llm", "list",
        "--project", "PROJ1",
        "--purpose", "TEXT_EMBEDDING_EXTRACTION",
    ])
    assert result.exit_code == 0
    patch_client.get_project("PROJ1").list_llms.assert_called_with(purpose="TEXT_EMBEDDING_EXTRACTION")


def test_llm_completion(patch_client):
    result = runner.invoke(app, ["llm", "completion", "llm1", "Hello", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "Hello from LLM" in result.output


def test_llm_completion_json(patch_client):
    result = runner.invoke(app, ["llm", "completion", "llm1", "Hello", "--project", "PROJ1", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["text"] == "Hello from LLM"


def test_llm_completion_with_system(patch_client):
    result = runner.invoke(app, [
        "llm", "completion", "llm1", "Hello",
        "--project", "PROJ1",
        "--system", "You are a helpful assistant",
    ])
    assert result.exit_code == 0
    assert "Hello from LLM" in result.output
    # Verify system message was passed through the builder chain
    proj = patch_client.get_project("PROJ1")
    llm = proj.get_llm("llm1")
    completion_obj = llm.new_completion()
    completion_obj.with_system_message.assert_called_with("You are a helpful assistant")


def test_llm_completion_with_json_output_flag(patch_client):
    result = runner.invoke(app, [
        "llm", "completion", "llm1", "List items",
        "--project", "PROJ1",
        "--json-output",
    ])
    assert result.exit_code == 0
    assert "Hello from LLM" in result.output
    # Verify the message was augmented with JSON instruction
    proj = patch_client.get_project("PROJ1")
    llm = proj.get_llm("llm1")
    completion_obj = llm.new_completion()
    call_args = completion_obj.with_message.call_args[0][0]
    assert "Respond in valid JSON format" in call_args


def test_llm_embeddings(patch_client):
    result = runner.invoke(app, [
        "llm", "embeddings", "embedding1",
        "--text", "Hello world",
        "--project", "PROJ1",
    ])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed == [[0.4, 0.5, 0.6]]
    proj = patch_client.get_project("PROJ1")
    llm = proj.get_llm("embedding1")
    llm.new_embeddings().add_text.assert_called_with("Hello world")


def test_llm_embeddings_rejects_non_embedding_model(patch_client):
    result = runner.invoke(app, [
        "llm", "embeddings", "azureopenai:Azure_AI_Connection:4o",
        "--text", "Hello world",
        "--project", "PROJ1",
    ])
    assert result.exit_code == 1
    assert "TEXT_EMBEDDING_EXTRACTION" in result.output


def test_llm_embeddings_json_error_payload_is_single_document(patch_client):
    result = runner.invoke(app, [
        "--errors", "json",
        "llm", "embeddings", "azureopenai:Azure_AI_Connection:4o",
        "--text", "Hello world",
        "--project", "PROJ1",
    ])
    assert result.exit_code == 1
    assert result.stdout == ""
    parsed = json.loads(result.stderr)
    assert parsed["error"]["code"] == "invalid_llm_purpose"
    assert parsed["error"]["details"] == ["Requested LLM ID: azureopenai:Azure_AI_Connection:4o"]
