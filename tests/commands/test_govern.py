"""Tests for dku govern commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_govern_whoami(patch_client):
    result = runner.invoke(app, ["govern", "whoami"])
    assert result.exit_code == 0
    assert "govern_key" in result.output


def test_govern_whoami_json(patch_client):
    result = runner.invoke(app, ["govern", "whoami", "-o", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["authIdentifier"] == "api:govern_key"


def test_govern_info(patch_client):
    result = runner.invoke(app, ["govern", "info"])
    assert result.exit_code == 0
    assert "govern_node" in result.output or "IKU" in result.output


def test_govern_info_json(patch_client):
    result = runner.invoke(app, ["govern", "info", "-o", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["node_type"] == "GOVERN"
    assert data["node_name"] == "IKU"


def test_govern_not_configured(patch_client):
    patch_client.get_govern_client.return_value = None
    result = runner.invoke(app, ["govern", "whoami"])
    assert result.exit_code != 0
    assert (
        "not enabled" in result.output.lower()
        or "not enabled" in (result.stderr or "").lower()
    )
