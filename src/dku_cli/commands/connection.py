"""dku connection — list, test, create, get, delete, schemas, tables."""

from __future__ import annotations

from typing import Optional

import typer

from dku_cli.errors import handle_api_error
from dku_cli.helpers import get_client_from_ctx, read_json_input, resolve_project
from dku_cli.output import info, render, render_raw, resolve_output_format, success

app = typer.Typer(help="Manage DSS connections.")


@app.command("list")
def list_connections(
    ctx: typer.Context,
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List all connections (admin only)."""
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        connections = client.list_connections()

        data = []
        for name, conn in connections.items():
            data.append(
                {
                    "name": name,
                    "type": conn.get("type", ""),
                    "allow_write": str(conn.get("allowWrite", "")),
                    "allow_managed": str(conn.get("allowManagedDatasets", "")),
                }
            )

        render(
            data,
            ["name", "type", "allow_write", "allow_managed"],
            output_format=output,
            title="Connections",
            headers={
                "name": "NAME",
                "type": "TYPE",
                "allow_write": "WRITABLE",
                "allow_managed": "MANAGED",
            },
        )
    except Exception as e:
        handle_api_error(e)


@app.command()
def create(
    ctx: typer.Context,
    name: str = typer.Argument(help="Connection name"),
    conn_type: str = typer.Option(
        ..., "--type", "-t", help="Connection type (e.g. PostgreSQL, Snowflake)"
    ),
    definition: Optional[str] = typer.Option(
        None,
        "--definition",
        "-d",
        help="Connection params as JSON (literal, @file.json, or - for stdin)",
    ),
) -> None:
    """Create a new connection."""
    try:
        client = get_client_from_ctx(ctx)
        params = read_json_input(definition) or {}
        client.create_connection(name, conn_type, params)

        success(f"Created connection '{name}' (type: {conn_type})")
    except Exception as e:
        handle_api_error(e)


@app.command()
def test(
    ctx: typer.Context,
    connection_name: str = typer.Argument(help="Connection name"),
) -> None:
    """Test a connection."""
    try:
        client = get_client_from_ctx(ctx)
        conn = client.get_connection(connection_name)
        result = conn.test()
        ok = result.get("ok", False)
        if ok:
            success(f"Connection '{connection_name}' is working")
        else:
            from dku_cli.output import error

            msg = result.get("errorMessage", "Unknown error")
            error(f"Connection '{connection_name}' test failed: {msg}")
    except Exception as e:
        handle_api_error(e)


@app.command()
def get(
    ctx: typer.Context,
    name: str = typer.Argument(help="Connection name"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Get connection details as JSON (admin only)."""
    output = resolve_output_format(output, allowed=("json",), default="json")
    try:
        client = get_client_from_ctx(ctx)
        conn = client.get_connection(name)
        settings = conn.get_settings()
        render_raw(settings.get_raw(), output_format=output)
    except Exception as e:
        handle_api_error(e)


@app.command()
def delete(
    ctx: typer.Context,
    name: str = typer.Argument(help="Connection name"),
) -> None:
    """Delete a connection (admin only)."""
    try:
        client = get_client_from_ctx(ctx)
        conn = client.get_connection(name)
        conn.delete()
        success(f"Deleted connection '{name}'")
    except Exception as e:
        handle_api_error(e)


@app.command()
def schemas(
    ctx: typer.Context,
    connection_name: str = typer.Argument(help="Connection name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List schemas/namespaces available in a SQL or Iceberg connection.

    For SQL connections, lists database schemas. For Iceberg connections,
    lists namespaces. Requires project context for API access.

    Use this before 'dku connection tables' to discover what's available.

    Example:
      dku connection schemas my_postgres -P PROJ
      dku connection schemas my_iceberg -P PROJ -o json
    """
    project_key = resolve_project(project)
    fmt = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)

        # Try SQL schemas first (most common), fall back to Iceberg namespaces
        schema_list: list = []
        try:
            schema_list = proj.list_sql_schemas(connection_name)
        except Exception:
            try:
                schema_list = proj.list_iceberg_namespaces(connection_name)
            except Exception:
                pass

        if fmt == "json":
            render_raw(schema_list, output_format="json")
        else:
            if not schema_list:
                info(
                    f"No schemas found for connection '{connection_name}'. "
                    "The connection may not be SQL/Iceberg, or you may lack access. "
                    f"Check connection type: dku connection get {connection_name}"
                )
                return

            data = [{"schema": s} for s in schema_list]
            render(
                data,
                ["schema"],
                output_format=fmt,
                title=f"Schemas ({connection_name})",
                headers={"schema": "SCHEMA"},
            )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def tables(
    ctx: typer.Context,
    connection_name: str = typer.Argument(help="Connection name"),
    schema_name: str | None = typer.Option(
        None,
        "--schema",
        "-s",
        help="Schema/namespace to list tables from (default: all)",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List tables available for import in a SQL or Iceberg connection.

    Discovers what tables exist so agents can create datasets with the
    correct table names. Use --schema to narrow results.

    Example:
      dku connection tables my_postgres -P PROJ
      dku connection tables my_postgres --schema public -P PROJ
      dku connection tables my_iceberg --schema my_namespace -P PROJ -o json
    """
    project_key = resolve_project(project)
    fmt = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)

        # Try SQL tables first (most common), fall back to Iceberg tables
        table_list: list = []
        try:
            table_list = proj.list_sql_tables(connection_name, schema_name=schema_name)
        except Exception:
            try:
                table_list = proj.list_iceberg_tables(
                    connection_name, namespace=schema_name
                )
            except Exception:
                pass

        if fmt == "json":
            render_raw(table_list, output_format="json")
        else:
            if not table_list:
                hint = f" in schema '{schema_name}'" if schema_name else ""
                info(
                    f"No tables found for connection '{connection_name}'{hint}. "
                    "Try listing schemas first: "
                    f"dku connection schemas {connection_name} -P {project_key}"
                )
                return

            # Normalize keys — SQL returns {schema, table}, Iceberg returns {namespace, table}
            data = []
            for t in table_list:
                scope = t.get("schema") or t.get("namespace") or ""
                data.append({"schema": scope, "table": t.get("table", "")})

            render(
                data,
                ["schema", "table"],
                output_format=fmt,
                title=f"Tables ({connection_name})",
                headers={"schema": "SCHEMA", "table": "TABLE"},
            )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)
