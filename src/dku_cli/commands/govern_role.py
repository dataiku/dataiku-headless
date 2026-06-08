"""dku govern role — list, get, create, set-definition, delete."""

from __future__ import annotations

import typer

from dku_cli.errors import handle_api_error
from dku_cli.helpers import get_govern_client_from_ctx, read_json_input
from dku_cli.output import render, render_raw, resolve_output_format, success
from dku_cli.safety import Tier, guard

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


@app.command()
def create(
    ctx: typer.Context,
    identifier: str = typer.Argument(
        help="New role identifier (letters, digits, hyphen, underscore)"
    ),
    definition: str = typer.Option(
        ...,
        "--definition",
        help="Role definition JSON (string, @file.json, or - for stdin)",
    ),
) -> None:
    """Create a new role (admin/architect). Provide definition as JSON."""
    try:
        govern = get_govern_client_from_ctx(ctx)
        handler = govern.get_roles_permissions_handler()
        role_data = read_json_input(definition)
        role = handler.create_role(identifier, role_data)
        success(f"Created role '{role.role_id}'")
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("set-definition")
def set_definition(
    ctx: typer.Context,
    role_id: str = typer.Argument(help="Role ID (e.g. ro.project_manager)"),
    definition: str = typer.Option(
        ...,
        "--definition",
        help="New role definition JSON (string, @file.json, or - for stdin)",
    ),
) -> None:
    """Update a role definition (admin/architect)."""
    try:
        govern = get_govern_client_from_ctx(ctx)
        handler = govern.get_roles_permissions_handler()
        role = handler.get_role(role_id)
        defn = role.get_definition()
        new_def = read_json_input(definition)
        defn.definition = new_def
        defn.save()
        success(f"Updated definition for role '{role_id}'")
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def delete(
    ctx: typer.Context,
    role_id: str = typer.Argument(help="Role ID (e.g. ro.custom_role)"),
    confirm: bool = typer.Option(
        False, "--confirm", "--yes", "-y", help="Confirm deletion (required)"
    ),
) -> None:
    """Delete a Govern role. Requires --confirm flag and admin/architect rights."""
    guard(
        ctx,
        tier=Tier.DELETE,
        action="govern.role.delete",
        subject=f"role '{role_id}'",
        yes=confirm,
        prompt=f"Delete Govern role '{role_id}'?",
    )
    try:
        govern = get_govern_client_from_ctx(ctx)
        handler = govern.get_roles_permissions_handler()
        handler.get_role(role_id).delete()
        success(f"Deleted role '{role_id}'")
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)
