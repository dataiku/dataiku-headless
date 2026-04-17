"""Tests for user commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_user_list(patch_client):
    result = runner.invoke(app, ["user", "list"])
    assert result.exit_code == 0
    assert "admin" in result.output


def test_user_list_json(patch_client):
    result = runner.invoke(app, ["user", "list", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 2
    assert parsed[0]["login"] == "admin"


# --- user create ---


def test_user_create(patch_client):
    result = runner.invoke(
        app,
        [
            "user",
            "create",
            "newuser",
            "--display-name",
            "New User",
            "--email",
            "new@test.com",
        ],
    )
    assert result.exit_code == 0
    patch_client.create_user.assert_called_once_with(
        "newuser", None, "New User", "new@test.com", groups=[]
    )


def test_user_create_with_groups(patch_client):
    result = runner.invoke(
        app,
        [
            "user",
            "create",
            "newuser",
            "--display-name",
            "New User",
            "--email",
            "new@test.com",
            "--password",
            "secret123",
            "--groups",
            "admin,data_team",
        ],
    )
    assert result.exit_code == 0
    patch_client.create_user.assert_called_once_with(
        "newuser",
        "secret123",
        "New User",
        "new@test.com",
        groups=["admin", "data_team"],
    )


# --- user get ---


def test_user_get(patch_client):
    result = runner.invoke(app, ["user", "get", "testuser"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["login"] == "testuser"
    assert parsed["displayName"] == "Test User"


def test_user_get_json(patch_client):
    result = runner.invoke(app, ["user", "get", "testuser", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["email"] == "test@test.com"


# --- user delete ---


def test_user_delete(patch_client):
    result = runner.invoke(app, ["user", "delete", "testuser"])
    assert result.exit_code == 0
    assert "Deleted user" in result.output
    user = patch_client.get_user("testuser")
    user.delete.assert_called_once()


# --- user activity ---


def test_user_activity(patch_client):
    result = runner.invoke(app, ["user", "activity", "admin"])
    assert result.exit_code == 0
    assert "admin" in result.output
    assert "2023" in result.output  # formatted timestamp year


def test_user_activity_json(patch_client):
    result = runner.invoke(app, ["user", "activity", "admin", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["login"] == "admin"
    assert parsed["lastSuccessfulLogin"] == 1700000000000


# --- user add-secret ---


def test_user_add_secret(patch_client):
    result = runner.invoke(
        app, ["user", "add-secret", "admin", "--name", "MY_TOKEN", "--value", "abc123"]
    )
    assert result.exit_code == 0
    assert "Added secret" in result.output
    user = patch_client.get_user("admin")
    user.get_settings().add_secret.assert_called_once_with("MY_TOKEN", "abc123")
    user.get_settings().save.assert_called()
