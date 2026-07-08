"""#255 — dku project get-settings: raw settings dict + --fields dotted paths."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from typer.testing import CliRunner

from dku_cli.commands.project import app

runner = CliRunner()

SETTINGS = {
    "settings": {
        "codeEnvs": {"python": {"mode": "INHERIT", "preventOverride": False}},
        "gitCommitMode": "AUTO",
    }
}


def _client(monkeypatch):
    settings_handle = MagicMock()
    settings_handle.get_raw.return_value = SETTINGS
    proj = MagicMock()
    proj.get_settings.return_value = settings_handle
    client = MagicMock()
    client.get_project.return_value = proj
    monkeypatch.setattr(
        "dku_cli.commands.project.get_client_from_ctx", lambda ctx: client
    )
    return client


def test_get_settings_full(monkeypatch):
    _client(monkeypatch)
    result = runner.invoke(app, ["get-settings", "PROJ"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == SETTINGS["settings"]


def test_get_settings_fields_projection(monkeypatch):
    _client(monkeypatch)
    result = runner.invoke(
        app, ["get-settings", "PROJ", "--fields", "codeEnvs.python.mode,gitCommitMode"]
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == {
        "codeEnvs.python.mode": "INHERIT",
        "gitCommitMode": "AUTO",
    }


def test_get_settings_bad_field_lists_available_keys(monkeypatch):
    _client(monkeypatch)
    result = runner.invoke(app, ["get-settings", "PROJ", "--fields", "codeEnvs.r.mode"])
    assert result.exit_code != 0
    assert "No settings path 'codeEnvs.r.mode'" in result.output
    assert "python" in result.output  # names the keys that DO exist


def test_get_settings_dash_p_resolution(monkeypatch):
    client = _client(monkeypatch)
    result = runner.invoke(app, ["get-settings", "-P", "FLAGPROJ"])
    assert result.exit_code == 0, result.output
    client.get_project.assert_called_once_with("FLAGPROJ")
