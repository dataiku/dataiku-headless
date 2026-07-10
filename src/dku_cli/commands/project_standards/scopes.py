"""Project Standards scope discovery and creation commands."""

from __future__ import annotations

import typer

from dku_cli.enums import ScopeSelectionMethod
from dku_cli.errors import handle_errors
from dku_cli.helpers import get_client_from_ctx
from dku_cli.output import hint, render_raw, resolve_output_format, success

from ._common import (
    app,
    guard_admin,
    policy_write_lock,
    render_resource,
    render_scopes,
    validate_check_ids,
)


@app.command("list-scopes")
@handle_errors
def list_scopes(ctx: typer.Context) -> None:
    """List scopes in evaluation priority order."""
    output = resolve_output_format()
    standards = get_client_from_ctx(ctx).get_project_standards()
    render_scopes(standards.list_scopes(), output)


@app.command("get-scope")
@handle_errors
def get_scope(
    ctx: typer.Context,
    scope_name: str = typer.Argument(help="Scope name"),
) -> None:
    """Get one scope's full definition."""
    output = resolve_output_format()
    standards = get_client_from_ctx(ctx).get_project_standards()
    render_resource(standards.get_scope(scope_name), output)


@app.command("get-default-scope")
@handle_errors
def get_default_scope(ctx: typer.Context) -> None:
    """Get the fallback scope used when no custom scope matches."""
    output = resolve_output_format()
    standards = get_client_from_ctx(ctx).get_project_standards()
    render_resource(standards.get_default_scope(), output)


@app.command("create-scope")
@handle_errors
def create_scope(
    ctx: typer.Context,
    name: str = typer.Option(..., "--name", help="Unique scope name"),
    description: str = typer.Option("", "--description", help="Description"),
    check: list[str] = typer.Option(
        [], "--check", help="Check id to include (repeatable)"
    ),
    selection_method: ScopeSelectionMethod = typer.Option(
        ScopeSelectionMethod.BY_PROJECT,
        "--selection-method",
        case_sensitive=False,
        help="How this scope selects projects",
    ),
    item: list[str] = typer.Option(
        [], "--item", help="Project key, folder id, or tag (repeatable)"
    ),
    if_not_exists: bool = typer.Option(
        False, "--if-not-exists", help="Return the existing scope instead of failing"
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Authorize admin write"),
    confirm_name: str | None = typer.Option(
        None, "--confirm-name", help="Must equal the scope name"
    ),
    i_know: bool = typer.Option(
        False, "--i-know-what-im-doing", help="Tier-4 admin acknowledgement"
    ),
) -> None:
    """Create a project-, folder-, or tag-selected scope (admin)."""
    output = resolve_output_format()
    client = get_client_from_ctx(ctx)
    standards = client.get_project_standards()
    if if_not_exists:
        existing = next(
            (scope for scope in standards.list_scopes() if scope.get("name") == name),
            None,
        )
        if existing is not None:
            render_raw(existing, output_format=output)
            success(f"Project Standards scope '{name}' already exists; skipped")
            return
    validate_check_ids(standards, check)
    guard_admin(
        ctx,
        action="project-standards.scope.create",
        subject=f"Project Standards scope '{name}'",
        target_id=name,
        yes=yes,
        confirm_name=confirm_name,
        i_know=i_know,
    )
    with policy_write_lock(client):
        if if_not_exists:
            existing = next(
                (
                    scope
                    for scope in standards.list_scopes()
                    if scope.get("name") == name
                ),
                None,
            )
            if existing is not None:
                render_raw(existing, output_format=output)
                success(f"Project Standards scope '{name}' already exists; skipped")
                return
        validate_check_ids(standards, check)
        scope = standards.create_scope(
            name,
            description=description,
            checks=check,
            selection_method=selection_method.value,
            items=item,
        )
    render_resource(scope, output)
    success(f"Created Project Standards scope '{name}'")
    hint(f"dku project-standards get-scope {name}")
