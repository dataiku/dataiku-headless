"""Tests for macro commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_macro_list(patch_client):
    result = runner.invoke(app, ["macro", "list", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "My Macro" in result.output


def test_macro_list_json(patch_client):
    result = runner.invoke(
        app, ["--format", "json", "macro", "list", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["id"] == "pyrunnable_test_run-macro"


def test_macro_run(patch_client):
    result = runner.invoke(app, ["macro", "run", "macro1", "--project", "PROJ1"])
    assert result.exit_code == 0
