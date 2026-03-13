"""Tests for code-env commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_codeenv_list(patch_client):
    result = runner.invoke(app, ["code-env", "list"])
    assert result.exit_code == 0
    assert "py39" in result.output


def test_codeenv_list_json(patch_client):
    result = runner.invoke(app, ["code-env", "list", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 1
    assert parsed[0]["name"] == "py39"


def test_codeenv_get(patch_client):
    result = runner.invoke(app, ["code-env", "get", "py39"])
    assert result.exit_code == 0
    assert "py39" in result.output


def test_codeenv_get_json(patch_client):
    result = runner.invoke(app, ["code-env", "get", "py39", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["envName"] == "py39"


def test_codeenv_delete(patch_client):
    result = runner.invoke(app, ["code-env", "delete", "py39"])
    assert result.exit_code == 0


def test_codeenv_update(patch_client):
    result = runner.invoke(app, ["code-env", "update", "py39"])
    assert result.exit_code == 0
