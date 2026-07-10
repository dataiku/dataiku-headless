"""Project Standards check-spec and check-library commands."""

from __future__ import annotations

import typer

from dku_cli.errors import exit_with_error, handle_errors
from dku_cli.helpers import get_client_from_ctx, mutate_settings, read_json_input
from dku_cli.output import hint, resolve_output_format, success

from ._common import (
    app,
    guard_admin,
    policy_write_lock,
    render_check_specs,
    render_checks,
    render_resource,
)


@app.command("list-check-specs")
@handle_errors
def list_check_specs(ctx: typer.Context) -> None:
    """List available check specs and their parameter schemas."""
    output = resolve_output_format()
    standards = get_client_from_ctx(ctx).get_project_standards()
    render_check_specs(standards.list_check_specs(), output)
    hint("dku project-standards create-checks --spec <ELEMENT_TYPE>")


@app.command("list-checks")
@handle_errors
def list_checks(ctx: typer.Context) -> None:
    """List configured checks, parameters, and tags."""
    output = resolve_output_format()
    standards = get_client_from_ctx(ctx).get_project_standards()
    checks = standards.list_checks(as_type="objects")
    render_checks(checks, output, title="Project Standards checks")
    if not checks:
        hint("dku project-standards list-check-specs")


@app.command("get-check")
@handle_errors
def get_check(
    ctx: typer.Context,
    check_id: str = typer.Argument(help="Check id (see list-checks)"),
) -> None:
    """Get one check's full definition."""
    output = resolve_output_format()
    standards = get_client_from_ctx(ctx).get_project_standards()
    render_resource(standards.get_check(check_id), output)


@app.command("create-checks")
@handle_errors
def create_checks(
    ctx: typer.Context,
    spec: list[str] = typer.Option(
        ...,
        "--spec",
        help="Check-spec element type to import (repeatable; see list-check-specs)",
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Authorize admin write"),
    confirm_name: str | None = typer.Option(
        None, "--confirm-name", help="Must equal 'checks-library'"
    ),
    i_know: bool = typer.Option(
        False, "--i-know-what-im-doing", help="Tier-4 admin acknowledgement"
    ),
) -> None:
    """Import checks from plugin specs into the instance library (admin)."""
    guard_admin(
        ctx,
        action="project-standards.check.create",
        subject="the instance Project Standards checks library",
        target_id="checks-library",
        yes=yes,
        confirm_name=confirm_name,
        i_know=i_know,
    )
    output = resolve_output_format()
    standards = get_client_from_ctx(ctx).get_project_standards()
    checks = standards.create_checks(spec, as_type="objects")
    render_checks(checks, output, title="Created Project Standards checks")
    success(f"Created {len(checks)} Project Standards check(s)")
    hint("dku project-standards list-checks")


@app.command("update-check")
@handle_errors
def update_check(
    ctx: typer.Context,
    check_id: str = typer.Argument(help="Check id"),
    name: str | None = typer.Option(None, "--name", help="New check name"),
    description: str | None = typer.Option(
        None, "--description", help="New description"
    ),
    params: str | None = typer.Option(
        None, "--params", help="Check params JSON, @file.json, or '-' for stdin"
    ),
    tags: str | None = typer.Option(
        None, "--tags", help="Comma-separated replacement tags"
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Authorize admin write"),
    confirm_name: str | None = typer.Option(
        None, "--confirm-name", help="Must equal CHECK_ID"
    ),
    i_know: bool = typer.Option(
        False, "--i-know-what-im-doing", help="Tier-4 admin acknowledgement"
    ),
) -> None:
    """Update a check's name, description, params, or tags (admin)."""
    if all(value is None for value in (name, description, params, tags)):
        exit_with_error(
            "No check updates requested.",
            details=[
                "Provide --name, --description, --params, and/or --tags.",
                f"Inspect first: dku project-standards get-check {check_id}",
            ],
        )
    parsed_params = read_json_input(params)
    if parsed_params is not None and not isinstance(parsed_params, dict):
        exit_with_error(
            "Check params must be a JSON object.",
            details=[
                "Read the schema: dku --format json project-standards list-check-specs"
            ],
        )
    client = get_client_from_ctx(ctx)
    standards = client.get_project_standards()
    standards.get_check(check_id)
    guard_admin(
        ctx,
        action="project-standards.check.update",
        subject=f"Project Standards check '{check_id}'",
        target_id=check_id,
        yes=yes,
        confirm_name=confirm_name,
        i_know=i_know,
    )

    def apply(check):
        if name is not None:
            check.name = name
        if description is not None:
            check.description = description
        if parsed_params is not None:
            check.check_params = parsed_params
        if tags is not None:
            check.tags = [tag.strip() for tag in tags.split(",") if tag.strip()]
        return check

    mutate_settings(
        client,
        "instance",
        "project-standards-check",
        check_id,
        fetch=lambda: standards.get_check(check_id),
        mutate=apply,
    )
    render_resource(standards.get_check(check_id), resolve_output_format())
    success(f"Updated Project Standards check '{check_id}'")


@app.command("delete-check")
@handle_errors
def delete_check(
    ctx: typer.Context,
    check_id: str = typer.Argument(help="Check id"),
    force: bool = typer.Option(
        False, "--force", help="Remove references from every scope before deleting"
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Authorize admin write"),
    confirm_name: str | None = typer.Option(
        None, "--confirm-name", help="Must equal CHECK_ID"
    ),
    i_know: bool = typer.Option(
        False, "--i-know-what-im-doing", help="Tier-4 admin acknowledgement"
    ),
) -> None:
    """Delete a check without leaving dangling scope references (admin)."""
    client = get_client_from_ctx(ctx)
    standards = client.get_project_standards()
    standards.get_check(check_id)
    usages = _referencing_scopes(standards, check_id)
    if usages and not force:
        _exit_referenced(check_id, usages)
    guard_admin(
        ctx,
        action="project-standards.check.delete",
        subject=f"Project Standards check '{check_id}'",
        target_id=check_id,
        yes=yes,
        confirm_name=confirm_name,
        i_know=i_know,
    )
    with policy_write_lock(client):
        usages = _referencing_scopes(standards, check_id)
        if usages and not force:
            _exit_referenced(check_id, usages)
        for scope_name in usages if force else []:
            mutate_settings(
                client,
                "instance",
                "project-standards-scope",
                scope_name,
                fetch=lambda scope_name=scope_name: standards.get_scope(scope_name),
                mutate=lambda scope: _remove_check(scope, check_id),
            )
        remaining = _referencing_scopes(standards, check_id)
        if remaining:
            exit_with_error(
                f"Not deleting check '{check_id}': scope references remain.",
                details=[
                    f"Scopes: {', '.join(remaining)}",
                    "Another policy writer may have changed a scope; "
                    "re-run the command.",
                ],
            )
        standards.get_check(check_id).delete()
        if check_id in {item.id for item in standards.list_checks()}:
            exit_with_error(
                f"DSS reported success but check '{check_id}' still exists.",
                details=["Verify with: dku project-standards list-checks"],
            )
    success(f"Deleted Project Standards check '{check_id}'")
    hint("dku project-standards list-checks")


def _remove_check(scope, check_id: str):
    scope.checks = [item for item in scope.checks if item != check_id]
    return scope


def _referencing_scopes(standards, check_id: str) -> list[str]:
    return [
        scope.get("name", "")
        for scope in standards.list_scopes()
        if check_id in (scope.get("checks") or [])
    ]


def _exit_referenced(check_id: str, usages: list[str]) -> None:
    exit_with_error(
        f"Check '{check_id}' is still referenced by {len(usages)} scope(s).",
        details=[
            f"Scopes: {', '.join(usages)}",
            "The DSS API would leave dangling check IDs.",
            "Re-run with --force to remove the references first.",
        ],
    )
