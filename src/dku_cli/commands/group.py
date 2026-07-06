"""dku group — list, get, create, delete."""

from __future__ import annotations

import typer

from dku_cli.commands._source_type import SourceType
from dku_cli.errors import handle_api_error
from dku_cli.helpers import ALL_NODE_TYPES, get_client_from_ctx
from dku_cli.output import hint, render, render_raw, resolve_output_format, success

app = typer.Typer(help="Manage DSS groups.")


@app.command("list")
def list_groups(
    ctx: typer.Context,
) -> None:
    """List DSS groups."""
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx, allowed_node_types=ALL_NODE_TYPES)
        groups = client.list_groups()

        data = []
        for g in groups:
            data.append(
                {
                    "name": g.get("name", ""),
                    "description": g.get("description", ""),
                    "source": g.get("sourceType", ""),
                }
            )

        render(
            data,
            ["name", "description", "source"],
            output_format=output,
            title="Groups",
        )
    except Exception as e:
        handle_api_error(e)


@app.command()
def get(
    ctx: typer.Context,
    name: str = typer.Argument(help="Group name"),
) -> None:
    """Show group details."""
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx, allowed_node_types=ALL_NODE_TYPES)
        group = client.get_group(name)
        defn = group.get_definition()
        if output == "json":
            render_raw(defn, output_format="json")
        else:
            data = [
                {"field": "Name", "value": defn.get("name", name)},
                {"field": "Description", "value": defn.get("description", "")},
                {"field": "Source", "value": defn.get("sourceType", "")},
                {"field": "Admin", "value": str(defn.get("admin", False))},
            ]
            render(
                data,
                ["field", "value"],
                output_format=output,
                title=f"Group: {name}",
            )
    except Exception as e:
        handle_api_error(e)


@app.command()
def create(
    ctx: typer.Context,
    name: str = typer.Argument(help="Group name"),
    description: str | None = typer.Option(
        None, "--description", "-d", help="Group description"
    ),
    source_type: SourceType = typer.Option(
        SourceType.LOCAL,
        "--source-type",
        case_sensitive=False,
        help="Source type",
    ),
) -> None:
    """Create a DSS group."""
    try:
        client = get_client_from_ctx(ctx, allowed_node_types=ALL_NODE_TYPES)
        client.create_group(
            name, description=description or "", source_type=str(source_type)
        )
        success(f"Created group '{name}'")
        hint(f"dku group get {name}")
    except Exception as e:
        handle_api_error(e)


@app.command()
def delete(
    ctx: typer.Context,
    name: str = typer.Argument(help="Group name"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
) -> None:
    """Delete a DSS group."""
    from dku_cli.safety import Tier, guard

    guard(
        ctx,
        tier=Tier.DELETE,
        action="group.delete",
        subject=f"group '{name}'",
        yes=yes,
        prompt=f"Delete DSS group '{name}'? Users in the group lose its associated permissions.",
    )
    try:
        client = get_client_from_ctx(ctx, allowed_node_types=ALL_NODE_TYPES)
        group = client.get_group(name)
        group.delete()
        success(f"Deleted group '{name}'")
    except Exception as e:
        handle_api_error(e)
