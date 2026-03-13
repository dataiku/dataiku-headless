"""Tests for sql commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_sql_query_table(patch_client):
    result = runner.invoke(
        app, ["sql", "query", "SELECT 1", "--connection", "myconn"]
    )
    assert result.exit_code == 0
    assert "val1" in result.output
    assert "val2" in result.output
    patch_client.sql_query.assert_called_once_with(
        "SELECT 1", connection="myconn"
    )


def test_sql_query_json(patch_client):
    result = runner.invoke(
        app, ["sql", "query", "SELECT 1", "--connection", "myconn", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 2
    assert parsed[0]["col1"] == "val1"
    assert parsed[1]["col2"] == "val4"


def test_sql_query_from_file(tmp_path, patch_client):
    sql_file = tmp_path / "query.sql"
    sql_file.write_text("SELECT * FROM users WHERE active = 1")

    result = runner.invoke(
        app, ["sql", "query", f"@{sql_file}", "--connection", "myconn"]
    )
    assert result.exit_code == 0
    patch_client.sql_query.assert_called_once_with(
        "SELECT * FROM users WHERE active = 1", connection="myconn"
    )
