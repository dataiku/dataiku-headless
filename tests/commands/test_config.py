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


def test_config_get_unknown_key():
    result = runner.invoke(app, ["config", "get", "nonexistent_key"])
    assert result.exit_code != 0


def test_config_set_unknown_key():
    result = runner.invoke(app, ["config", "set", "nonexistent_key", "value"])
    assert result.exit_code != 0


def test_config_set_output_invalid():
    result = runner.invoke(app, ["config", "set", "output", "yaml"])
    assert result.exit_code != 0


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
