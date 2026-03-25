"""Tests for knowledge commands."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_knowledge_list(patch_client):
    result = runner.invoke(app, ["knowledge", "list", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "kb1" in result.output


def test_knowledge_list_json(patch_client):
    result = runner.invoke(app, ["knowledge", "list", "--project", "PROJ1", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["id"] == "kb1"
    assert parsed[0]["name"] == "My KB"


def test_knowledge_create(patch_client):
    result = runner.invoke(app, [
        "knowledge", "create", "My KB",
        "--embedding-llm", "openai:conn:text-embedding-3-small",
        "--project", "PROJ1",
    ])
    assert result.exit_code == 0
    patch_client.get_project("PROJ1").create_knowledge_bank.assert_called_once_with(
        "My KB", "FAISS", "openai:conn:text-embedding-3-small"
    )


def test_knowledge_create_missing_embedding_llm(patch_client):
    """Omitting --embedding-llm gives actionable error with discovery command."""
    result = runner.invoke(app, [
        "knowledge", "create", "My KB",
        "--project", "PROJ1",
    ])
    assert result.exit_code != 0
    assert "embedding-llm" in result.output.lower()
    assert "dku llm list" in result.output


def test_knowledge_create_if_not_exists_when_exists(patch_client):
    """--if-not-exists silently skips when KB already exists."""
    proj = patch_client.get_project("PROJ1")
    proj.create_knowledge_bank.side_effect = Exception("Knowledge bank already exists")
    result = runner.invoke(app, [
        "knowledge", "create", "My KB",
        "--embedding-llm", "openai:conn:text-embedding-3-small",
        "--if-not-exists",
        "--project", "PROJ1",
    ])
    assert result.exit_code == 0
    assert "already exists" in result.output.lower()


def test_knowledge_create_if_not_exists_when_new(patch_client):
    """--if-not-exists creates normally when KB doesn't exist."""
    result = runner.invoke(app, [
        "knowledge", "create", "My KB",
        "--embedding-llm", "openai:conn:text-embedding-3-small",
        "--if-not-exists",
        "--project", "PROJ1",
    ])
    assert result.exit_code == 0
    patch_client.get_project("PROJ1").create_knowledge_bank.assert_called_once()


def test_knowledge_get(patch_client):
    response = MagicMock()
    response.headers = {"Content-Type": "application/json"}
    response.json.return_value = {"id": "kb1", "name": "My KB"}
    patch_client._perform_http.return_value = response
    result = runner.invoke(app, ["knowledge", "get", "kb1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "kb1" in result.output


def test_knowledge_get_json(patch_client):
    response = MagicMock()
    response.headers = {"Content-Type": "application/json"}
    response.json.return_value = {"id": "kb1", "name": "My KB"}
    patch_client._perform_http.return_value = response
    result = runner.invoke(app, ["knowledge", "get", "kb1", "--project", "PROJ1", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["id"] == "kb1"


def test_knowledge_get_sleep_page_error(patch_client):
    response = MagicMock()
    response.headers = {"Content-Type": "text/html; charset=utf-8"}
    response.text = "<html><body>Dataiku instance not found</body></html>"
    patch_client._perform_http.return_value = response
    result = runner.invoke(app, ["knowledge", "get", "kb1", "--project", "PROJ1"])
    assert result.exit_code == 1
    assert "sleep/wake page" in result.output


def test_knowledge_build(patch_client):
    result = runner.invoke(app, ["knowledge", "build", "kb1", "--project", "PROJ1"])
    assert result.exit_code == 0
    patch_client.get_project("PROJ1").get_knowledge_bank("kb1").build.assert_called_once()


def test_knowledge_build_wait(patch_client):
    result = runner.invoke(app, ["knowledge", "build", "kb1", "--project", "PROJ1", "--wait"])
    assert result.exit_code == 0
    future = patch_client.get_project("PROJ1").get_knowledge_bank("kb1").build()
    future.wait_for_result.assert_called()


def test_knowledge_search(patch_client):
    result = runner.invoke(app, ["knowledge", "search", "kb1", "--query", "test query", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "result1" in result.output


def test_knowledge_search_json(patch_client):
    result = runner.invoke(app, ["knowledge", "search", "kb1", "--query", "test query", "--project", "PROJ1", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["content"] == "result1"
    assert parsed[0]["score"] == 0.95


def test_knowledge_search_max(patch_client):
    result = runner.invoke(app, ["knowledge", "search", "kb1", "--query", "test", "--max", "5", "--project", "PROJ1"])
    assert result.exit_code == 0
    patch_client.get_project("PROJ1").get_knowledge_bank("kb1").search.assert_called_with("test", max_documents=5)


def test_knowledge_delete(patch_client):
    result = runner.invoke(app, ["knowledge", "delete", "kb1", "--project", "PROJ1"])
    assert result.exit_code == 0
    patch_client.get_project("PROJ1").get_knowledge_bank("kb1").delete.assert_called_once()
