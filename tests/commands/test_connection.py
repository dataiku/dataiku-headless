"""Tests for connection commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_connection_list(patch_client):
    result = runner.invoke(app, ["connection", "list"])
    assert result.exit_code == 0
    assert "filesystem_managed" in result.output


def test_connection_list_json(patch_client):
    result = runner.invoke(app, ["connection", "list", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 1
    assert parsed[0]["name"] == "filesystem_managed"


def test_connection_test(patch_client):
    result = runner.invoke(app, ["connection", "test", "filesystem_managed"])
    assert result.exit_code == 0


# --- connection create ---


def test_connection_create(patch_client):
    result = runner.invoke(
        app, ["connection", "create", "new_conn", "--type", "PostgreSQL"]
    )
    assert result.exit_code == 0
    patch_client.create_connection.assert_called_once_with("new_conn", "PostgreSQL", {})


def test_connection_create_with_definition(patch_client):
    definition = json.dumps({"host": "db.example.com", "port": 5432})
    result = runner.invoke(
        app,
        [
            "connection",
            "create",
            "new_conn",
            "--type",
            "PostgreSQL",
            "--definition",
            definition,
        ],
    )
    assert result.exit_code == 0
    patch_client.create_connection.assert_called_once_with(
        "new_conn", "PostgreSQL", {"host": "db.example.com", "port": 5432}
    )


# --- connection get ---


def test_connection_get(patch_client):
    result = runner.invoke(app, ["connection", "get", "filesystem_managed"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["name"] == "filesystem_managed"
    assert parsed["type"] == "Filesystem"


def test_connection_get_json(patch_client):
    result = runner.invoke(
        app, ["connection", "get", "filesystem_managed", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["name"] == "filesystem_managed"


# --- connection delete ---


def test_connection_delete(patch_client):
    result = runner.invoke(app, ["connection", "delete", "filesystem_managed"])
    assert result.exit_code == 0
    assert "Deleted connection" in result.output
    conn = patch_client.get_connection("filesystem_managed")
    conn.delete.assert_called_once()
