"""dku user — list, create, get, delete, activity, add-secret."""

from __future__ import annotations

from typing import Optional

import typer

from dku_cli.errors import handle_api_error
from dku_cli.helpers import get_client_from_ctx
from dku_cli.output import info, render, render_raw, resolve_output_format, success

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
            data.append(
                {
                    "login": u.get("login", ""),
                    "display_name": u.get("displayName", ""),
                    "email": u.get("email", ""),
                    "groups": ", ".join(u.get("groups", [])),
                }
            )

        render(
            data,
            ["login", "display_name", "email", "groups"],
            output_format=output,
            title="Users",
            headers={
                "login": "LOGIN",
                "display_name": "NAME",
                "email": "EMAIL",
                "groups": "GROUPS",
            },
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
    groups: Optional[str] = typer.Option(
        None, "--groups", help="Comma-separated group names"
    ),
) -> None:
    """Create a DSS user."""
    try:
        client = get_client_from_ctx(ctx)
        group_list = [g.strip() for g in groups.split(",")] if groups else []
        client.create_user(login, password, display_name, email, groups=group_list)

        success(f"Created user '{login}'")
    except Exception as e:
        handle_api_error(e)


@app.command()
def get(
    ctx: typer.Context,
    login: str = typer.Argument(help="User login"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Get user details."""
    output = resolve_output_format(output, allowed=("json",), default="json")
    try:
        client = get_client_from_ctx(ctx)
        user = client.get_user(login)
        settings = user.get_settings()
        render_raw(settings.get_raw(), output_format=output)
    except Exception as e:
        handle_api_error(e)


@app.command()
def delete(
    ctx: typer.Context,
    login: str = typer.Argument(help="User login"),
) -> None:
    """Delete a DSS user."""
    try:
        client = get_client_from_ctx(ctx)
        user = client.get_user(login)
        user.delete()
        success(f"Deleted user '{login}'")
    except Exception as e:
        handle_api_error(e)


@app.command()
def activity(
    ctx: typer.Context,
    login: str = typer.Argument(help="User login"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show user activity (last login, last session, etc).

    Example:
      dku user activity admin
    """
    fmt = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        user = client.get_user(login)
        act = user.get_activity()
        raw = act.get_raw()

        if fmt == "json":
            render_raw(raw, output_format="json")
        else:

            def _fmt_ts(ts):
                if not ts or ts <= 0:
                    return "(never)"
                try:
                    from datetime import datetime, timezone

                    return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime(
                        "%Y-%m-%d %H:%M UTC"
                    )
                except Exception:
                    return str(ts)

            info(f"User: {login}")
            info(f"Last successful login: {_fmt_ts(raw.get('lastSuccessfulLogin'))}")
            info(f"Last failed login: {_fmt_ts(raw.get('lastFailedLogin'))}")
            info(f"Last session activity: {_fmt_ts(raw.get('lastSessionActivity'))}")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("add-secret")
def add_secret(
    ctx: typer.Context,
    login: str = typer.Argument(help="User login"),
    name: str = typer.Option(..., "--name", "-n", help="Secret name"),
    value: str = typer.Option(..., "--value", "-v", help="Secret value"),
) -> None:
    """Add or replace a user secret.

    User secrets are accessible in code via dataiku.get_custom_variables()
    and are scoped to the user.

    Example:
      dku user add-secret admin --name MY_TOKEN --value "abc123"
    """
    try:
        client = get_client_from_ctx(ctx)
        user = client.get_user(login)
        settings = user.get_settings()
        settings.add_secret(name, value)
        settings.save()
        success(f"Added secret '{name}' for user '{login}'")
    except Exception as e:
        handle_api_error(e)
