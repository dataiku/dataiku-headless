"""Tests for admin commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_admin_logs(patch_client):
    result = runner.invoke(app, ["admin", "logs"])
    assert result.exit_code == 0
    assert "backend.log" in result.output


def test_admin_logs_json(patch_client):
    result = runner.invoke(app, ["admin", "logs", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed[0]["name"] == "backend.log"


def test_admin_get_log(patch_client):
    result = runner.invoke(app, ["admin", "get-log", "backend.log"])
    assert result.exit_code == 0
    assert "DSS started" in result.output


def test_admin_usage(patch_client):
    result = runner.invoke(app, ["admin", "usage"])
    assert result.exit_code == 0
    assert "projects" in result.output
    assert "10" in result.output


def test_admin_usage_json(patch_client):
    result = runner.invoke(app, ["admin", "usage", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["projects"] == 10
    assert parsed["datasets"] == 50


def test_admin_instance_info(patch_client):
    result = runner.invoke(app, ["admin", "instance-info"])
    assert result.exit_code == 0
    assert "DESIGN" in result.output


def test_admin_instance_info_json(patch_client):
    result = runner.invoke(app, ["admin", "instance-info", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["nodeType"] == "DESIGN"
    assert parsed["dssVersion"] == "14.5.0"


def test_admin_sanity_check(patch_client):
    result = runner.invoke(app, ["admin", "sanity-check"])
    assert result.exit_code == 0
    assert "WARNING" in result.output
    assert "CHECK_001" in result.output
