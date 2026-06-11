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
    result = runner.invoke(app, ["--format", "json", "user", "list"])
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
    result = runner.invoke(app, ["--format", "json", "user", "get", "testuser"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["email"] == "test@test.com"


# --- user delete ---


def test_user_delete(patch_client):
    result = runner.invoke(app, ["user", "delete", "testuser", "--yes"])
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
    result = runner.invoke(app, ["--format", "json", "user", "activity", "admin"])
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


# =============================================================================
# Bulk user create / edit
# =============================================================================


def test_user_bulk_create_dry_run(patch_client):
    result = runner.invoke(
        app,
        [
            "user",
            "bulk-create",
            "--from",
            '[{"login":"alice"},{"login":"bob"}]',
        ],
    )
    assert result.exit_code == 0
    assert "Dry run" in result.output
    patch_client.create_users.assert_not_called()


def test_user_bulk_create_executes(patch_client):
    result = runner.invoke(
        app,
        [
            "user",
            "bulk-create",
            "--from",
            '[{"login":"alice"},{"login":"bob"}]',
            "--yes",
        ],
    )
    # bob fails in the mock, so exit code should be 1
    assert result.exit_code == 1
    patch_client.create_users.assert_called_once()
    assert "alice" in result.output
    assert "FAILURE" in result.output


def test_user_bulk_create_csv(patch_client, tmp_path):
    csv_path = tmp_path / "users.csv"
    csv_path.write_text(
        "login,password,displayName,groups\n"
        "alice,pw1,Alice A,data_team;readers\n"
        "bob,pw2,Bob B,readers\n"
    )
    result = runner.invoke(
        app, ["user", "bulk-create", "--from-csv", str(csv_path), "--yes"]
    )
    assert result.exit_code == 1  # bob fails in mock
    args, _ = patch_client.create_users.call_args
    users_sent = args[0]
    assert users_sent[0]["login"] == "alice"
    assert users_sent[0]["groups"] == ["data_team", "readers"]


def test_user_bulk_create_requires_one_source(patch_client):
    result = runner.invoke(app, ["user", "bulk-create", "--yes"])
    assert result.exit_code == 1
    assert "--from" in result.output


def test_user_bulk_edit_dry_run(patch_client):
    result = runner.invoke(
        app,
        [
            "user",
            "bulk-edit",
            "--from",
            '[{"login":"alice","groups":["admin"]}]',
        ],
    )
    assert result.exit_code == 0
    assert "Dry run" in result.output
    patch_client.edit_users.assert_not_called()


def test_user_bulk_edit_requires_login(patch_client):
    result = runner.invoke(
        app,
        ["user", "bulk-edit", "--from", '[{"groups":["admin"]}]', "--yes"],
    )
    assert result.exit_code == 1
    assert "login" in result.output.lower()


def test_user_bulk_edit_executes(patch_client):
    result = runner.invoke(
        app,
        [
            "user",
            "bulk-edit",
            "--from",
            '[{"login":"alice","groups":["admin"]}]',
            "--yes",
        ],
    )
    assert result.exit_code == 0
    patch_client.edit_users.assert_called_once()


def test_user_bulk_edit_exits_nonzero_on_failures(patch_client):
    patch_client.edit_users.return_value = [
        {"login": "alice", "status": "SUCCESS", "error": ""},
        {"login": "bob", "status": "FAILURE", "error": "User not found"},
    ]
    result = runner.invoke(
        app,
        [
            "user",
            "bulk-edit",
            "--from",
            '[{"login":"alice","groups":["admin"]},{"login":"bob","enabled":false}]',
            "--yes",
        ],
    )
    assert result.exit_code == 1
    assert "1 user(s) failed" in result.output
