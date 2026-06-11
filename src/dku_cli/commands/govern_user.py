"""dku govern user — list, get, create, create-bulk, edit-bulk, delete-bulk, get-own, list-activity."""

from __future__ import annotations

from typing import Optional

import typer

from dku_cli.errors import handle_api_error
from dku_cli.helpers import get_govern_client_from_ctx, read_json_input
from dku_cli.output import hint, render, render_raw, resolve_output_format, success
from dku_cli.safety import Tier, guard

app = typer.Typer(help="Manage Govern users (admin).")


@app.command("list")
def list_users(
    ctx: typer.Context,
) -> None:
    """List all Govern users. Requires admin API key."""
    output = resolve_output_format()
    try:
        govern = get_govern_client_from_ctx(ctx)
        users = govern.list_users()
        data = []
        for u in users:
            data.append(
                {
                    "login": u.get("login", ""),
                    "display_name": u.get("displayName", ""),
                    "email": u.get("email", ""),
                    "groups": ", ".join(u.get("groups", [])),
                    "enabled": str(u.get("enabled", "")),
                }
            )
        render(
            data,
            ["login", "display_name", "email", "groups", "enabled"],
            output_format=output,
            title="Govern Users",
        )
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def get(
    ctx: typer.Context,
    login: str = typer.Argument(help="User login"),
) -> None:
    """Get a user's settings. Requires admin API key."""
    output = resolve_output_format()
    try:
        govern = get_govern_client_from_ctx(ctx)
        user = govern.get_user(login)
        settings = user.get_settings()
        render_raw(settings.get_raw(), output_format=output)
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def create(
    ctx: typer.Context,
    login: str = typer.Argument(help="Login for the new user"),
    password: str = typer.Option(..., "--password", help="Password"),
    display_name: str = typer.Option("", "--display-name", "-d", help="Display name"),
    source_type: str = typer.Option(
        "LOCAL", "--source-type", help="Source type: LOCAL or LDAP"
    ),
    groups: Optional[list[str]] = typer.Option(
        None, "--group", "-g", help="Group name (repeat for multiple)"
    ),
    profile: str = typer.Option(
        "DATA_SCIENTIST",
        "--profile",
        help="User profile (e.g. FULL_DESIGNER, DATA_DESIGNER, AI_CONSUMER)",
    ),
    email: Optional[str] = typer.Option(None, "--email", "-e", help="Email address"),
) -> None:
    """Create a Govern user. Requires admin API key."""
    try:
        govern = get_govern_client_from_ctx(ctx)
        govern.create_user(
            login,
            password,
            display_name=display_name,
            source_type=source_type,
            groups=groups or [],
            profile=profile,
            email=email,
        )
        success(f"Created user '{login}'")
        hint(f"dku govern user get {login}")
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("create-bulk")
def create_bulk(
    ctx: typer.Context,
    definition: str = typer.Option(
        ...,
        "--definition",
        help="JSON array of user dicts (string, @file.json, or - for stdin)",
    ),
) -> None:
    """Bulk create multiple users from JSON. Requires admin API key.

    Each user dict should contain: login, password, displayName, sourceType, groups, userProfile, email.
    """
    output = resolve_output_format()
    try:
        govern = get_govern_client_from_ctx(ctx)
        users = read_json_input(definition)
        results = govern.create_users(users)
        render(
            results,
            ["login", "status", "error"],
            output_format=output,
            title="Bulk User Creation Results",
        )
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("edit-bulk")
def edit_bulk(
    ctx: typer.Context,
    definition: str = typer.Option(
        ...,
        "--definition",
        help="JSON array of user change dicts (string, @file.json, or - for stdin)",
    ),
) -> None:
    """Bulk edit multiple users from JSON. Requires admin API key.

    Each dict must contain 'login' key. Other keys: displayName, email, groups, userProfile, enabled, sourceType.
    """
    output = resolve_output_format()
    try:
        govern = get_govern_client_from_ctx(ctx)
        changes = read_json_input(definition)
        results = govern.edit_users(changes)
        render(
            results,
            ["login", "status", "error"],
            output_format=output,
            title="Bulk User Edit Results",
        )
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("delete-bulk")
def delete_bulk(
    ctx: typer.Context,
    definition: str = typer.Option(
        ...,
        "--definition",
        help='JSON array of login strings (string, @file.json, or - for stdin). E.g. \'["user1","user2"]\'',
    ),
    confirm: bool = typer.Option(
        False, "--confirm", "--yes", "-y", help="Confirm deletion (required)"
    ),
    confirm_name: str | None = typer.Option(
        None,
        "--confirm-name",
        help="Required for bulk deletion; must be 'delete-users'.",
    ),
) -> None:
    """Bulk delete multiple users. Requires admin API key and cascade confirmation."""
    output = resolve_output_format()
    logins = read_json_input(definition)
    count = len(logins) if isinstance(logins, list) else 0
    guard(
        ctx,
        tier=Tier.CASCADE,
        action="govern.user.delete_bulk",
        subject=f"{count} Govern user(s)",
        yes=confirm,
        target_id="delete-users",
        confirm_name=confirm_name,
        prompt=f"Delete {count} Govern user(s)?",
    )
    try:
        govern = get_govern_client_from_ctx(ctx)
        results = govern.delete_users(logins)
        render(
            results,
            ["login", "status", "error"],
            output_format=output,
            title="Bulk User Deletion Results",
        )
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("get-own")
def get_own(
    ctx: typer.Context,
) -> None:
    """Get your own user settings."""
    output = resolve_output_format()
    try:
        govern = get_govern_client_from_ctx(ctx)
        own = govern.get_own_user()
        settings = own.get_settings()
        render_raw(settings.get_raw(), output_format=output)
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("list-activity")
def list_activity(
    ctx: typer.Context,
    enabled_only: bool = typer.Option(
        False, "--enabled-only", help="Only show enabled users"
    ),
) -> None:
    """List user activity (last login, etc.). Requires admin API key."""
    output = resolve_output_format()
    try:
        govern = get_govern_client_from_ctx(ctx)
        activities = govern.list_users_activity(enabled_users_only=enabled_only)
        data = []
        for act in activities:
            raw = act.get_raw()
            data.append(
                {
                    "login": raw.get("login", act.login),
                    "last_successful_login": str(raw.get("lastSuccessfulLogin", "")),
                    "last_failed_login": str(raw.get("lastFailedLogin", "")),
                    "last_session_activity": str(raw.get("lastSessionActivity", "")),
                }
            )
        render(
            data,
            [
                "login",
                "last_successful_login",
                "last_failed_login",
                "last_session_activity",
            ],
            output_format=output,
            title="User Activity",
        )
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)
