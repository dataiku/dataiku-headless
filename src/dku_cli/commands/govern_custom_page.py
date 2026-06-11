"""dku govern custom-page — list, get, create, set-definition."""

from __future__ import annotations

import typer

from dku_cli.errors import handle_api_error
from dku_cli.helpers import get_govern_client_from_ctx, read_json_input
from dku_cli.output import hint, render, render_raw, resolve_output_format, success
from dku_cli.safety import Tier, guard

app = typer.Typer(help="Manage Govern custom pages.")


@app.command("list")
def list_custom_pages(
    ctx: typer.Context,
) -> None:
    """List all Govern custom pages."""
    output = resolve_output_format()
    try:
        govern = get_govern_client_from_ctx(ctx)
        pages = govern.list_custom_pages()
        data = []
        for item in pages:
            raw = item.get_raw()
            data.append(
                {
                    "id": raw.get("id", ""),
                    "name": raw.get("name", ""),
                    "type": raw.get("type", ""),
                    "visible": str(raw.get("visible", "")),
                }
            )
        render(
            data,
            ["id", "name", "type", "visible"],
            output_format=output,
            title="Govern Custom Pages",
        )
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def get(
    ctx: typer.Context,
    page_id: str = typer.Argument(help="Custom page ID"),
) -> None:
    """Get a custom page definition."""
    output = resolve_output_format()
    try:
        govern = get_govern_client_from_ctx(ctx)
        page = govern.get_custom_page(page_id)
        defn = page.get_definition()
        render_raw(defn.get_raw(), output_format=output)
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def create(
    ctx: typer.Context,
    identifier: str = typer.Argument(
        help="New custom page identifier (letters, digits, hyphen, underscore)"
    ),
    definition: str = typer.Option(
        ...,
        "--definition",
        help="Custom page definition JSON (string, @file.json, or - for stdin)",
    ),
) -> None:
    """Create a new custom page (admin/architect). Provide definition as JSON."""
    try:
        govern = get_govern_client_from_ctx(ctx)
        handler = govern.get_custom_pages_handler()
        page_data = read_json_input(definition)
        page = handler.create_custom_page(identifier, page_data)
        success(f"Created custom page '{page.custom_page_id}'")
        hint(f"dku govern custom-page get {page.custom_page_id}")
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("set-definition")
def set_definition(
    ctx: typer.Context,
    page_id: str = typer.Argument(help="Custom page ID"),
    definition: str = typer.Option(
        ...,
        "--definition",
        help="New custom page definition JSON (string, @file.json, or - for stdin)",
    ),
) -> None:
    """Update a custom page definition (admin/architect)."""
    try:
        govern = get_govern_client_from_ctx(ctx)
        handler = govern.get_custom_pages_handler()
        page = handler.get_custom_page(page_id)
        defn = page.get_definition()
        new_def = read_json_input(definition)
        defn.definition = new_def
        defn.save()
        success(f"Updated definition for custom page '{page_id}'")
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def delete(
    ctx: typer.Context,
    page_id: str = typer.Argument(help="Custom page ID"),
    confirm: bool = typer.Option(
        False, "--confirm", "--yes", "-y", help="Confirm deletion (required)"
    ),
) -> None:
    """Delete a custom page (admin/architect). Requires --confirm flag."""
    guard(
        ctx,
        tier=Tier.DELETE,
        action="govern.custom_page.delete",
        subject=f"custom page '{page_id}'",
        yes=confirm,
        prompt=f"Delete Govern custom page '{page_id}'?",
    )
    try:
        govern = get_govern_client_from_ctx(ctx)
        handler = govern.get_custom_pages_handler()
        handler.get_custom_page(page_id).delete()
        success(f"Deleted custom page '{page_id}'")
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)
