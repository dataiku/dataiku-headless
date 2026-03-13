"""Tests for knowledge commands."""

from __future__ import annotations

import json

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
    result = runner.invoke(app, ["knowledge", "create", "My KB", "--project", "PROJ1"])
    assert result.exit_code == 0
    patch_client.get_project("PROJ1").create_knowledge_bank.assert_called_once_with("My KB")


def test_knowledge_get(patch_client):
    result = runner.invoke(app, ["knowledge", "get", "kb1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "kb1" in result.output


def test_knowledge_get_json(patch_client):
    result = runner.invoke(app, ["knowledge", "get", "kb1", "--project", "PROJ1", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["id"] == "kb1"


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
