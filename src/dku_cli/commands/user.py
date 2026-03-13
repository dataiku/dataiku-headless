"""dku user — list, create."""

from __future__ import annotations

from typing import Optional

import typer

from dku_cli.errors import handle_api_error
from dku_cli.helpers import get_client_from_ctx
from dku_cli.output import render, resolve_output_format, success

app = typer.Typer(help="Manage DSS users.")


@app.command("list")
def list_users(
    ctx: typer.Context,
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List DSS users."""
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        users = client.list_users()

        data = []
        for u in users:
            data.append({
                "login": u.get("login", ""),
                "display_name": u.get("displayName", ""),
                "email": u.get("email", ""),
                "groups": ", ".join(u.get("groups", [])),
            })

        render(
            data,
            ["login", "display_name", "email", "groups"],
            output_format=output,
            title="Users",
            headers={"login": "LOGIN", "display_name": "NAME", "email": "EMAIL", "groups": "GROUPS"},
        )
    except Exception as e:
        handle_api_error(e)


@app.command()
def create(
    ctx: typer.Context,
    login: str = typer.Argument(help="User login"),
    display_name: str = typer.Option(..., "--display-name", help="Display name"),
    email: str = typer.Option(..., "--email", help="Email address"),
    password: Optional[str] = typer.Option(None, "--password", help="User password"),
    groups: Optional[str] = typer.Option(None, "--groups", help="Comma-separated group names"),
) -> None:
    """Create a DSS user."""
    try:
        client = get_client_from_ctx(ctx)
        group_list = [g.strip() for g in groups.split(",")] if groups else []
        result = client.create_user(
            login, password, display_name, email, groups=group_list
        )

        success(f"Created user '{login}'")
    except Exception as e:
        handle_api_error(e)
