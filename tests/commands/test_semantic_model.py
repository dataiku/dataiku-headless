"""Tests for semantic-model commands."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helper: simulate name-based resolution (ID fails, name lookup succeeds)
# ---------------------------------------------------------------------------


def _setup_name_resolution(patch_client):
    """Configure mocks so get_semantic_model raises for non-ID args, enabling name fallback."""
    proj = patch_client.get_project("PROJ1")
    sm_mock = proj.get_semantic_model.return_value  # the default mock

    def _get_sm(ref):
        if ref == "sm1":
            return sm_mock
        bad = MagicMock()
        bad._get_definition.side_effect = Exception("Object not found: sm_ref")
        return bad

    proj.get_semantic_model.side_effect = _get_sm
    return proj, sm_mock


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


def test_list(patch_client):
    result = runner.invoke(app, ["semantic-model", "list", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "sm1" in result.output


def test_list_json(patch_client):
    result = runner.invoke(
        app, ["semantic-model", "list", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["id"] == "sm1"
    assert parsed[0]["name"] == "My Semantic Model"


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


def test_create(patch_client):
    result = runner.invoke(
        app,
        ["semantic-model", "create", "My Semantic Model", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    patch_client.get_project("PROJ1").create_semantic_model.assert_called_once_with(
        "My Semantic Model"
    )


def test_create_if_not_exists_when_exists(patch_client):
    """--if-not-exists silently skips when SM already exists."""
    proj = patch_client.get_project("PROJ1")
    proj.create_semantic_model.side_effect = Exception("Semantic model already exists")
    result = runner.invoke(
        app,
        [
            "semantic-model",
            "create",
            "My Semantic Model",
            "--if-not-exists",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "already exists" in result.output.lower()


def test_create_if_not_exists_when_new(patch_client):
    """--if-not-exists creates normally when SM doesn't exist."""
    result = runner.invoke(
        app,
        [
            "semantic-model",
            "create",
            "My Semantic Model",
            "--if-not-exists",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    patch_client.get_project("PROJ1").create_semantic_model.assert_called_once()


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------


def test_get(patch_client):
    result = runner.invoke(app, ["semantic-model", "get", "sm1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "sm1" in result.output


def test_get_json(patch_client):
    result = runner.invoke(
        app, ["semantic-model", "get", "sm1", "--project", "PROJ1", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["id"] == "sm1"
    assert parsed["activeVersionId"] == "v1"


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


def test_delete(patch_client):
    result = runner.invoke(
        app, ["semantic-model", "delete", "sm1", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    patch_client.get_project("PROJ1").get_semantic_model(
        "sm1"
    ).delete.assert_called_once()


# ---------------------------------------------------------------------------
# versions
# ---------------------------------------------------------------------------


def test_versions(patch_client):
    result = runner.invoke(
        app, ["semantic-model", "versions", "sm1", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "v1" in result.output
    assert "True" in result.output  # active marker


def test_versions_json(patch_client):
    result = runner.invoke(
        app,
        ["semantic-model", "versions", "sm1", "--project", "PROJ1", "-o", "json"],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["id"] == "v1"
    assert parsed[0]["active"] == "True"


# ---------------------------------------------------------------------------
# get-version
# ---------------------------------------------------------------------------


def test_get_version(patch_client):
    result = runner.invoke(
        app, ["semantic-model", "get-version", "sm1", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "v1" in result.output


def test_get_version_json(patch_client):
    result = runner.invoke(
        app,
        [
            "semantic-model",
            "get-version",
            "sm1",
            "--project",
            "PROJ1",
            "-o",
            "json",
        ],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["id"] == "v1"
    assert "entities" in parsed


def test_get_version_explicit(patch_client):
    """Passing --version explicitly uses that version."""
    result = runner.invoke(
        app,
        [
            "semantic-model",
            "get-version",
            "sm1",
            "--version",
            "v1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    patch_client.get_project("PROJ1").get_semantic_model(
        "sm1"
    ).get_version.assert_called_with("v1")


# ---------------------------------------------------------------------------
# create-version
# ---------------------------------------------------------------------------


def test_create_version(patch_client):
    result = runner.invoke(
        app,
        ["semantic-model", "create-version", "sm1", "v2", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    sm = patch_client.get_project("PROJ1").get_semantic_model("sm1")
    sm.new_version.assert_called_once_with("v2", duplicate_of=None)
    sm.new_version.return_value.save.assert_called_once()


def test_create_version_duplicate(patch_client):
    result = runner.invoke(
        app,
        [
            "semantic-model",
            "create-version",
            "sm1",
            "v2",
            "--duplicate-of",
            "v1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    sm = patch_client.get_project("PROJ1").get_semantic_model("sm1")
    sm.new_version.assert_called_once_with("v2", duplicate_of="v1")
    sm.new_version.return_value.save.assert_called_once()


# ---------------------------------------------------------------------------
# set-version
# ---------------------------------------------------------------------------


def test_set_version(patch_client):
    """set-version merges JSON into version settings and saves."""
    result = runner.invoke(
        app,
        [
            "semantic-model",
            "set-version",
            "sm1",
            "--definition",
            '{"description": "Updated"}',
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    sm = patch_client.get_project("PROJ1").get_semantic_model("sm1")
    version = sm.get_version("v1")
    settings = version.get_settings()
    raw = settings.get_raw()
    assert raw["description"] == "Updated"
    settings.save.assert_called_once()


# ---------------------------------------------------------------------------
# set-active-version
# ---------------------------------------------------------------------------


def test_set_active_version(patch_client):
    result = runner.invoke(
        app,
        [
            "semantic-model",
            "set-active-version",
            "sm1",
            "v1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    patch_client.get_project("PROJ1").get_semantic_model(
        "sm1"
    ).set_active_version_id.assert_called_once_with("v1")


# ---------------------------------------------------------------------------
# distinct-values
# ---------------------------------------------------------------------------


def test_distinct_values(patch_client):
    result = runner.invoke(
        app,
        ["semantic-model", "distinct-values", "sm1", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    assert "entity1" in result.output


def test_distinct_values_json(patch_client):
    result = runner.invoke(
        app,
        [
            "semantic-model",
            "distinct-values",
            "sm1",
            "--project",
            "PROJ1",
            "-o",
            "json",
        ],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert "entity1" in parsed


def test_distinct_values_attribute(patch_client):
    result = runner.invoke(
        app,
        [
            "semantic-model",
            "distinct-values",
            "sm1",
            "--entity",
            "entity1",
            "--attribute",
            "attr1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    sm = patch_client.get_project("PROJ1").get_semantic_model("sm1")
    sm.get_version("v1").get_basic_distinct_values_for_attribute.assert_called_with(
        "entity1", "attr1", max_values=1000
    )


def test_distinct_values_entity_without_attribute(patch_client):
    """Passing --entity without --attribute gives an error."""
    result = runner.invoke(
        app,
        [
            "semantic-model",
            "distinct-values",
            "sm1",
            "--entity",
            "entity1",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "--entity" in result.output or "--attribute" in result.output


# ---------------------------------------------------------------------------
# update-index
# ---------------------------------------------------------------------------


def test_update_index(patch_client):
    result = runner.invoke(
        app,
        ["semantic-model", "update-index", "sm1", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    sm = patch_client.get_project("PROJ1").get_semantic_model("sm1")
    sm.get_version("v1").start_update_distinct_values.assert_called_once()


def test_update_index_wait(patch_client):
    result = runner.invoke(
        app,
        ["semantic-model", "update-index", "sm1", "--wait", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    sm = patch_client.get_project("PROJ1").get_semantic_model("sm1")
    future = sm.get_version("v1").start_update_distinct_values()
    future.wait_for_result.assert_called()


# ---------------------------------------------------------------------------
# Name-to-ID resolution tests
# ---------------------------------------------------------------------------


def test_get_by_name(patch_client):
    """Passing a name instead of ID should resolve via list_semantic_models."""
    proj, sm_mock = _setup_name_resolution(patch_client)
    result = runner.invoke(
        app,
        ["semantic-model", "get", "My Semantic Model", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    proj.list_semantic_models.assert_called_once()


def test_delete_by_name(patch_client):
    """Delete command resolves by name."""
    proj, sm_mock = _setup_name_resolution(patch_client)
    result = runner.invoke(
        app,
        ["semantic-model", "delete", "My Semantic Model", "--project", "PROJ1"],
    )
    assert result.exit_code == 0
    sm_mock.delete.assert_called_once()


def test_not_found(patch_client):
    """Unknown name/ID gives prescriptive error listing available SMs."""
    proj, _ = _setup_name_resolution(patch_client)
    result = runner.invoke(
        app,
        ["semantic-model", "get", "nonexistent", "--project", "PROJ1"],
    )
    assert result.exit_code != 0
    assert "not found" in result.output.lower()
    assert "sm1" in result.output  # should list available SMs
