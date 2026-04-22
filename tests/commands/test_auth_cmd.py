"""Tests for auth commands."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_auth_logout_all_clears_profile_config():
    with (
        patch(
            "dku_cli.commands.auth_cmd.get_all_profiles",
            return_value={"default": {}, "prod": {}},
        ),
        patch("dku_cli.commands.auth_cmd.delete_api_key") as mock_delete,
        patch(
            "dku_cli.commands.auth_cmd.clear_profile_configs", return_value=2
        ) as mock_clear,
    ):
        result = runner.invoke(app, ["auth", "logout", "--all"])

    assert result.exit_code == 0
    assert mock_delete.call_count == 2
    mock_clear.assert_called_once_with()


def test_auth_logout_removes_profile_from_config():
    with (
        patch("dku_cli.commands.auth_cmd.get_active_profile", return_value="default"),
        patch("dku_cli.commands.auth_cmd.delete_api_key", return_value=False),
        patch(
            "dku_cli.commands.auth_cmd.delete_profile_config", return_value=True
        ) as mock_delete_profile,
    ):
        result = runner.invoke(app, ["auth", "logout"])

    assert result.exit_code == 0
    mock_delete_profile.assert_called_once_with("default")


def test_auth_status_shows_sources_and_project(patch_client):
    project = MagicMock()
    project.get_metadata.return_value = {"label": "Project One"}
    patch_client.get_project.return_value = project

    with (
        patch("dku_cli.commands.auth_cmd.get_active_profile", return_value="default"),
        patch(
            "dku_cli.commands.auth_cmd.get_profile_config",
            return_value={"url": "https://dss.example.com", "default_project": "PROJ1"},
        ),
        patch("dku_cli.commands.auth_cmd.get_default_project", return_value="PROJ1"),
        patch(
            "dku_cli.commands.auth_cmd.resolve_auth",
            return_value=("https://dss.example.com", "secret"),
        ),
        patch(
            "dku_cli.commands.auth_cmd.dataikuapi.DSSClient", return_value=patch_client
        ),
    ):
        result = runner.invoke(app, ["auth", "status"])

    assert result.exit_code == 0
    assert "Profile:" in result.output
    assert "URL Src:" in result.output
    assert "Key Src:" in result.output
    assert "DSS:" in result.output
    assert "Project:" in result.output
    assert "Project OK:" in result.output


def test_auth_status_project_access_error(patch_client):
    patch_client.get_project.side_effect = Exception(
        "NotFoundException: Project MISSING does not exist"
    )

    with (
        patch("dku_cli.commands.auth_cmd.get_active_profile", return_value="default"),
        patch(
            "dku_cli.commands.auth_cmd.get_profile_config",
            return_value={
                "url": "https://dss.example.com",
                "default_project": "MISSING",
            },
        ),
        patch("dku_cli.commands.auth_cmd.get_default_project", return_value="MISSING"),
        patch(
            "dku_cli.commands.auth_cmd.resolve_auth",
            return_value=("https://dss.example.com", "secret"),
        ),
        patch(
            "dku_cli.commands.auth_cmd.dataikuapi.DSSClient", return_value=patch_client
        ),
    ):
        result = runner.invoke(app, ["auth", "status"])

    assert result.exit_code == 0
    assert "Project OK:" in result.output
    assert "NotFoundException: Project MISSING does not exist" in result.output


def test_auth_switch_exits_zero_on_success():
    """Regression: auth switch must exit 0 on success (not 2) for set -e scripts."""
    with (
        patch(
            "dku_cli.commands.auth_cmd.get_all_profiles",
            return_value={"default": {}, "analytics": {}},
        ),
        patch("dku_cli.commands.auth_cmd.set_active_profile") as mock_set,
    ):
        result = runner.invoke(app, ["auth", "switch", "analytics"])

    assert result.exit_code == 0
    assert "Switched to profile" in result.output
    mock_set.assert_called_once_with("analytics")


def test_auth_switch_nonexistent_profile_exits_one():
    with patch(
        "dku_cli.commands.auth_cmd.get_all_profiles",
        return_value={"default": {}},
    ):
        result = runner.invoke(app, ["auth", "switch", "nonexistent"])

    assert result.exit_code == 1
    assert "does not exist" in result.output
