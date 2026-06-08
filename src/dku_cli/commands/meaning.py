"""dku meaning — list, get, create, update for data dictionary meanings."""

from __future__ import annotations

import typer

from dku_cli.commands._options import OutputOption
from dku_cli.errors import handle_errors
from dku_cli.helpers import get_client_from_ctx, read_json_input
from dku_cli.output import info, render, render_raw, resolve_output_format, success

app = typer.Typer(help="Manage DSS data dictionary meanings.")


@app.command("list")
@handle_errors
def list_meanings(
    ctx: typer.Context,
    output: OutputOption = None,
) -> None:
    """List all user-defined meanings."""
    fmt = resolve_output_format(output)
    client = get_client_from_ctx(ctx)
    meanings = client.list_meanings()

    if fmt == "json":
        render_raw(meanings, output_format="json")
    else:
        if not meanings:
            info("No user-defined meanings found.")
            return

        data = []
        for m in meanings:
            data.append(
                {
                    "id": m.get("id", ""),
                    "label": m.get("label", ""),
                    "type": m.get("type", ""),
                    "description": (m.get("description") or "")[:60],
                }
            )
        render(
            data,
            ["id", "label", "type", "description"],
            output_format=fmt,
            title="Meanings",
            headers={
                "id": "ID",
                "label": "LABEL",
                "type": "TYPE",
                "description": "DESCRIPTION",
            },
        )


@app.command()
@handle_errors
def get(
    ctx: typer.Context,
    meaning_id: str = typer.Argument(help="Meaning ID"),
    output: OutputOption = None,
) -> None:
    """Get a meaning's definition."""
    output = resolve_output_format(output, allowed=("json",), default="json")
    client = get_client_from_ctx(ctx)
    meaning = client.get_meaning(meaning_id)
    definition = meaning.get_definition()
    render_raw(definition, output_format=output)


@app.command()
@handle_errors
def create(
    ctx: typer.Context,
    meaning_id: str = typer.Argument(help="Meaning ID"),
    label: str = typer.Option(..., "--label", "-l", help="Display label"),
    meaning_type: str = typer.Option(
        "DECLARATIVE",
        "--type",
        "-t",
        help="Type: DECLARATIVE, VALUES_LIST, VALUES_MAPPING, PATTERN",
    ),
    description: str | None = typer.Option(
        None, "--description", "-d", help="Description"
    ),
) -> None:
    """Create a new meaning (admin only).

    Supported types: DECLARATIVE, VALUES_LIST, VALUES_MAPPING, PATTERN.

    Example:
      dku meaning create country_code --label "Country Code" --type VALUES_LIST
      dku meaning create email --label "Email Address" --type PATTERN
    """
    client = get_client_from_ctx(ctx)
    client.create_meaning(
        meaning_id,
        label,
        meaning_type,
        description=description,
    )
    success(f"Created meaning '{meaning_id}' (type: {meaning_type})")


@app.command()
@handle_errors
def update(
    ctx: typer.Context,
    meaning_id: str = typer.Argument(help="Meaning ID"),
    definition: str = typer.Option(
        ...,
        "--definition",
        "-d",
        help="Definition JSON (string, @file.json, or '-' for stdin)",
    ),
) -> None:
    """Update a meaning's definition (admin only).

    Use 'dku meaning get ID' to retrieve the current definition,
    modify it, then pass it back.

    Example:
      dku meaning get my_meaning > def.json
      # edit def.json
      dku meaning update my_meaning -d @def.json
    """
    client = get_client_from_ctx(ctx)
    meaning = client.get_meaning(meaning_id)
    new_def = read_json_input(definition)
    meaning.set_definition(new_def)
    success(f"Updated meaning '{meaning_id}'")
