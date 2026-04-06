"""Tests for dku govern-artifact commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_artifact_list(patch_client):
    result = runner.invoke(app, ["govern-artifact", "list"])
    assert result.exit_code == 0
    assert "ar.5" in result.output
    assert "Test Project" in result.output


def test_artifact_list_json(patch_client):
    result = runner.invoke(app, ["govern-artifact", "list", "-o", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 1
    assert data[0]["id"] == "ar.5"
    assert data[0]["blueprint"] == "bp.system.govern_project"


def test_artifact_list_with_blueprint_filter(patch_client):
    result = runner.invoke(
        app,
        ["govern-artifact", "list", "--blueprint", "bp.system.govern_project"],
    )
    assert result.exit_code == 0
    assert "ar.5" in result.output


def test_artifact_list_with_page_size(patch_client):
    result = runner.invoke(app, ["govern-artifact", "list", "--page-size", "10"])
    assert result.exit_code == 0
    gov = patch_client.get_govern_client()
    req = gov.new_artifact_search_request.return_value
    req.fetch_next_batch.assert_called_with(page_size=10)


def test_artifact_get(patch_client):
    result = runner.invoke(app, ["govern-artifact", "get", "ar.5"])
    assert result.exit_code == 0
    assert "ar.5" in result.output


def test_artifact_get_json(patch_client):
    result = runner.invoke(app, ["govern-artifact", "get", "ar.5", "-o", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["id"] == "ar.5"
    assert data["name"] == "Test Project"


def test_artifact_create(patch_client):
    defn = json.dumps(
        {
            "name": "New Artifact",
            "blueprintVersionId": {"blueprintId": "bp.swag", "versionId": "bv.1"},
        }
    )
    result = runner.invoke(app, ["govern-artifact", "create", "--definition", defn])
    assert result.exit_code == 0
    gov = patch_client.get_govern_client()
    gov.create_artifact.assert_called_once()


def test_artifact_delete_requires_confirm(patch_client):
    result = runner.invoke(app, ["govern-artifact", "delete", "ar.5"])
    assert result.exit_code != 0
    assert (
        "confirm" in result.output.lower() or "confirm" in (result.stderr or "").lower()
    )


def test_artifact_delete_with_confirm(patch_client):
    result = runner.invoke(app, ["govern-artifact", "delete", "ar.5", "--confirm"])
    assert result.exit_code == 0
    gov = patch_client.get_govern_client()
    gov.get_artifact.return_value.delete.assert_called_once()


def test_artifact_set_definition(patch_client):
    new_def = json.dumps({"name": "Updated", "fields": {"description": "New desc"}})
    result = runner.invoke(
        app,
        ["govern-artifact", "set-definition", "ar.5", "--definition", new_def],
    )
    assert result.exit_code == 0
    gov = patch_client.get_govern_client()
    gov.get_artifact.return_value.get_definition.return_value.save.assert_called_once()
