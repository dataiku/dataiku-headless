"""Tests for config commands."""

from __future__ import annotations

from unittest.mock import patch

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_config_path():
    result = runner.invoke(app, ["config", "path"])
    assert result.exit_code == 0
    assert "config.toml" in result.output


def test_config_list_profiles_does_not_crash():
    """Regression: the alias called the auth command function directly without
    passing `output`, so resolve_output_format got a Typer OptionInfo and
    crashed on `.lower()`."""
    with (
        patch(
            "dku_cli.commands.auth_cmd.get_all_profiles",
            return_value={"local": {"url": "http://localhost:8082"}},
        ),
        patch("dku_cli.commands.auth_cmd.get_active_profile", return_value="local"),
    ):
        result = runner.invoke(app, ["config", "list-profiles"])
    assert result.exit_code == 0
    assert "local" in result.output
    assert "OptionInfo" not in result.output


def test_config_set_default_project():
    with patch("dku_cli.commands.config_cmd.set_default_project") as mock_set:
        result = runner.invoke(app, ["config", "set", "default_project", "MYPROJ"])
        assert result.exit_code == 0
        mock_set.assert_called_once_with("MYPROJ")


def test_config_get_default_project():
    with patch(
        "dku_cli.commands.config_cmd.get_default_project", return_value="MYPROJ"
    ):
        result = runner.invoke(app, ["config", "get", "default_project"])
        assert result.exit_code == 0
        assert "MYPROJ" in result.output


def test_config_set_safety_dangerous():
    with patch("dku_cli.commands.config_cmd.set_dangerous_mode") as mock_set:
        result = runner.invoke(app, ["config", "set-safety", "dangerous"])
        assert result.exit_code == 0
        mock_set.assert_called_once_with(True)


def test_config_set_safety_case_insensitive():
    with patch("dku_cli.commands.config_cmd.set_dangerous_mode") as mock_set:
        result = runner.invoke(app, ["config", "set-safety", "GUARDED"])
        assert result.exit_code == 0
        mock_set.assert_called_once_with(False)


def test_config_set_safety_bad_value():
    result = runner.invoke(app, ["config", "set-safety", "wide-open"])
    assert result.exit_code == 2
    assert "guarded" in result.output


def test_config_get_unknown_key():
    result = runner.invoke(app, ["config", "get", "nonexistent_key"])
    assert result.exit_code != 0


def test_config_set_unknown_key():
    result = runner.invoke(app, ["config", "set", "nonexistent_key", "value"])
    assert result.exit_code != 0


def test_config_set_output_is_unknown_key():
    """The `output` config key was removed; only default_project is settable."""
    result = runner.invoke(app, ["config", "set", "output", "json"])
    assert result.exit_code == 1
    assert "Unknown key" in result.output


def test_config_list():
    with patch(
        "dku_cli.commands.config_cmd.get_config",
        return_value={
            "default": {"url": "https://dss.example.com", "default_project": "PROJ1"},
            "active_profile": "default",
        },
    ):
        result = runner.invoke(app, ["config", "list"])
        assert result.exit_code == 0
