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
