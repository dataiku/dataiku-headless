"""Tests for whoami command."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_whoami(patch_client):
    result = runner.invoke(app, ["whoami"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["user"] == "testuser"
    assert parsed["url"] == "https://dss.example.com"
    assert parsed["dss_version"] == "14.5.0"


def test_whoami_shows_groups(patch_client):
    result = runner.invoke(app, ["whoami"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["groups"] == ["admin", "data_team"]


def test_whoami_json_format_is_structured(patch_client):
    result = runner.invoke(app, ["whoami", "--format", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["user"] == "testuser"


def test_whoami_ids_outputs_user_only(patch_client):
    result = runner.invoke(app, ["whoami", "--format", "ids"])
    assert result.exit_code == 0
    assert result.output == "testuser\n"
