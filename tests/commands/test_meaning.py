"""Tests for meaning commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_meaning_list_table(patch_client):
    result = runner.invoke(app, ["meaning", "list"])
    assert result.exit_code == 0
    assert "country_code" in result.output
    assert "VALUES_LIST" in result.output


def test_meaning_list_json(patch_client):
    result = runner.invoke(app, ["meaning", "list", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 1
    assert parsed[0]["id"] == "country_code"


def test_meaning_list_empty(patch_client):
    patch_client.list_meanings.return_value = []
    result = runner.invoke(app, ["meaning", "list"])
    assert result.exit_code == 0
    assert "no" in result.output.lower()


def test_meaning_list_handles_null_description(patch_client):
    """A meaning whose `description` is explicitly null must render, not crash
    with a TypeError (None[:60]) routed through the 'DSS API error' mapper."""
    patch_client.list_meanings.return_value = [
        {"id": "m1", "label": "L1", "type": "DECLARATIVE", "description": None},
    ]
    result = runner.invoke(app, ["meaning", "list"])
    assert result.exit_code == 0
    assert "m1" in result.output


def test_meaning_get(patch_client):
    result = runner.invoke(app, ["meaning", "get", "country_code"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["id"] == "country_code"
    assert len(parsed["entries"]) == 3


def test_meaning_create(patch_client):
    result = runner.invoke(
        app,
        [
            "meaning",
            "create",
            "email_addr",
            "--label",
            "Email Address",
            "--type",
            "PATTERN",
        ],
    )
    assert result.exit_code == 0
    assert "Created" in result.output
    patch_client.create_meaning.assert_called_once_with(
        "email_addr", "Email Address", "PATTERN", description=None
    )


def test_meaning_create_with_description(patch_client):
    result = runner.invoke(
        app,
        [
            "meaning",
            "create",
            "status",
            "--label",
            "Status",
            "-d",
            "Active or inactive",
        ],
    )
    assert result.exit_code == 0
    patch_client.create_meaning.assert_called_once_with(
        "status", "Status", "DECLARATIVE", description="Active or inactive"
    )


def test_meaning_update(patch_client):
    new_def = json.dumps({"id": "country_code", "label": "Updated"})
    result = runner.invoke(app, ["meaning", "update", "country_code", "-d", new_def])
    assert result.exit_code == 0
    assert "Updated" in result.output
    meaning = patch_client.get_meaning("country_code")
    meaning.set_definition.assert_called_once()
