"""Tests for sql commands."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def _make_sql_result(schema, rows):
    """Helper to build a mock DSSSQLQuery object."""
    mock = MagicMock()
    mock.get_schema.return_value = schema
    mock.iter_rows.return_value = iter(rows)
    return mock


def test_sql_query_table(patch_client):
    result = runner.invoke(app, ["sql", "query", "SELECT 1", "--connection", "myconn"])
    assert result.exit_code == 0
    assert "val1" in result.output
    assert "val2" in result.output
    patch_client.sql_query.assert_called_once_with("SELECT 1", connection="myconn")


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


def test_sql_query_empty_result(patch_client):
    """Empty result set should render headers but no rows."""
    patch_client.sql_query.return_value = _make_sql_result(
        [{"name": "id", "type": "int"}, {"name": "name", "type": "string"}],
        [],
    )
    result = runner.invoke(
        app, ["sql", "query", "SELECT * FROM empty_table", "-c", "myconn"]
    )
    assert result.exit_code == 0
    # Rich uppercases headers in table output
    assert "ID" in result.output
    assert "NAME" in result.output


def test_sql_query_empty_result_json(patch_client):
    """Empty result set should return an empty JSON array."""
    patch_client.sql_query.return_value = _make_sql_result(
        [{"name": "id", "type": "int"}],
        [],
    )
    result = runner.invoke(
        app, ["sql", "query", "SELECT * FROM empty_table", "-c", "myconn", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed == []


def test_sql_query_single_column(patch_client):
    """Single column result should work correctly."""
    patch_client.sql_query.return_value = _make_sql_result(
        [{"name": "count", "type": "int"}],
        [[42]],
    )
    result = runner.invoke(
        app, ["sql", "query", "SELECT COUNT(*) as count", "-c", "myconn"]
    )
    assert result.exit_code == 0
    assert "42" in result.output


def test_sql_query_single_column_json(patch_client):
    """Single column JSON output."""
    patch_client.sql_query.return_value = _make_sql_result(
        [{"name": "count", "type": "int"}],
        [[42]],
    )
    result = runner.invoke(
        app, ["sql", "query", "SELECT COUNT(*) as count", "-c", "myconn", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 1
    assert parsed[0]["count"] == 42


def test_sql_query_many_columns(patch_client):
    """Wide result set with many columns."""
    cols = [{"name": f"c{i}", "type": "string"} for i in range(20)]
    row = [f"v{i}" for i in range(20)]
    patch_client.sql_query.return_value = _make_sql_result(cols, [row])
    result = runner.invoke(
        app, ["sql", "query", "SELECT *", "-c", "myconn", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 1
    assert parsed[0]["c0"] == "v0"
    assert parsed[0]["c19"] == "v19"


def test_sql_query_null_values(patch_client):
    """NULL values in result rows."""
    patch_client.sql_query.return_value = _make_sql_result(
        [{"name": "id", "type": "int"}, {"name": "name", "type": "string"}],
        [[1, None], [None, "hello"]],
    )
    result = runner.invoke(
        app, ["sql", "query", "SELECT id, name FROM t", "-c", "myconn", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 2
    assert parsed[0]["name"] is None
    assert parsed[1]["id"] is None


def test_sql_query_special_characters(patch_client):
    """Values with special characters (quotes, newlines, unicode)."""
    patch_client.sql_query.return_value = _make_sql_result(
        [{"name": "text", "type": "string"}],
        [['it\'s a "test"'], ["line1\nline2"], ["emoji: \u2603"]],
    )
    result = runner.invoke(
        app, ["sql", "query", "SELECT text FROM t", "-c", "myconn", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 3
    assert "test" in parsed[0]["text"]
    assert "\u2603" in parsed[2]["text"]


def test_sql_query_many_rows(patch_client):
    """Large result set."""
    rows = [[i, f"row_{i}"] for i in range(500)]
    patch_client.sql_query.return_value = _make_sql_result(
        [{"name": "id", "type": "int"}, {"name": "val", "type": "string"}],
        rows,
    )
    result = runner.invoke(
        app, ["sql", "query", "SELECT * FROM big_table", "-c", "myconn", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 500
    assert parsed[0]["id"] == 0
    assert parsed[499]["val"] == "row_499"


def test_sql_query_missing_file(tmp_path):
    """@file.sql pointing to nonexistent file should fail."""
    result = runner.invoke(
        app, ["sql", "query", f"@{tmp_path}/nope.sql", "-c", "myconn"]
    )
    assert result.exit_code != 0


def test_sql_query_api_error(patch_client):
    """API errors should be handled gracefully."""
    patch_client.sql_query.side_effect = Exception("connection refused")
    result = runner.invoke(app, ["sql", "query", "SELECT 1", "-c", "badconn"])
    assert result.exit_code != 0
