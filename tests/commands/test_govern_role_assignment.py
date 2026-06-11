"""Tests for dku govern role-assignment commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_role_assignment_list(patch_client):
    result = runner.invoke(app, ["govern", "role-assignment", "list"])
    assert result.exit_code == 0
    assert "bp.system.govern_project" in result.output
    assert "ro.reviewer" in result.output


def test_role_assignment_list_json(patch_client):
    result = runner.invoke(
        app, ["--format", "json", "govern", "role-assignment", "list"]
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0]["blueprint_id"] == "bp.system.govern_project"


def test_role_assignment_get(patch_client):
    result = runner.invoke(
        app, ["govern", "role-assignment", "get", "bp.system.govern_project"]
    )
    assert result.exit_code == 0
    assert "roleAssignmentsRules" in result.output


def test_role_assignment_set_requires_group_or_user(patch_client):
    """Binding nothing is the silent dead-workflow trap — must be rejected."""
    result = runner.invoke(
        app,
        ["govern", "role-assignment", "set", "bp.system.govern_project", "-r", "ro.x"],
    )
    assert result.exit_code == 2
    assert "at least one --group or --user" in result.output.lower()


def test_role_assignment_set_existing_blueprint_saves(patch_client):
    """When the blueprint already has an assignments record, set GETs, patches
    the role's rule, and saves — with the verified rule shape."""
    govern = patch_client.get_govern_client.return_value
    handler = govern.get_roles_permissions_handler.return_value
    ra_def = handler.get_role_assignments.return_value.get_definition.return_value

    result = runner.invoke(
        app,
        [
            "govern",
            "role-assignment",
            "set",
            "bp.system.govern_project",
            "--role",
            "ro.reviewer",
            "--group",
            "data-stewards",
        ],
    )
    assert result.exit_code == 0
    ra_def.save.assert_called_once()
    raw = ra_def.get_raw.return_value
    rule = raw["roleAssignmentsRules"]["ro.reviewer"]
    assert rule == [
        {
            "criteria": [],
            "userContainers": [{"type": "group", "groupName": "data-stewards"}],
            "fieldIds": [],
        }
    ]
    # Existing-blueprint path must NOT POST a new assignment.
    handler.create_role_assignments.assert_not_called()


def test_role_assignment_set_new_blueprint_creates(patch_client):
    """A blueprint with no existing assignments goes through create_role_assignments."""
    govern = patch_client.get_govern_client.return_value
    handler = govern.get_roles_permissions_handler.return_value

    result = runner.invoke(
        app,
        [
            "govern",
            "role-assignment",
            "set",
            "bp.brand_new",
            "--role",
            "ro.reviewer",
            "--user",
            "alice",
        ],
    )
    assert result.exit_code == 0
    handler.create_role_assignments.assert_called_once()
    payload = handler.create_role_assignments.call_args.args[0]
    assert payload["blueprintId"] == "bp.brand_new"
    rule = payload["roleAssignmentsRules"]["ro.reviewer"]
    assert rule[0]["userContainers"] == [{"type": "user", "login": "alice"}]


def test_role_assignment_delete_blocked_without_yes(patch_client):
    """delete is a DELETE-tier guard: blocked = reserved exit 77, no API call."""
    govern = patch_client.get_govern_client.return_value
    handler = govern.get_roles_permissions_handler.return_value
    result = runner.invoke(
        app, ["govern", "role-assignment", "delete", "bp.system.govern_project"]
    )
    assert result.exit_code == 77
    assert "--yes" in result.output
    handler.get_role_assignments.return_value.delete.assert_not_called()


def test_role_assignment_delete_with_confirm(patch_client):
    govern = patch_client.get_govern_client.return_value
    handler = govern.get_roles_permissions_handler.return_value
    result = runner.invoke(
        app,
        ["govern", "role-assignment", "delete", "bp.system.govern_project", "--yes"],
    )
    assert result.exit_code == 0
    handler.get_role_assignments.return_value.delete.assert_called_once()
