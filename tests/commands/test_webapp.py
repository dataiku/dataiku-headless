"""Tests for webapp commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_webapp_list(patch_client):
    result = runner.invoke(app, ["webapp", "list", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "webapp1" in result.output


def test_webapp_list_json(patch_client):
    result = runner.invoke(app, ["webapp", "list", "--project", "PROJ1", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["id"] == "webapp1"


def test_webapp_start(patch_client):
    result = runner.invoke(app, ["webapp", "start", "webapp1", "--project", "PROJ1"])
    assert result.exit_code == 0


def test_webapp_stop(patch_client):
    result = runner.invoke(app, ["webapp", "stop", "webapp1", "--project", "PROJ1"])
    assert result.exit_code == 0


def test_webapp_status(patch_client):
    result = runner.invoke(app, ["webapp", "status", "webapp1", "--project", "PROJ1"])
    assert result.exit_code == 0


def test_webapp_status_json(patch_client):
    result = runner.invoke(app, ["webapp", "status", "webapp1", "--project", "PROJ1", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert any(d["value"] == "True" for d in parsed)
