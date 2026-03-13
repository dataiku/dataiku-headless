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
        "llm", "embeddings", "llm1",
        "--text", "Hello world",
        "--project", "PROJ1",
    ])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed == [[0.1, 0.2, 0.3]]
