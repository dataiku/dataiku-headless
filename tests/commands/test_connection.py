"""Tests for connection commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_connection_list(patch_client):
    result = runner.invoke(app, ["connection", "list"])
    assert result.exit_code == 0
    assert "filesystem_managed" in result.output


def test_connection_list_json(patch_client):
    result = runner.invoke(app, ["connection", "list", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 1
    assert parsed[0]["name"] == "filesystem_managed"


def test_connection_test(patch_client):
    result = runner.invoke(app, ["connection", "test", "filesystem_managed"])
    assert result.exit_code == 0


# --- connection create ---


def test_connection_create(patch_client):
    result = runner.invoke(
        app, ["connection", "create", "new_conn", "--type", "PostgreSQL"]
    )
    assert result.exit_code == 0
    patch_client.create_connection.assert_called_once_with("new_conn", "PostgreSQL", {})


def test_connection_create_with_definition(patch_client):
    definition = json.dumps({"host": "db.example.com", "port": 5432})
    result = runner.invoke(
        app,
        [
            "connection",
            "create",
            "new_conn",
            "--type",
            "PostgreSQL",
            "--definition",
            definition,
        ],
    )
    assert result.exit_code == 0
    patch_client.create_connection.assert_called_once_with(
        "new_conn", "PostgreSQL", {"host": "db.example.com", "port": 5432}
    )


# --- connection get ---


def test_connection_get(patch_client):
    result = runner.invoke(app, ["connection", "get", "filesystem_managed"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["name"] == "filesystem_managed"
    assert parsed["type"] == "Filesystem"


def test_connection_get_json(patch_client):
    result = runner.invoke(
        app, ["connection", "get", "filesystem_managed", "-o", "json"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["name"] == "filesystem_managed"


# --- connection delete ---


def test_connection_delete(patch_client):
    result = runner.invoke(app, ["connection", "delete", "filesystem_managed"])
    assert result.exit_code == 0
    assert "Deleted connection" in result.output
    conn = patch_client.get_connection("filesystem_managed")
    conn.delete.assert_called_once()


# --- connection schemas ---


def test_connection_schemas_table(patch_client):
    """Lists SQL schemas in table format."""
    result = runner.invoke(
        app, ["connection", "schemas", "my_postgres", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "public" in result.output
    assert "analytics" in result.output
    assert "staging" in result.output
    proj = patch_client.get_project("PROJ1")
    proj.list_sql_schemas.assert_called_once_with("my_postgres")


def test_connection_schemas_json(patch_client):
    """JSON output returns raw schema list."""
    result = runner.invoke(
        app,
        ["connection", "schemas", "my_postgres", "--project", "PROJ1", "-o", "json"],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed == ["public", "analytics", "staging"]


def test_connection_schemas_falls_back_to_iceberg(patch_client):
    """Falls back to Iceberg namespaces when SQL schemas fail."""
    proj = patch_client.get_project("PROJ1")
    proj.list_sql_schemas.side_effect = Exception("Not a SQL connection")
    result = runner.invoke(
        app, ["connection", "schemas", "my_iceberg", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "default" in result.output
    assert "production" in result.output
    proj.list_iceberg_namespaces.assert_called_once_with("my_iceberg")


def test_connection_schemas_empty(patch_client):
    """No schemas shows informational message."""
    proj = patch_client.get_project("PROJ1")
    proj.list_sql_schemas.return_value = []
    result = runner.invoke(
        app, ["connection", "schemas", "my_conn", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "no schemas" in result.output.lower()


def test_connection_schemas_env_project(patch_client, monkeypatch):
    """Resolves project from DKU_PROJECT env var."""
    monkeypatch.setenv("DKU_PROJECT", "PROJ1")
    result = runner.invoke(app, ["connection", "schemas", "my_postgres"])
    assert result.exit_code == 0
    assert "public" in result.output


# --- connection tables ---


def test_connection_tables_table(patch_client):
    """Lists SQL tables in table format."""
    result = runner.invoke(
        app, ["connection", "tables", "my_postgres", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "customers" in result.output
    assert "orders" in result.output
    assert "revenue_daily" in result.output
    proj = patch_client.get_project("PROJ1")
    proj.list_sql_tables.assert_called_once_with("my_postgres", schema_name=None)


def test_connection_tables_with_schema(patch_client):
    """--schema filters tables to a specific schema."""
    result = runner.invoke(
        app,
        [
            "connection",
            "tables",
            "my_postgres",
            "--schema",
            "public",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    proj.list_sql_tables.assert_called_once_with("my_postgres", schema_name="public")


def test_connection_tables_json(patch_client):
    """JSON output returns raw table list."""
    result = runner.invoke(
        app,
        ["connection", "tables", "my_postgres", "--project", "PROJ1", "-o", "json"],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 3
    assert parsed[0]["schema"] == "public"
    assert parsed[0]["table"] == "customers"


def test_connection_tables_falls_back_to_iceberg(patch_client):
    """Falls back to Iceberg tables when SQL tables fail."""
    proj = patch_client.get_project("PROJ1")
    proj.list_sql_tables.side_effect = Exception("Not a SQL connection")
    result = runner.invoke(
        app, ["connection", "tables", "my_iceberg", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "events" in result.output
    assert "sessions" in result.output
    proj.list_iceberg_tables.assert_called_once_with("my_iceberg", namespace=None)


def test_connection_tables_empty(patch_client):
    """No tables shows informational message with schema hint."""
    proj = patch_client.get_project("PROJ1")
    proj.list_sql_tables.return_value = []
    result = runner.invoke(
        app, ["connection", "tables", "my_conn", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    assert "no tables" in result.output.lower()
    # Rich may wrap the hint across lines, so check key parts separately
    assert "schemas" in result.output
    assert "my_conn" in result.output


def test_connection_tables_empty_with_schema_hint(patch_client):
    """No tables with --schema shows the schema name in the message."""
    proj = patch_client.get_project("PROJ1")
    proj.list_sql_tables.return_value = []
    result = runner.invoke(
        app,
        [
            "connection",
            "tables",
            "my_conn",
            "--schema",
            "missing_schema",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "missing_schema" in result.output


def test_connection_tables_env_project(patch_client, monkeypatch):
    """Resolves project from DKU_PROJECT env var."""
    monkeypatch.setenv("DKU_PROJECT", "PROJ1")
    result = runner.invoke(app, ["connection", "tables", "my_postgres"])
    assert result.exit_code == 0
    assert "customers" in result.output


# --- list --type filter ---


def test_connection_list_with_type_filter(patch_client):
    """--type uses list_connections_names for fast filtering."""
    result = runner.invoke(app, ["connection", "list", "--type", "Snowflake"])
    assert result.exit_code == 0
    assert "Dataiku-Internal-Snowflake" in result.output
    patch_client.list_connections_names.assert_called_once_with("Snowflake")


# --- sync-acls ---


def test_connection_sync_acls_root(patch_client):
    result = runner.invoke(app, ["connection", "sync-acls", "hdfs_conn"])
    assert result.exit_code == 0
    assert "Synced" in result.output
    conn = patch_client.get_connection("hdfs_conn")
    conn.sync_root_acls.assert_called_once()


def test_connection_sync_acls_datasets(patch_client):
    result = runner.invoke(app, ["connection", "sync-acls", "hdfs_conn", "--datasets"])
    assert result.exit_code == 0
    assert "datasets" in result.output.lower()
    conn = patch_client.get_connection("hdfs_conn")
    conn.sync_datasets_acls.assert_called_once()
