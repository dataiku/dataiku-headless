"""dku govern-custom-page — list, get."""

from __future__ import annotations

import typer

from dku_cli.errors import handle_api_error
from dku_cli.helpers import get_govern_client_from_ctx
from dku_cli.output import render, render_raw, resolve_output_format

app = typer.Typer(help="Manage Govern custom pages.")


@app.command("list")
def list_custom_pages(
    ctx: typer.Context,
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List all Govern custom pages."""
    output = resolve_output_format(output)
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
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Get a custom page definition."""
    output = resolve_output_format(output)
    try:
        govern = get_govern_client_from_ctx(ctx)
        page = govern.get_custom_page(page_id)
        defn = page.get_definition()
        render_raw(defn.get_raw(), output_format=output)
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)
