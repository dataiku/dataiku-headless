"""Tests for `dku dataset count` and `dku dataset query`.

These commands resolve a SQL-backed dataset's physical table (`${projectKey}_<NAME>`)
and connection so an agent can count/query by logical name instead of hand-resolving
the templated table. Non-SQL datasets fall back to the COUNT_RECORDS metric (count)
or a prescriptive error (query).
"""

from __future__ import annotations

from unittest.mock import MagicMock

from typer.testing import CliRunner

from dku_cli.commands.dataset import _resolve_sql_table
from dku_cli.main import app

runner = CliRunner()


# --- _resolve_sql_table helper ---


def test_resolve_sql_table_substitutes_project_key():
    ds_def = {
        "type": "Snowflake",
        "params": {"connection": "SF", "table": "${projectKey}_ORDERS"},
    }
    assert _resolve_sql_table(ds_def, "PROJ") == ("SF", "PROJ_ORDERS")


def test_resolve_sql_table_qualifies_with_schema_and_catalog():
    ds_def = {
        "params": {
            "connection": "BQ",
            "table": "${projectKey}_O",
            "schema": "PUBLIC",
            "catalog": "CAT",
        }
    }
    assert _resolve_sql_table(ds_def, "P") == ("BQ", "CAT.PUBLIC.P_O")


def test_resolve_sql_table_none_for_filesystem():
    assert _resolve_sql_table({"type": "UploadedFiles", "params": {}}, "P") is None
    assert _resolve_sql_table({"params": {"connection": "SF"}}, "P") is None  # no table


def test_resolve_sql_table_none_for_query_mode_with_leftover_table():
    """A query-mode SQL dataset can carry a stale/templated `table` value, but
    DSS evaluates its customQuery — not that table. params.mode != 'table' must
    fall through to None so count/query use the metric path, not a wrong table."""
    ds_def = {
        "type": "Snowflake",
        "params": {
            "connection": "SF",
            "mode": "query",
            "table": "${projectKey}_ORDERS",
        },
    }
    assert _resolve_sql_table(ds_def, "PROJ") is None


def test_resolve_sql_table_resolves_explicit_table_mode():
    """An explicit params.mode == 'table' still resolves as table-backed."""
    ds_def = {
        "type": "Snowflake",
        "params": {"connection": "SF", "mode": "table", "table": "${projectKey}_O"},
    }
    assert _resolve_sql_table(ds_def, "PROJ") == ("SF", "PROJ_O")


# --- dataset count ---


def test_count_sql_backed_resolves_physical_table(patch_client):
    ds = patch_client.get_project("PROJ1").get_dataset("orders")
    ds.get_definition.return_value = {
        "type": "Snowflake",
        "params": {"connection": "SF", "table": "${projectKey}_ORDERS"},
    }
    res = MagicMock()
    res.iter_rows.return_value = iter([[60]])
    patch_client.sql_query.return_value = res

    result = runner.invoke(app, ["dataset", "count", "orders", "-P", "PROJ1"])
    assert result.exit_code == 0
    assert "60" in result.output
    sql = patch_client.sql_query.call_args[0][0]
    assert "PROJ1_ORDERS" in sql  # ${projectKey} resolved
    assert patch_client.sql_query.call_args.kwargs["connection"] == "SF"


def test_count_sql_backed_applies_where(patch_client):
    ds = patch_client.get_project("PROJ1").get_dataset("orders")
    ds.get_definition.return_value = {
        "type": "Snowflake",
        "params": {"connection": "SF", "table": "${projectKey}_ORDERS"},
    }
    res = MagicMock()
    res.iter_rows.return_value = iter([[23]])
    patch_client.sql_query.return_value = res

    result = runner.invoke(
        app,
        ["dataset", "count", "orders", "--where", "\"region\" = 'EU'", "-P", "PROJ1"],
    )
    assert result.exit_code == 0
    sql = patch_client.sql_query.call_args[0][0]
    assert "WHERE \"region\" = 'EU'" in sql


def test_count_non_sql_uses_metric(patch_client):
    ds = patch_client.get_project("PROJ1").get_dataset("orders")
    ds.get_definition.return_value = {"type": "UploadedFiles", "params": {}}
    ds.get_last_metric_values.return_value.get_global_value.side_effect = None
    ds.get_last_metric_values.return_value.get_global_value.return_value = 42

    result = runner.invoke(app, ["dataset", "count", "orders", "-P", "PROJ1"])
    assert result.exit_code == 0
    # Non-SQL datasets must use the COUNT_RECORDS metric, never SQL.
    patch_client.sql_query.assert_not_called()
    ds.compute_metrics.assert_called_once()
    assert "42" in result.output


def test_count_where_on_non_sql_is_prescriptive_error(patch_client):
    ds = patch_client.get_project("PROJ1").get_dataset("orders")
    ds.get_definition.return_value = {"type": "UploadedFiles", "params": {}}

    result = runner.invoke(
        app, ["dataset", "count", "orders", "--where", "x=1", "-P", "PROJ1"]
    )
    assert result.exit_code != 0
    assert "only supported on SQL-backed" in result.output


def test_count_query_mode_sql_uses_metric_not_table(patch_client):
    """A query-mode SQL dataset with a leftover `table` must use the metric path,
    not run COUNT(*) against the stale physical table."""
    ds = patch_client.get_project("PROJ1").get_dataset("orders")
    ds.get_definition.return_value = {
        "type": "Snowflake",
        "params": {
            "connection": "SF",
            "mode": "query",
            "table": "${projectKey}_ORDERS",
        },
    }
    ds.get_last_metric_values.return_value.get_global_value.side_effect = None
    ds.get_last_metric_values.return_value.get_global_value.return_value = 17

    result = runner.invoke(app, ["dataset", "count", "orders", "-P", "PROJ1"])
    assert result.exit_code == 0
    # Key assertion: the leftover physical table is NOT queried; metric path used.
    patch_client.sql_query.assert_not_called()
    ds.compute_metrics.assert_called_once()
    assert "17" in result.output


# --- dataset query ---


def test_query_substitutes_table_token(patch_client):
    ds = patch_client.get_project("PROJ1").get_dataset("orders")
    ds.get_definition.return_value = {
        "type": "Snowflake",
        "params": {"connection": "SF", "table": "${projectKey}_ORDERS"},
    }

    result = runner.invoke(
        app,
        ["dataset", "query", "orders", "-q", "SELECT * FROM {{table}}", "-P", "PROJ1"],
    )
    assert result.exit_code == 0
    sql = patch_client.sql_query.call_args[0][0]
    assert sql == "SELECT * FROM PROJ1_ORDERS"


def test_query_non_sql_is_prescriptive_error(patch_client):
    ds = patch_client.get_project("PROJ1").get_dataset("orders")
    ds.get_definition.return_value = {"type": "UploadedFiles", "params": {}}

    result = runner.invoke(
        app, ["dataset", "query", "orders", "-q", "SELECT 1", "-P", "PROJ1"]
    )
    assert result.exit_code != 0
    assert "not a SQL-table-backed dataset" in result.output
