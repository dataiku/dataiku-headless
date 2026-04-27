"""Tests for RAG LLM commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


# --- list ---


def test_rag_list_table(patch_client):
    result = runner.invoke(app, ["rag", "list", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "rag1" in result.output
    assert "Customer Support RAG" in result.output


def test_rag_list_json(patch_client):
    result = runner.invoke(app, ["rag", "list", "--project", "PROJ1", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 1
    assert parsed[0]["id"] == "rag1"
    assert parsed[0]["name"] == "Customer Support RAG"


def test_rag_list_env_project(patch_client, monkeypatch):
    monkeypatch.setenv("DKU_PROJECT", "PROJ1")
    result = runner.invoke(app, ["rag", "list"])
    assert result.exit_code == 0


# --- create ---


def test_rag_create(patch_client):
    result = runner.invoke(
        app,
        [
            "rag",
            "create",
            "My RAG",
            "--kb",
            "kb1",
            "--llm",
            "openai:gpt-4o",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Created" in result.output
    proj = patch_client.get_project("PROJ1")
    proj.create_retrieval_augmented_llm.assert_called_once_with(
        "My RAG", "kb1", "openai:gpt-4o"
    )


def test_rag_create_json(patch_client):
    result = runner.invoke(
        app,
        [
            "rag",
            "create",
            "My RAG",
            "--kb",
            "kb1",
            "--llm",
            "openai:gpt-4o",
            "--project",
            "PROJ1",
            "-o",
            "json",
        ],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["id"] == "rag1"
    assert parsed["name"] == "My RAG"


# --- get ---


def test_rag_get_table(patch_client):
    result = runner.invoke(app, ["rag", "get", "rag1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "Customer Support RAG" in result.output
    assert "openai:gpt-4o" in result.output


def test_rag_get_json(patch_client):
    result = runner.invoke(
        app, ["rag", "get", "rag1", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["id"] == "rag1"
    # Real API nests llmId/kbRef under versions[0].ragllmSettings
    assert parsed["versions"][0]["ragllmSettings"]["kbRef"] == "kb1"
    assert parsed["versions"][0]["ragllmSettings"]["llmId"] == "openai:gpt-4o"


# --- delete ---


def test_rag_delete(patch_client):
    result = runner.invoke(
        app, ["rag", "delete", "rag1", "--project", "PROJ1", "--yes"]
    )
    assert result.exit_code == 0
    assert "Deleted" in result.output
    rag = patch_client.get_project("PROJ1").get_retrieval_augmented_llm("rag1")
    rag.delete.assert_called_once()


def test_rag_delete_blocks_without_yes(patch_client):
    result = runner.invoke(app, ["rag", "delete", "rag1", "--project", "PROJ1"])
    assert result.exit_code == 77


# --- get-definition ---


def test_rag_get_definition(patch_client):
    result = runner.invoke(app, ["rag", "get-definition", "rag1", "--project", "PROJ1"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["id"] == "rag1"
    assert "versions" in parsed


# --- set-definition ---


def test_rag_set_definition(patch_client):
    new_def = json.dumps({"name": "Updated RAG"})
    result = runner.invoke(
        app,
        [
            "rag",
            "set-definition",
            "rag1",
            "--definition",
            new_def,
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "Updated" in result.output
    rag = patch_client.get_project("PROJ1").get_retrieval_augmented_llm("rag1")
    rag.get_settings.return_value.save.assert_called_once()
