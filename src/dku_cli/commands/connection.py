"""dku connection — list, test, create, get, delete."""

from __future__ import annotations

from typing import Optional

import typer

from dku_cli.errors import handle_api_error
from dku_cli.helpers import get_client_from_ctx, read_json_input
from dku_cli.output import render, render_raw, resolve_output_format, success

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
