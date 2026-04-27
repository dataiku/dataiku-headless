"""Tests for dku govern-user commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_user_list(patch_client):
    result = runner.invoke(app, ["govern", "user", "list"])
    assert result.exit_code == 0
    assert "alice" in result.output


def test_user_list_json(patch_client):
    result = runner.invoke(app, ["govern", "user", "list", "-o", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 1
    assert data[0]["login"] == "alice"


def test_user_get(patch_client):
    result = runner.invoke(app, ["govern", "user", "get", "alice"])
    assert result.exit_code == 0
    assert "alice" in result.output


def test_user_get_json(patch_client):
    result = runner.invoke(app, ["govern", "user", "get", "alice", "-o", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["login"] == "alice"


def test_user_create(patch_client):
    result = runner.invoke(
        app,
        [
            "govern",
            "user",
            "create",
            "bob",
            "--password",
            "secret123",
            "--display-name",
            "Bob Jones",
            "--email",
            "bob@example.com",
        ],
    )
    assert result.exit_code == 0
    gov = patch_client.get_govern_client()
    gov.create_user.assert_called_once()


def test_user_create_bulk(patch_client):
    result = runner.invoke(
        app,
        [
            "govern",
            "user",
            "create-bulk",
            "--definition",
            '[{"login":"bob","password":"pass"}]',
        ],
    )
    assert result.exit_code == 0
    assert "SUCCESS" in result.output


def test_user_edit_bulk(patch_client):
    result = runner.invoke(
        app,
        [
            "govern",
            "user",
            "edit-bulk",
            "--definition",
            '[{"login":"alice","displayName":"Alice Updated"}]',
        ],
    )
    assert result.exit_code == 0
    assert "SUCCESS" in result.output


def test_user_delete_bulk_requires_confirm(patch_client):
    result = runner.invoke(
        app,
        [
            "govern",
            "user",
            "delete-bulk",
            "--definition",
            '["alice"]',
        ],
    )
    assert result.exit_code != 0


def test_user_delete_bulk(patch_client):
    result = runner.invoke(
        app,
        [
            "govern",
            "user",
            "delete-bulk",
            "--definition",
            '["alice"]',
            "--confirm",
        ],
    )
    assert result.exit_code == 0
    assert "SUCCESS" in result.output


def test_user_get_own(patch_client):
    result = runner.invoke(app, ["govern", "user", "get-own"])
    assert result.exit_code == 0


def test_user_get_own_json(patch_client):
    result = runner.invoke(app, ["govern", "user", "get-own", "-o", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["login"] == "me"


def test_user_list_activity(patch_client):
    result = runner.invoke(app, ["govern", "user", "list-activity"])
    assert result.exit_code == 0
    assert "alice" in result.output


def test_user_list_activity_json(patch_client):
    result = runner.invoke(app, ["govern", "user", "list-activity", "-o", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 1
    assert data[0]["login"] == "alice"
