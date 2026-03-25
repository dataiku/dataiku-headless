"""Tests for plugin commands."""

from __future__ import annotations

import json
from unittest.mock import MagicMock
from zipfile import ZipFile

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def _write_plugin_zip(path, plugin_id: str) -> None:
    with ZipFile(path, "w") as archive:
        archive.writestr(
            "plugin.json", json.dumps({"id": plugin_id, "version": "1.0.0"})
        )


def test_plugin_list_table(patch_client):
    result = runner.invoke(app, ["plugin", "list"])
    assert result.exit_code == 0
    assert "my-plugin" in result.output


def test_plugin_list_json(patch_client):
    result = runner.invoke(app, ["plugin", "list", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 2
    assert parsed[0]["id"] == "my-plugin"
    assert parsed[0]["version"] == "1.0.0"


def test_plugin_list_handles_dict_quirk(mock_client):
    """dataikuapi returns dicts from list_plugins(), not objects."""
    plugins = mock_client.list_plugins()
    assert isinstance(plugins[0], dict)
    assert "id" in plugins[0]


def test_plugin_push_missing_file():
    result = runner.invoke(app, ["plugin", "push", "/nonexistent/plugin.zip"])
    assert result.exit_code != 0


def test_plugin_settings_view(patch_client):
    plugin_obj = MagicMock()
    settings = MagicMock()
    settings.get_raw.return_value = {
        "codeEnvName": "plugin_test_managed",
        "config": {"param1": "value1", "password_param": "secret"},
    }
    plugin_obj.get_settings.return_value = settings
    patch_client.get_plugin.return_value = plugin_obj

    result = runner.invoke(app, ["plugin", "settings", "my-plugin"])
    assert result.exit_code == 0
    assert "****" in result.output
    assert "secret" not in result.output


def test_plugin_push_reads_plugin_id_from_archive(tmp_path, patch_client):
    plugin_obj = MagicMock()
    patch_client.get_plugin.return_value = plugin_obj
    patch_client.list_plugins.return_value = [
        {"id": "real-plugin", "version": "1.0.0", "isDev": False}
    ]

    zip_path = tmp_path / "release-1.2.3.zip"
    _write_plugin_zip(zip_path, "real-plugin")

    result = runner.invoke(app, ["plugin", "push", str(zip_path)])

    assert result.exit_code == 0
    plugin_obj.update_from_zip.assert_called_once()
    patch_client.install_plugin_from_archive.assert_not_called()
    assert "Updated plugin 'real-plugin'" in result.output


def test_plugin_push_installs_when_plugin_is_missing(tmp_path, patch_client):
    patch_client.list_plugins.return_value = []

    zip_path = tmp_path / "release-1.2.3.zip"
    _write_plugin_zip(zip_path, "real-plugin")

    result = runner.invoke(app, ["plugin", "push", str(zip_path)])

    assert result.exit_code == 0
    patch_client.install_plugin_from_archive.assert_called_once()
    assert "Installed plugin 'real-plugin'" in result.output
