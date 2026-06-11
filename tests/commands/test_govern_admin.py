"""Tests for admin commands on govern blueprint, govern role, govern custom-page (create, set-definition, delete)."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


# ── Blueprint admin ──────────────────────────────────────────────────


def test_blueprint_create(patch_client):
    result = runner.invoke(
        app,
        [
            "govern",
            "blueprint",
            "create",
            "my_bp",
            "--definition",
            '{"name": "My Blueprint", "icon": "star"}',
        ],
    )
    assert result.exit_code == 0
    gov = patch_client.get_govern_client()
    gov.get_blueprint_designer.return_value.create_blueprint.assert_called_once()


def test_blueprint_create_json(patch_client):
    result = runner.invoke(
        app,
        [
            "--format",
            "quiet",
            "govern",
            "blueprint",
            "create",
            "my_bp",
            "--definition",
            '{"name": "My Blueprint"}',
        ],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["id"] == "bp.custom.my_bp"


def test_blueprint_set_definition(patch_client):
    result = runner.invoke(
        app,
        [
            "govern",
            "blueprint",
            "set-definition",
            "bp.custom.my_bp",
            "--definition",
            '{"name": "Updated Blueprint"}',
        ],
    )
    assert result.exit_code == 0


def test_blueprint_delete_requires_confirm(patch_client):
    result = runner.invoke(app, ["govern", "blueprint", "delete", "bp.custom.my_bp"])
    assert result.exit_code != 0


def test_blueprint_delete(patch_client):
    result = runner.invoke(
        app, ["govern", "blueprint", "delete", "bp.custom.my_bp", "--confirm"]
    )
    assert result.exit_code == 0
    gov = patch_client.get_govern_client()
    gov.get_blueprint_designer.return_value.get_blueprint.return_value.delete.assert_called_once()


# ── Role admin ───────────────────────────────────────────────────────


def test_role_create(patch_client):
    result = runner.invoke(
        app,
        [
            "govern",
            "role",
            "create",
            "custom_role",
            "--definition",
            '{"label": "Custom Role", "description": "A custom role"}',
        ],
    )
    assert result.exit_code == 0
    gov = patch_client.get_govern_client()
    gov.get_roles_permissions_handler.return_value.create_role.assert_called_once()


def test_role_set_definition(patch_client):
    result = runner.invoke(
        app,
        [
            "govern",
            "role",
            "set-definition",
            "ro.project_manager",
            "--definition",
            '{"label": "Updated Role"}',
        ],
    )
    assert result.exit_code == 0


def test_role_delete_requires_confirm(patch_client):
    result = runner.invoke(app, ["govern", "role", "delete", "ro.custom_role"])
    assert result.exit_code != 0


def test_role_delete(patch_client):
    result = runner.invoke(
        app, ["govern", "role", "delete", "ro.custom_role", "--confirm"]
    )
    assert result.exit_code == 0
    gov = patch_client.get_govern_client()
    gov.get_roles_permissions_handler.return_value.get_role.return_value.delete.assert_called_once()


# ── Custom page admin ───────────────────────────────────────────────


def test_custom_page_create(patch_client):
    result = runner.invoke(
        app,
        [
            "govern",
            "custom-page",
            "create",
            "my_page",
            "--definition",
            '{"name": "My Page", "type": "standard-page"}',
        ],
    )
    assert result.exit_code == 0
    gov = patch_client.get_govern_client()
    gov.get_custom_pages_handler.return_value.create_custom_page.assert_called_once()


def test_custom_page_set_definition(patch_client):
    result = runner.invoke(
        app,
        [
            "govern",
            "custom-page",
            "set-definition",
            "cp.system.governable-items",
            "--definition",
            '{"name": "Updated Page"}',
        ],
    )
    assert result.exit_code == 0


def test_custom_page_delete_requires_confirm(patch_client):
    result = runner.invoke(
        app, ["govern", "custom-page", "delete", "cp.system.governable-items"]
    )
    assert result.exit_code != 0


def test_custom_page_delete(patch_client):
    result = runner.invoke(
        app,
        ["govern", "custom-page", "delete", "cp.system.governable-items", "--confirm"],
    )
    assert result.exit_code == 0
    gov = patch_client.get_govern_client()
    gov.get_custom_pages_handler.return_value.get_custom_page.return_value.delete.assert_called_once()
