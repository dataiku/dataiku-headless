"""dku user — list, create, get, delete, activity, add-secret."""

from __future__ import annotations

from typing import Optional

import typer

from dku_cli.errors import exit_with_error, handle_api_error
from dku_cli.helpers import ALL_NODE_TYPES, get_client_from_ctx, read_json_input
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
        client = get_client_from_ctx(ctx, allowed_node_types=ALL_NODE_TYPES)
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
        client = get_client_from_ctx(ctx, allowed_node_types=ALL_NODE_TYPES)
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
        client = get_client_from_ctx(ctx, allowed_node_types=ALL_NODE_TYPES)
        user = client.get_user(login)
        settings = user.get_settings()
        render_raw(settings.get_raw(), output_format=output)
    except Exception as e:
        handle_api_error(e)


@app.command()
def delete(
    ctx: typer.Context,
    login: str = typer.Argument(help="User login"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip safety guard"),
) -> None:
    """Delete a DSS user."""
    from dku_cli.safety import Tier, guard

    guard(
        ctx,
        tier=Tier.DELETE,
        action="user.delete",
        subject=f"user '{login}'",
        yes=yes,
        prompt=f"Delete DSS user '{login}'?",
    )
    try:
        client = get_client_from_ctx(ctx, allowed_node_types=ALL_NODE_TYPES)
        user = client.get_user(login)
        user.delete()
        success(f"Deleted user '{login}'")
    except typer.Exit:
        raise
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
        client = get_client_from_ctx(ctx, allowed_node_types=ALL_NODE_TYPES)
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
        client = get_client_from_ctx(ctx, allowed_node_types=ALL_NODE_TYPES)
        user = client.get_user(login)
        settings = user.get_settings()
        settings.add_secret(name, value)
        settings.save()
        success(f"Added secret '{name}' for user '{login}'")
    except Exception as e:
        handle_api_error(e)


# =============================================================================
# Bulk user ops — create_users / edit_users (admin only)
# =============================================================================


def _load_users_from_csv(path: str) -> list[dict]:
    """Parse a CSV file into the user dicts expected by DSSClient.create_users().

    Required header: login
    Optional headers: password, displayName, email, groups, userProfile, sourceType
    'groups' is a semicolon-separated list within the cell.
    """
    import csv
    from pathlib import Path

    p = Path(path)
    if not p.exists():
        exit_with_error(
            f"CSV file not found: {path}",
            code="user_bulk_csv_not_found",
            details=["Check the file path and try again."],
        )
    users: list[dict] = []
    with p.open(newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None or "login" not in reader.fieldnames:
            exit_with_error(
                "CSV must have a 'login' column.",
                code="user_bulk_csv_missing_login",
                details=[
                    f"Found columns: {reader.fieldnames}",
                    "Required: login",
                ],
            )
        for row in reader:
            user = {k: v for k, v in row.items() if v != "" and v is not None}
            if "groups" in user and isinstance(user["groups"], str):
                user["groups"] = [
                    g.strip() for g in user["groups"].split(";") if g.strip()
                ]
            users.append(user)
    return users


@app.command("bulk-create")
def bulk_create(
    ctx: typer.Context,
    from_json: str | None = typer.Option(
        None,
        "--from",
        "-f",
        help="JSON list of user dicts (inline, @file, -)",
    ),
    from_csv: str | None = typer.Option(
        None,
        "--from-csv",
        help="CSV file path. Headers: login[,password,displayName,email,groups,userProfile,sourceType]. groups separator: ';'",
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Confirm creation of all users in the input"
    ),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Bulk-create users from JSON or CSV. Returns per-user status list.

    Example:
      dku user bulk-create --from-csv @new-team.csv --yes
      dku user bulk-create --from '[{"login":"alice","password":"x","groups":["readers"]}]' --yes

    CSV columns (semicolon separates group lists):
      login,password,displayName,email,groups,userProfile,sourceType
      alice,tempPass,Alice A,alice@example.com,data_team;readers,DATA_SCIENTIST,LOCAL
    """
    if (from_json is None) == (from_csv is None):
        exit_with_error(
            "Pass exactly one of --from or --from-csv.",
            code="user_bulk_input_missing",
        )

    if from_csv:
        users = _load_users_from_csv(from_csv)
    else:
        parsed = read_json_input(from_json)
        if not isinstance(parsed, list):
            exit_with_error(
                "--from must be a JSON array of user objects.",
                code="user_bulk_bad_payload",
            )
        users = parsed

    if not users:
        info("No users to create (empty input).")
        raise typer.Exit(code=0)

    if not yes:
        info(f"Dry run — would create {len(users)} user(s). Pass --yes to execute.")
        for u in users[:10]:
            info(
                f"  • {u.get('login', '?')} "
                f"(profile={u.get('userProfile', 'DATA_SCIENTIST')}, "
                f"groups={u.get('groups', [])})"
            )
        if len(users) > 10:
            info(f"  • … and {len(users) - 10} more")
        raise typer.Exit(code=0)

    try:
        client = get_client_from_ctx(ctx)
        results = client.create_users(users)
        fmt = resolve_output_format(output)
        if fmt == "json":
            render_raw(results, output_format="json")
        else:
            data = [
                {
                    "login": r.get("login", ""),
                    "status": r.get("status", ""),
                    "error": (r.get("error") or "")[:80],
                }
                for r in results
            ]
            render(
                data,
                ["login", "status", "error"],
                output_format=fmt,
                title="Bulk User Create Results",
            )
        failures = [r for r in results if r.get("status") == "FAILURE"]
        if failures:
            info(f"{len(failures)} user(s) failed — see 'error' column.")
            raise typer.Exit(code=1)
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("bulk-edit")
def bulk_edit(
    ctx: typer.Context,
    from_json: str = typer.Option(
        ...,
        "--from",
        "-f",
        help="JSON list of user-change dicts (each must have 'login')",
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Confirm mass edit"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Bulk-edit existing users. Each change dict MUST include 'login'.

    Example:
      # Move 3 users into a new group
      dku user bulk-edit --from '[
        {"login":"alice","groups":["data_team","admin"]},
        {"login":"bob","groups":["data_team"]},
        {"login":"clara","enabled":false}
      ]' --yes
    """
    changes = read_json_input(from_json)
    if not isinstance(changes, list):
        exit_with_error(
            "--from must be a JSON array of change objects.",
            code="user_bulk_bad_payload",
        )
    missing_login = [c for c in changes if not isinstance(c, dict) or "login" not in c]
    if missing_login:
        exit_with_error(
            f"{len(missing_login)} change entries missing 'login' — required for bulk-edit.",
            code="user_bulk_missing_login",
        )

    if not yes:
        info(f"Dry run — would edit {len(changes)} user(s). Pass --yes to execute.")
        for c in changes[:10]:
            fields = [k for k in c if k != "login"]
            info(f"  • {c['login']} → {fields}")
        raise typer.Exit(code=0)

    try:
        client = get_client_from_ctx(ctx)
        results = client.edit_users(changes)
        fmt = resolve_output_format(output)
        if fmt == "json":
            render_raw(results, output_format=fmt)
        else:
            data = [
                {
                    "login": r.get("login", ""),
                    "status": r.get("status", ""),
                    "error": (r.get("error") or "")[:80],
                }
                for r in results
            ]
            render(
                data,
                ["login", "status", "error"],
                output_format=fmt,
                title="Bulk User Edit Results",
            )
        failures = [r for r in results if r.get("status") == "FAILURE"]
        if failures:
            info(f"{len(failures)} user(s) failed — see 'error' column.")
            raise typer.Exit(code=1)
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)
