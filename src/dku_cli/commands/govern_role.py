"""dku govern-role — list, get."""

from __future__ import annotations

import typer

from dku_cli.errors import handle_api_error
from dku_cli.helpers import get_govern_client_from_ctx
from dku_cli.output import render, render_raw, resolve_output_format

app = typer.Typer(help="Manage Govern roles.")


@app.command("list")
def list_roles(
    ctx: typer.Context,
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List all Govern roles."""
    output = resolve_output_format(output)
    try:
        govern = get_govern_client_from_ctx(ctx)
        handler = govern.get_roles_permissions_handler()
        roles = handler.list_roles()
        data = []
        for item in roles:
            raw = item.get_raw()
            data.append(
                {
                    "id": raw.get("id", ""),
                    "label": raw.get("label", ""),
                    "description": raw.get("description", ""),
                }
            )
        render(
            data,
            ["id", "label", "description"],
            output_format=output,
            title="Govern Roles",
        )
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def get(
    ctx: typer.Context,
    role_id: str = typer.Argument(help="Role ID (e.g. ro.project_manager)"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Get a role definition."""
    output = resolve_output_format(output)
    try:
        govern = get_govern_client_from_ctx(ctx)
        handler = govern.get_roles_permissions_handler()
        role = handler.get_role(role_id)
        defn = role.get_definition()
        render_raw(defn.get_raw(), output_format=output)
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)
