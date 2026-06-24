"""Tests for knowledge commands."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from dataikuapi.utils import DataikuException
from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helper: simulate name-based resolution (ID fails, name lookup succeeds)
# ---------------------------------------------------------------------------


def _setup_name_resolution(patch_client):
    """Configure mocks so get_knowledge_bank raises for non-ID args, enabling name fallback."""
    proj = patch_client.get_project("PROJ1")
    kb_mock = proj.get_knowledge_bank.return_value  # the default mock

    def _get_kb(ref):
        if ref == "kb1":
            return kb_mock
        # For name-based lookups, return a mock whose get_settings raises
        bad = MagicMock()
        bad.get_settings.side_effect = DataikuException("Object not found: kb_ref")
        return bad

    proj.get_knowledge_bank.side_effect = _get_kb
    return proj, kb_mock


def test_knowledge_list(patch_client):
    result = runner.invoke(app, ["knowledge", "list", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "kb1" in result.output


def test_knowledge_list_json(patch_client):
    result = runner.invoke(
        app, ["--format", "json", "knowledge", "list", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["id"] == "kb1"
    assert parsed[0]["name"] == "My KB"


def test_knowledge_create(patch_client):
    result = runner.invoke(
        app,
        [
            "knowledge",
            "create",
            "My KB",
            "--embedding-llm",
            "openai:conn:text-embedding-3-small",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    patch_client.get_project("PROJ1").create_knowledge_bank.assert_called_once_with(
        "My KB", "CHROMA", "openai:conn:text-embedding-3-small"
    )


def test_knowledge_create_missing_embedding_llm(patch_client):
    """Omitting --embedding-llm gives actionable error with discovery command."""
    result = runner.invoke(
        app,
        [
            "knowledge",
            "create",
            "My KB",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "embedding-llm" in result.output.lower()
    assert "dku llm list" in result.output


def test_knowledge_create_if_not_exists_when_exists(patch_client):
    """--if-not-exists silently skips when KB already exists."""
    proj = patch_client.get_project("PROJ1")
    proj.create_knowledge_bank.side_effect = Exception("Knowledge bank already exists")
    result = runner.invoke(
        app,
        [
            "knowledge",
            "create",
            "My KB",
            "--embedding-llm",
            "openai:conn:text-embedding-3-small",
            "--if-not-exists",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "already exists" in result.output.lower()


def test_knowledge_create_if_not_exists_when_new(patch_client):
    """--if-not-exists creates normally when KB doesn't exist."""
    result = runner.invoke(
        app,
        [
            "knowledge",
            "create",
            "My KB",
            "--embedding-llm",
            "openai:conn:text-embedding-3-small",
            "--if-not-exists",
            "--project",
            "PROJ1",
        ],
    )
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
    result = runner.invoke(
        app, ["--format", "json", "knowledge", "get", "kb1", "--project", "PROJ1"]
    )
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
    patch_client.get_project("PROJ1").get_knowledge_bank(
        "kb1"
    ).build.assert_called_once()


def test_knowledge_build_wait(patch_client):
    result = runner.invoke(
        app, ["knowledge", "build", "kb1", "--project", "PROJ1", "--wait"]
    )
    assert result.exit_code == 0
    # kb.build(wait=True) blocks server-side; no wait_for_result() on the result.
    kb = patch_client.get_project("PROJ1").get_knowledge_bank("kb1")
    kb.build.assert_called_with(wait=True)


def test_knowledge_build_wait_warns_on_empty_kb(patch_client):
    kb = patch_client.get_project("PROJ1").get_knowledge_bank("kb1")
    kb.search.return_value = []
    result = runner.invoke(
        app, ["knowledge", "build", "kb1", "--project", "PROJ1", "--wait"]
    )
    assert result.exit_code == 0
    assert "no indexed content" in result.output or "no documents" in result.output
    assert "recipe run" in result.output
    assert "build completed" not in result.output


def test_knowledge_build_wait_probe_failure_is_not_empty(patch_client):
    kb = patch_client.get_project("PROJ1").get_knowledge_bank("kb1")
    kb.search.side_effect = Exception("401 Unauthorized")
    result = runner.invoke(
        app, ["knowledge", "build", "kb1", "--project", "PROJ1", "--wait"]
    )
    assert result.exit_code == 0
    assert "build completed" in result.output
    assert "Could not verify indexed content" in result.output
    assert "401 Unauthorized" in result.output
    assert "no indexed content" not in result.output
    assert "recipe run" not in result.output


def test_knowledge_build_wait_reports_indexed_docs(patch_client):
    result = runner.invoke(
        app, ["knowledge", "build", "kb1", "--project", "PROJ1", "--wait"]
    )
    assert result.exit_code == 0
    assert "build completed" in result.output
    assert "documents indexed" in result.output


def test_knowledge_search(patch_client):
    result = runner.invoke(
        app,
        ["knowledge", "search", "kb1", "--query", "test query", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    assert "result1" in result.output


def test_knowledge_search_json(patch_client):
    result = runner.invoke(
        app,
        [
            "--format",
            "json",
            "knowledge",
            "search",
            "kb1",
            "--query",
            "test query",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["content"] == "result1"
    assert parsed[0]["score"] == 0.95


def test_knowledge_search_max(patch_client):
    result = runner.invoke(
        app,
        [
            "knowledge",
            "search",
            "kb1",
            "--query",
            "test",
            "--max",
            "5",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    patch_client.get_project("PROJ1").get_knowledge_bank(
        "kb1"
    ).search.assert_called_with("test", max_documents=5)


def test_knowledge_delete(patch_client):
    result = runner.invoke(
        app, ["knowledge", "delete", "kb1", "--project", "PROJ1", "--yes"]
    )
    assert result.exit_code == 0
    patch_client.get_project("PROJ1").get_knowledge_bank(
        "kb1"
    ).delete.assert_called_once()


def test_knowledge_delete_prompts_without_yes(patch_client):
    """Delete without --yes aborts on no-input (typer.confirm)."""
    result = runner.invoke(
        app, ["knowledge", "delete", "kb1", "--project", "PROJ1"], input="\n"
    )
    assert result.exit_code != 0
    patch_client.get_project("PROJ1").get_knowledge_bank(
        "kb1"
    ).delete.assert_not_called()


# ---------------------------------------------------------------------------
# Name-to-ID resolution tests
# ---------------------------------------------------------------------------


def test_knowledge_build_by_name(patch_client):
    """Passing a name instead of ID should resolve via list_knowledge_banks."""
    proj, kb_mock = _setup_name_resolution(patch_client)
    result = runner.invoke(app, ["knowledge", "build", "My KB", "--project", "PROJ1"])
    assert result.exit_code == 0
    # Should have resolved "My KB" → "kb1" via list_knowledge_banks fallback
    proj.list_knowledge_banks.assert_called_once()
    kb_mock.build.assert_called_once()


def test_knowledge_search_by_name(patch_client):
    """Search command resolves by name."""
    proj, kb_mock = _setup_name_resolution(patch_client)
    result = runner.invoke(
        app,
        ["knowledge", "search", "My KB", "--query", "test", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    proj.list_knowledge_banks.assert_called_once()


def test_knowledge_delete_by_name(patch_client):
    """Delete command resolves by name."""
    proj, kb_mock = _setup_name_resolution(patch_client)
    result = runner.invoke(
        app, ["knowledge", "delete", "My KB", "--project", "PROJ1", "--yes"]
    )
    assert result.exit_code == 0
    kb_mock.delete.assert_called_once()


def test_knowledge_not_found(patch_client):
    """Unknown name/ID gives prescriptive error listing available KBs."""
    proj, _ = _setup_name_resolution(patch_client)
    result = runner.invoke(
        app, ["knowledge", "build", "nonexistent", "--project", "PROJ1"]
    )
    assert result.exit_code != 0
    assert "not found" in result.output.lower()
    assert "kb1" in result.output  # should list available KBs


# ---------------------------------------------------------------------------
# set-definition tests
# ---------------------------------------------------------------------------


def test_knowledge_set_definition(patch_client):
    """set-definition merges JSON into KB settings and saves."""
    result = runner.invoke(
        app,
        [
            "knowledge",
            "set-definition",
            "kb1",
            "--definition",
            '{"vectorStoreType": "CHROMA"}',
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    kb = patch_client.get_project("PROJ1").get_knowledge_bank("kb1")
    settings = kb.get_settings()
    raw = settings.get_raw()
    assert raw["vectorStoreType"] == "CHROMA"
    settings.save.assert_called_once()


def test_knowledge_set_definition_by_name(patch_client):
    """set-definition resolves KB by name."""
    proj, kb_mock = _setup_name_resolution(patch_client)
    result = runner.invoke(
        app,
        [
            "knowledge",
            "set-definition",
            "My KB",
            "--definition",
            '{"vectorStoreType": "CHROMA"}',
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    proj.list_knowledge_banks.assert_called_once()
    kb_mock.get_settings().save.assert_called()
