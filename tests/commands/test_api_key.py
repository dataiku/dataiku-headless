"""Tests for API key commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_api_key_list(patch_client):
    result = runner.invoke(app, ["api-key", "list"])
    assert result.exit_code == 0
    assert "ak1" in result.output
    assert "CI Key" in result.output


def test_api_key_list_json(patch_client):
    result = runner.invoke(app, ["api-key", "list", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 1
    assert parsed[0]["id"] == "ak1"


def test_api_key_get(patch_client):
    result = runner.invoke(app, ["api-key", "get", "ak1"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["id"] == "ak1"


def test_api_key_create(patch_client):
    result = runner.invoke(app, ["api-key", "create", "--label", "New Key"])
    assert result.exit_code == 0
    assert "Created" in result.output
    assert "secret123" in result.output
    patch_client.create_global_api_key.assert_called_once_with(
        label="New Key", description=None, admin=False
    )


def test_api_key_create_json(patch_client):
    result = runner.invoke(app, ["api-key", "create", "--label", "Test", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["id"] == "ak1"
    assert parsed["key"] == "secret123"


def test_api_key_delete(patch_client):
    result = runner.invoke(app, ["api-key", "delete", "ak1", "--yes"])
    assert result.exit_code == 0
    assert "Deleted" in result.output


def test_api_key_list_personal(patch_client):
    result = runner.invoke(app, ["api-key", "list-personal"])
    assert result.exit_code == 0
    assert "pak-1" in result.output


def test_api_key_list_personal_json(patch_client):
    result = runner.invoke(app, ["api-key", "list-personal", "-o", "json"])
    assert result.exit_code == 0
    import json as _json

    data = _json.loads(result.output)
    assert data[0]["id"] == "pak-1"
