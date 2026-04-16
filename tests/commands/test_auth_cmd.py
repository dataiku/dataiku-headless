"""Tests for auth commands."""

from __future__ import annotations

from unittest.mock import patch

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
