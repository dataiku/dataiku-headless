"""dku govern group — list, get, create, delete."""

from __future__ import annotations

from typing import Optional

import typer

from dku_cli.errors import handle_api_error
from dku_cli.helpers import get_govern_client_from_ctx
from dku_cli.output import hint, render, render_raw, resolve_output_format, success
from dku_cli.safety import Tier, guard

app = typer.Typer(help="Manage Govern groups (admin).")


@app.command("list")
def list_groups(
    ctx: typer.Context,
) -> None:
    """List all Govern groups. Requires admin API key."""
    output = resolve_output_format()
    try:
        govern = get_govern_client_from_ctx(ctx)
        groups = govern.list_groups()
        data = []
        for g in groups:
            data.append(
                {
                    "name": g.get("name", ""),
                    "description": g.get("description", ""),
                    "source_type": g.get("sourceType", ""),
                }
            )
        render(
            data,
            ["name", "description", "source_type"],
            output_format=output,
            title="Govern Groups",
        )
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def get(
    ctx: typer.Context,
    name: str = typer.Argument(help="Group name"),
) -> None:
    """Get a group's definition. Requires admin API key."""
    output = resolve_output_format()
    try:
        govern = get_govern_client_from_ctx(ctx)
        group = govern.get_group(name)
        defn = group.get_definition()
        render_raw(defn, output_format=output)
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def create(
    ctx: typer.Context,
    name: str = typer.Argument(help="Name for the new group"),
    description: Optional[str] = typer.Option(
        None, "--description", "-d", help="Group description"
    ),
    source_type: str = typer.Option(
        "LOCAL", "--source-type", help="Source type: LOCAL or LDAP"
    ),
) -> None:
    """Create a Govern group. Requires admin API key."""
    try:
        govern = get_govern_client_from_ctx(ctx)
        govern.create_group(name, description=description, source_type=source_type)
        success(f"Created group '{name}'")
        hint(f"dku govern group get {name}")
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def delete(
    ctx: typer.Context,
    name: str = typer.Argument(help="Group name"),
    confirm: bool = typer.Option(
        False, "--confirm", "--yes", "-y", help="Confirm deletion (required)"
    ),
) -> None:
    """Delete a Govern group. Requires --confirm flag and admin API key."""
    guard(
        ctx,
        tier=Tier.DELETE,
        action="govern.group.delete",
        subject=f"group '{name}'",
        yes=confirm,
        prompt=f"Delete Govern group '{name}'?",
    )
    try:
        govern = get_govern_client_from_ctx(ctx)
        govern.get_group(name).delete()
        success(f"Deleted group '{name}'")
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)
