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
    patch_client.sql_query.assert_called_once_with(
        "SELECT 1", connection="myconn", post_queries=None
    )


def test_sql_query_json(patch_client):
    result = runner.invoke(
        app, ["--format", "json", "sql", "query", "SELECT 1", "--connection", "myconn"]
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
        "SELECT * FROM users WHERE active = 1",
        connection="myconn",
        post_queries=None,
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
    assert "id\tname" in result.output


def test_sql_query_empty_result_json(patch_client):
    """Empty result set should return an empty JSON array."""
    patch_client.sql_query.return_value = _make_sql_result(
        [{"name": "id", "type": "int"}],
        [],
    )
    result = runner.invoke(
        app,
        [
            "--format",
            "json",
            "sql",
            "query",
            "SELECT * FROM empty_table",
            "-c",
            "myconn",
        ],
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
        app,
        [
            "--format",
            "json",
            "sql",
            "query",
            "SELECT COUNT(*) as count",
            "-c",
            "myconn",
        ],
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
        app, ["--format", "json", "sql", "query", "SELECT *", "-c", "myconn"]
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
        app,
        ["--format", "json", "sql", "query", "SELECT id, name FROM t", "-c", "myconn"],
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
        app, ["--format", "json", "sql", "query", "SELECT text FROM t", "-c", "myconn"]
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
        app,
        ["--format", "json", "sql", "query", "SELECT * FROM big_table", "-c", "myconn"],
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


def test_sql_query_ddl_auto_commits(patch_client):
    """DDL statements (DROP, CREATE, TRUNCATE, ALTER) return no result set
    AND are silently rolled back by DSS's sql_query endpoint unless we pass
    post_queries=['COMMIT']. The CLI auto-appends the commit and reports
    'Committed on <connection>'.

    DROP is tier-3 cascade: needs --yes AND --confirm-name matching the
    connection.
    """
    result_mock = MagicMock()
    result_mock.get_schema.side_effect = KeyError("schema")
    patch_client.sql_query.return_value = result_mock
    result = runner.invoke(
        app,
        [
            "sql",
            "query",
            'DROP TABLE IF EXISTS "stale_table"',
            "-c",
            "sql_managed",
            "--yes",
            "--confirm-name",
            "sql_managed",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Committed on" in result.output
    assert "sql_managed" in result.output
    patch_client.sql_query.assert_called_once_with(
        'DROP TABLE IF EXISTS "stale_table"',
        connection="sql_managed",
        post_queries=["COMMIT"],
    )


def test_sql_query_insert_auto_commits(patch_client):
    """INSERT is DML — CLI should auto-commit. Tier-2 delete guard: --yes."""
    result_mock = MagicMock()
    result_mock.get_schema.side_effect = Exception("no schema for DML")
    patch_client.sql_query.return_value = result_mock
    result = runner.invoke(
        app,
        [
            "sql",
            "query",
            "INSERT INTO logs (msg) VALUES ('hi')",
            "-c",
            "myconn",
            "--yes",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Committed on" in result.output
    patch_client.sql_query.assert_called_once_with(
        "INSERT INTO logs (msg) VALUES ('hi')",
        connection="myconn",
        post_queries=["COMMIT"],
    )


def test_sql_query_no_auto_commit_flag(patch_client):
    """--no-auto-commit opts out of the COMMIT append. CREATE is tier-2: --yes."""
    result_mock = MagicMock()
    result_mock.get_schema.side_effect = KeyError("schema")
    patch_client.sql_query.return_value = result_mock
    result = runner.invoke(
        app,
        [
            "sql",
            "query",
            "CREATE TABLE t (id int)",
            "-c",
            "myconn",
            "--no-auto-commit",
            "--yes",
        ],
    )
    assert result.exit_code == 0, result.output
    # No auto-commit → old-style "Statement executed" wording
    assert "Statement executed" in result.output
    patch_client.sql_query.assert_called_once_with(
        "CREATE TABLE t (id int)", connection="myconn", post_queries=None
    )


def test_sql_query_ddl_detection_ignores_leading_comments(patch_client):
    """A DDL statement after -- line comments should still be detected as DDL."""
    result_mock = MagicMock()
    result_mock.get_schema.side_effect = KeyError("schema")
    patch_client.sql_query.return_value = result_mock
    query = "-- cleanup\n/* remove stale */\nDROP TABLE t"
    # Use -- to stop Typer from interpreting the leading '--' as a flag
    result = runner.invoke(
        app,
        [
            "sql",
            "query",
            "-c",
            "myconn",
            "--yes",
            "--confirm-name",
            "myconn",
            "--",
            query,
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Committed on" in result.output
    patch_client.sql_query.assert_called_once_with(
        query, connection="myconn", post_queries=["COMMIT"]
    )


def test_sql_query_drop_blocked_without_confirmation(patch_client, monkeypatch):
    """DROP without --yes/--confirm-name is a tier-3 cascade — blocked at exit 77,
    and sql_query is never called (no silent destructive commit)."""
    monkeypatch.delenv("DKU_DANGEROUS", raising=False)
    result = runner.invoke(
        app,
        ["sql", "query", "DROP TABLE customers", "-c", "myconn"],
    )
    assert result.exit_code == 77, result.output
    patch_client.sql_query.assert_not_called()


def test_sql_query_drop_blocked_with_yes_but_no_confirm_name(patch_client, monkeypatch):
    """DROP with --yes but a mismatched/absent --confirm-name stays blocked."""
    monkeypatch.delenv("DKU_DANGEROUS", raising=False)
    result = runner.invoke(
        app,
        ["sql", "query", "DROP TABLE customers", "-c", "myconn", "--yes"],
    )
    assert result.exit_code == 77, result.output
    patch_client.sql_query.assert_not_called()


def test_sql_query_delete_blocked_without_yes(patch_client, monkeypatch):
    """DELETE (DML) without --yes is a tier-2 delete guard — blocked at exit 77."""
    monkeypatch.delenv("DKU_DANGEROUS", raising=False)
    result = runner.invoke(
        app,
        ["sql", "query", "DELETE FROM logs WHERE id < 100", "-c", "myconn"],
    )
    assert result.exit_code == 77, result.output
    patch_client.sql_query.assert_not_called()


def test_sql_query_delete_runs_with_yes(patch_client):
    """DELETE with --yes proceeds and auto-commits."""
    result_mock = MagicMock()
    result_mock.get_schema.side_effect = KeyError("schema")
    patch_client.sql_query.return_value = result_mock
    result = runner.invoke(
        app,
        ["sql", "query", "DELETE FROM logs WHERE id < 100", "-c", "myconn", "--yes"],
    )
    assert result.exit_code == 0, result.output
    assert "Committed on" in result.output
    patch_client.sql_query.assert_called_once_with(
        "DELETE FROM logs WHERE id < 100",
        connection="myconn",
        post_queries=["COMMIT"],
    )


def test_sql_query_select_does_not_auto_commit(patch_client):
    """Plain SELECT must not get a post COMMIT — it's pointless and could confuse some drivers."""
    result = runner.invoke(
        app,
        ["sql", "query", "SELECT 42", "-c", "myconn"],
    )
    assert result.exit_code == 0, result.output
    patch_client.sql_query.assert_called_once_with(
        "SELECT 42", connection="myconn", post_queries=None
    )


def test_sql_query_accepts_and_ignores_project_flag(patch_client):
    """-P is muscle memory from every other command — accept it as a no-op
    (SQL is connection-scoped)."""
    result = runner.invoke(
        app,
        [
            "sql",
            "query",
            "SELECT 1",
            "--connection",
            "my_conn",
            "-P",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# The guard cannot be bypassed by hiding a mutation behind a leading SELECT,
# a comment, a string literal, or a WITH-prefixed CTE.
# ---------------------------------------------------------------------------


def test_sql_query_cte_delete_is_guarded(patch_client, monkeypatch):
    """A data-modifying CTE (WITH ... DELETE) must hit the guard, not slip past
    as a read just because the first keyword is WITH."""
    monkeypatch.delenv("DKU_DANGEROUS", raising=False)
    result = runner.invoke(
        app,
        [
            "sql",
            "query",
            "WITH doomed AS (SELECT id FROM logs WHERE id < 100) "
            "DELETE FROM logs USING doomed WHERE logs.id = doomed.id",
            "-c",
            "myconn",
        ],
    )
    assert result.exit_code == 77, result.output
    patch_client.sql_query.assert_not_called()


def test_sql_query_cte_body_delete_is_guarded(patch_client, monkeypatch):
    monkeypatch.delenv("DKU_DANGEROUS", raising=False)
    result = runner.invoke(
        app,
        [
            "sql",
            "query",
            "WITH deleted AS (DELETE FROM logs WHERE id < 100 RETURNING id) "
            "SELECT * FROM deleted",
            "-c",
            "myconn",
        ],
    )
    assert result.exit_code == 77, result.output
    patch_client.sql_query.assert_not_called()


def test_sql_query_multistatement_drop_is_guarded(patch_client, monkeypatch):
    """A DROP chained after a leading SELECT must be guarded at the CASCADE tier
    (--yes alone is not enough), not hidden by the SELECT first keyword."""
    monkeypatch.delenv("DKU_DANGEROUS", raising=False)
    result = runner.invoke(
        app,
        ["sql", "query", "SELECT 1; DROP TABLE customers", "-c", "myconn", "--yes"],
    )
    assert result.exit_code == 77, result.output
    patch_client.sql_query.assert_not_called()


def test_sql_query_cte_select_is_not_guarded(patch_client):
    """A read-only WITH ... SELECT must stay unguarded and get no auto-COMMIT."""
    query = "WITH recent AS (SELECT * FROM logs LIMIT 5) SELECT * FROM recent"
    result = runner.invoke(app, ["sql", "query", query, "-c", "myconn"])
    assert result.exit_code == 0, result.output
    patch_client.sql_query.assert_called_once_with(
        query, connection="myconn", post_queries=None
    )


def test_sql_query_keyword_in_string_literal_is_not_a_mutation(patch_client):
    """'DROP' inside a string literal must not trip the guard — the statement is
    a SELECT and runs unguarded with no COMMIT."""
    query = "SELECT 'DROP TABLE x' AS note"
    result = runner.invoke(app, ["sql", "query", query, "-c", "myconn"])
    assert result.exit_code == 0, result.output
    patch_client.sql_query.assert_called_once_with(
        query, connection="myconn", post_queries=None
    )


def test_operative_keyword_detection_unit():
    """Direct coverage of the statement classifier across the bypass shapes."""
    from dku_cli.commands.sql import _is_ddl_or_dml, _mutation_tier

    # Bypasses that must now be caught as mutations.
    assert _is_ddl_or_dml("WITH c AS (SELECT 1) DELETE FROM t USING c")
    assert _is_ddl_or_dml(
        "WITH deleted AS (DELETE FROM t RETURNING id) SELECT * FROM deleted"
    )
    assert _is_ddl_or_dml("SELECT 1; DROP TABLE x")
    assert _is_ddl_or_dml("/* hi */ DROP TABLE x")
    assert _is_ddl_or_dml("delete from t")

    # Reads that must stay unguarded.
    assert not _is_ddl_or_dml("SELECT * FROM t")
    assert not _is_ddl_or_dml("WITH c AS (SELECT 1) SELECT * FROM c")
    assert not _is_ddl_or_dml("SELECT 'DROP TABLE x' AS note")

    # Tier escalation: any DROP/TRUNCATE/ALTER in a chain forces CASCADE.
    assert _mutation_tier("INSERT INTO t VALUES (1); DROP TABLE x") == (
        "CASCADE",
        "DROP",
    )
    assert _mutation_tier(
        "WITH deleted AS (DELETE FROM t RETURNING id) SELECT * FROM deleted"
    ) == ("DELETE", "DELETE")
    assert _mutation_tier("DELETE FROM t WHERE id = 1") == ("DELETE", "DELETE")
    assert _mutation_tier("SELECT 1") is None
