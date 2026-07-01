"""Tests for `dku auth export-env` (issue #179)."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.commands import auth_cmd
from dku_cli.commands.auth_cmd import app

runner = CliRunner()


def test_export_env_emits_export_lines(monkeypatch):
    monkeypatch.setattr(auth_cmd, "resolve_auth", lambda **kw: ("https://x", "KEY123"))
    monkeypatch.setattr(auth_cmd, "get_profile_config", lambda p: {})
    monkeypatch.setattr(auth_cmd, "get_active_profile", lambda: "default")

    result = runner.invoke(app, ["export-env"])
    assert result.exit_code == 0, result.output
    assert "export DKU_URL='https://x'" in result.stdout
    assert "export DKU_API_KEY='KEY123'" in result.stdout


def test_export_env_squotes_values(monkeypatch):
    monkeypatch.setattr(auth_cmd, "resolve_auth", lambda **kw: ("https://x", "ab'cd"))
    monkeypatch.setattr(auth_cmd, "get_profile_config", lambda p: {})
    monkeypatch.setattr(auth_cmd, "get_active_profile", lambda: "default")

    result = runner.invoke(app, ["export-env"])
    assert result.exit_code == 0, result.output
    assert "export DKU_API_KEY='ab'\\''cd'" in result.stdout


def test_export_env_json(monkeypatch):
    monkeypatch.setattr(auth_cmd, "resolve_auth", lambda **kw: ("https://x", "KEY123"))
    monkeypatch.setattr(auth_cmd, "get_profile_config", lambda p: {})
    monkeypatch.setattr(auth_cmd, "get_active_profile", lambda: "default")
    monkeypatch.setattr(auth_cmd, "resolve_output_format", lambda: "json")

    result = runner.invoke(app, ["export-env"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload == {"DKU_URL": "https://x", "DKU_API_KEY": "KEY123"}


def test_export_env_in_pod_ticket_errors(monkeypatch):
    monkeypatch.setattr(
        auth_cmd,
        "get_profile_config",
        lambda p: {"auth_mode": auth_cmd.AUTH_MODE_IN_POD_TICKET},
    )
    monkeypatch.setattr(auth_cmd, "get_active_profile", lambda: "default")

    result = runner.invoke(app, ["export-env"])
    assert result.exit_code == 1
    assert "in-pod ticket" in result.output


def test_export_env_help_lists_verb():
    result = runner.invoke(app, ["--help"])
    assert "export-env" in result.output
