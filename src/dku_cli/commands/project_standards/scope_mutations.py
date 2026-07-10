"""Project Standards scope update, ordering, and deletion commands."""

from __future__ import annotations

import typer

from dku_cli.enums import ScopeSelectionMethod
from dku_cli.errors import exit_with_error, handle_errors
from dku_cli.helpers import get_client_from_ctx, mutate_settings
from dku_cli.output import hint, render_raw, resolve_output_format, success

from ._common import (
    app,
    guard_admin,
    policy_write_lock,
    render_resource,
    validate_check_ids,
)


@app.command("update-scope")
@handle_errors
def update_scope(
    ctx: typer.Context,
    scope_name: str = typer.Argument(help="Scope name"),
    description: str | None = typer.Option(
        None, "--description", help="New description"
    ),
    check: list[str] | None = typer.Option(
        None, "--check", help="Replacement check id (repeatable)"
    ),
    clear_checks: bool = typer.Option(
        False, "--clear-checks", help="Replace the check list with an empty list"
    ),
    selection_method: ScopeSelectionMethod | None = typer.Option(
        None,
        "--selection-method",
        case_sensitive=False,
        help="New project selection method",
    ),
    item: list[str] | None = typer.Option(
        None, "--item", help="Replacement project key, folder id, or tag"
    ),
    clear_items: bool = typer.Option(
        False, "--clear-items", help="Replace selected items with an empty list"
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Authorize admin write"),
    confirm_name: str | None = typer.Option(
        None, "--confirm-name", help="Must equal SCOPE_NAME"
    ),
    i_know: bool = typer.Option(
        False, "--i-know-what-im-doing", help="Tier-4 admin acknowledgement"
    ),
) -> None:
    """Replace a scope's checks, description, or selector (admin)."""
    selection_requested = _validate_update(
        scope_name,
        description,
        check,
        clear_checks,
        selection_method,
        item,
        clear_items,
    )
    client = get_client_from_ctx(ctx)
    standards = client.get_project_standards()
    current = standards.get_scope(scope_name)
    if current.is_default and (description is not None or selection_requested):
        exit_with_error(
            "The Default scope's description and ALL selection are immutable.",
            details=[
                "Update only its checks with --check or --clear-checks.",
                "Inspect it: dku project-standards get-default-scope",
            ],
        )
    if check is not None:
        validate_check_ids(standards, check)
    guard_admin(
        ctx,
        action="project-standards.scope.update",
        subject=f"Project Standards scope '{scope_name}'",
        target_id=scope_name,
        yes=yes,
        confirm_name=confirm_name,
        i_know=i_know,
    )

    def apply(scope):
        if description is not None:
            scope.description = description
        if check is not None:
            scope.checks = check
        elif clear_checks:
            scope.checks = []
        if selection_requested:
            method = (
                selection_method.value if selection_method else scope.selection_method
            )
            _set_selection(scope, method, list(item or []))
        return scope

    with policy_write_lock(client):
        if check is not None:
            validate_check_ids(standards, check)
        mutate_settings(
            client,
            "instance",
            "project-standards-scope",
            scope_name,
            fetch=lambda: standards.get_scope(scope_name),
            mutate=apply,
        )
        persisted = standards.get_scope(scope_name)
    render_resource(persisted, resolve_output_format())
    success(f"Updated Project Standards scope '{scope_name}'")


@app.command("reorder-scope")
@handle_errors
def reorder_scope(
    ctx: typer.Context,
    scope_name: str = typer.Argument(help="Scope name"),
    index: int = typer.Argument(..., min=0, help="New zero-based priority index"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Authorize admin write"),
    confirm_name: str | None = typer.Option(
        None, "--confirm-name", help="Must equal SCOPE_NAME"
    ),
    i_know: bool = typer.Option(
        False, "--i-know-what-im-doing", help="Tier-4 admin acknowledgement"
    ),
) -> None:
    """Move a custom scope in priority order; Default remains last (admin)."""
    output = resolve_output_format()
    client = get_client_from_ctx(ctx)
    standards = client.get_project_standards()
    scope = standards.get_scope(scope_name)
    if scope.is_default:
        exit_with_error(
            "The Default scope cannot be reordered.",
            details=["Custom scopes always remain above Default."],
        )
    guard_admin(
        ctx,
        action="project-standards.scope.reorder",
        subject=f"Project Standards scope '{scope_name}'",
        target_id=scope_name,
        yes=yes,
        confirm_name=confirm_name,
        i_know=i_know,
    )
    with policy_write_lock(client):
        standards.get_scope(scope_name).reorder(index)
        order = [item.get("name", "") for item in standards.list_scopes()]
    render_raw(
        {
            "name": scope_name,
            "requested_index": index,
            "actual_index": order.index(scope_name),
            "order": order,
        },
        output_format=output,
    )
    success(f"Reordered Project Standards scope '{scope_name}'")


@app.command("delete-scope")
@handle_errors
def delete_scope(
    ctx: typer.Context,
    scope_name: str = typer.Argument(help="Scope name"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Authorize admin write"),
    confirm_name: str | None = typer.Option(
        None, "--confirm-name", help="Must equal SCOPE_NAME"
    ),
    i_know: bool = typer.Option(
        False, "--i-know-what-im-doing", help="Tier-4 admin acknowledgement"
    ),
) -> None:
    """Delete a custom scope (admin)."""
    client = get_client_from_ctx(ctx)
    standards = client.get_project_standards()
    scope = standards.get_scope(scope_name)
    if scope.is_default:
        exit_with_error(
            "The Default scope cannot be deleted.",
            details=[
                "Update its checks with: dku project-standards update-scope Default"
            ],
        )
    guard_admin(
        ctx,
        action="project-standards.scope.delete",
        subject=f"Project Standards scope '{scope_name}'",
        target_id=scope_name,
        yes=yes,
        confirm_name=confirm_name,
        i_know=i_know,
    )
    with policy_write_lock(client):
        standards.get_scope(scope_name).delete()
        if scope_name in {item.get("name") for item in standards.list_scopes()}:
            exit_with_error(
                f"DSS reported success but scope '{scope_name}' still exists.",
                details=["Verify with: dku project-standards list-scopes"],
            )
    success(f"Deleted Project Standards scope '{scope_name}'")
    hint("dku project-standards list-scopes")


def _validate_update(
    scope_name: str,
    description: str | None,
    checks: list[str] | None,
    clear_checks: bool,
    selection_method: ScopeSelectionMethod | None,
    items: list[str] | None,
    clear_items: bool,
) -> bool:
    if checks is not None and clear_checks:
        exit_with_error("Use either --check or --clear-checks, not both.")
    if items is not None and clear_items:
        exit_with_error("Use either --item or --clear-items, not both.")
    if selection_method is not None and items is None and not clear_items:
        exit_with_error(
            "Changing --selection-method also requires --item or --clear-items.",
            details=["This prevents silently reinterpreting the old selector values."],
        )
    values = (description, checks, selection_method, items)
    if all(value is None for value in values) and not clear_checks and not clear_items:
        exit_with_error(
            "No scope updates requested.",
            details=[f"Inspect first: dku project-standards get-scope {scope_name}"],
        )
    return selection_method is not None or items is not None or clear_items


def _set_selection(scope, method: str, items: list[str]) -> None:
    scope.selection_method = method
    scope.selected_projects = items if method == "BY_PROJECT" else []
    scope.selected_folders = items if method == "BY_FOLDER" else []
    scope.selected_tags = items if method == "BY_TAG" else []
