"""Tests for dku govern-custom-page commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_custom_page_list(patch_client):
    result = runner.invoke(app, ["govern", "custom-page", "list"])
    assert result.exit_code == 0
    assert "governable-items" in result.output


def test_custom_page_list_json(patch_client):
    result = runner.invoke(app, ["--format", "json", "govern", "custom-page", "list"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 1
    assert data[0]["id"] == "cp.system.governable-items"


def test_custom_page_get(patch_client):
    result = runner.invoke(
        app, ["govern", "custom-page", "get", "cp.system.governable-items"]
    )
    assert result.exit_code == 0
    assert "governable-items" in result.output


def test_custom_page_get_json(patch_client):
    result = runner.invoke(
        app,
        [
            "--format",
            "json",
            "govern",
            "custom-page",
            "get",
            "cp.system.governable-items",
        ],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["id"] == "cp.system.governable-items"
