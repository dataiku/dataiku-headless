"""dku govern — Govern instance info."""

from __future__ import annotations

import typer

from dku_cli.errors import handle_api_error
from dku_cli.helpers import get_govern_client_from_ctx
from dku_cli.output import render_raw, resolve_output_format

app = typer.Typer(help="Govern instance commands.")


@app.command()
def whoami(
    ctx: typer.Context,
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show current authenticated Govern user."""
    output = resolve_output_format(output)
    try:
        govern = get_govern_client_from_ctx(ctx)
        auth_info = govern.get_auth_info()
        render_raw(auth_info, output_format=output)
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def info(
    ctx: typer.Context,
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show Govern instance information."""
    output = resolve_output_format(output)
    try:
        govern = get_govern_client_from_ctx(ctx)
        inst = govern.get_instance_info()
        data = {
            "node_id": inst.node_id,
            "node_name": inst.node_name,
            "node_type": inst.node_type,
        }
        render_raw(data, output_format=output)
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)
