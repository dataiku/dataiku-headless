"""dku govern role-assignment — bind Govern roles to groups/users per blueprint.

Binding a role to at least one group or user is a PREREQUISITE for any sign-off
workflow: an unbound role produces an empty approver set, so every mandatory
gate becomes permanently un-crossable (a silent dead-workflow). This command
group is the CLI path for that binding, which previously required reverse-
engineering `create_role_assignments` against dataikuapi.
"""

from __future__ import annotations

import typer

from dku_cli.errors import handle_api_error
from dku_cli.helpers import get_govern_client_from_ctx
from dku_cli.output import (
    error,
    info,
    render,
    render_raw,
    resolve_output_format,
    success,
)
from dku_cli.safety import Tier, guard

app = typer.Typer(help="Bind Govern roles to groups/users (per blueprint).")


@app.command("list")
def list_assignments(
    ctx: typer.Context,
) -> None:
    """List blueprint role assignments across all blueprints."""
    output = resolve_output_format()
    try:
        govern = get_govern_client_from_ctx(ctx)
        handler = govern.get_roles_permissions_handler()
        data = []
        for item in handler.list_role_assignments():
            raw = item.get_raw()
            rules = raw.get("roleAssignmentsRules", {}) or {}
            data.append(
                {
                    "blueprint_id": raw.get("blueprintId", ""),
                    "roles_bound": ", ".join(sorted(rules.keys())) or "(none)",
                }
            )
        render(
            data,
            ["blueprint_id", "roles_bound"],
            output_format=output,
            title="Govern Role Assignments",
            headers={"blueprint_id": "BLUEPRINT", "roles_bound": "ROLES BOUND"},
        )
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def get(
    ctx: typer.Context,
    blueprint_id: str = typer.Argument(
        help="Blueprint ID (e.g. bp.system.dataiku_project)"
    ),
) -> None:
    """Show the full role-assignment rules for one blueprint."""
    output = resolve_output_format()
    try:
        govern = get_govern_client_from_ctx(ctx)
        handler = govern.get_roles_permissions_handler()
        defn = handler.get_role_assignments(blueprint_id).get_definition()
        render_raw(defn.get_raw(), output_format=output)
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("set")
def set_assignment(
    ctx: typer.Context,
    blueprint_id: str = typer.Argument(
        help="Blueprint ID (e.g. bp.system.dataiku_project)"
    ),
    role: str = typer.Option(
        ..., "--role", "-r", help="Role ID to bind (e.g. ro.reviewer)"
    ),
    groups: list[str] = typer.Option(
        None, "--group", "-g", help="Group name to bind (repeatable)"
    ),
    users: list[str] = typer.Option(
        None, "--user", "-u", help="User login to bind (repeatable)"
    ),
) -> None:
    """Bind a role to one or more groups/users for a blueprint.

    The role is assigned to EXACTLY the listed containers (idempotent — re-runs
    replace the role's binding). At least one --group or --user is required:
    binding an empty container set silently breaks every gate that uses the role.

    Example:
      dku govern role-assignment set bp.system.dataiku_project \\
        --role ro.reviewer --group data-stewards --profile my-govern
    """
    groups = groups or []
    users = users or []
    if not groups and not users:
        error("At least one --group or --user is required.")
        info(
            "An unbound role has an empty approver set, so every mandatory gate "
            "using it becomes permanently un-crossable (silent dead-workflow)."
        )
        info(
            "Example: dku govern role-assignment set "
            f"{blueprint_id} --role {role} --group <GROUP_NAME>"
        )
        raise typer.Exit(2)

    containers = [{"type": "group", "groupName": g} for g in groups]
    containers += [{"type": "user", "login": u} for u in users]
    # Empirically-verified rule shape: a missing "criteria"/"fieldIds" key, or
    # passing the containers under the wrong key, silently stores an empty
    # binding (no server error). Keep all three keys.
    rule = [{"criteria": [], "userContainers": containers, "fieldIds": []}]

    try:
        govern = get_govern_client_from_ctx(ctx)
        handler = govern.get_roles_permissions_handler()

        existing_ids = {
            item.get_raw().get("blueprintId")
            for item in handler.list_role_assignments()
        }

        if blueprint_id in existing_ids:
            defn = handler.get_role_assignments(blueprint_id).get_definition()
            raw = defn.get_raw()
            raw.setdefault("roleAssignmentsRules", {})[role] = rule
            defn.save()
        else:
            payload = {
                "blueprintId": blueprint_id,
                "roleAssignmentsRules": {role: rule},
            }
            handler.create_role_assignments(payload)

        bound = ", ".join(groups + users)
        success(f"Bound role '{role}' to {bound} on blueprint '{blueprint_id}'")
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def delete(
    ctx: typer.Context,
    blueprint_id: str = typer.Argument(
        help="Blueprint ID (e.g. bp.system.dataiku_project)"
    ),
    confirm: bool = typer.Option(
        False, "--confirm", "--yes", "-y", help="Confirm deletion (required)"
    ),
) -> None:
    """Delete ALL role assignments for a blueprint. Requires --yes.

    This removes every role binding on the blueprint at once — any sign-off gate
    relying on those roles will lose its approvers.
    """
    guard(
        ctx,
        tier=Tier.DELETE,
        action="govern.role_assignment.delete",
        subject=f"all role assignments for blueprint '{blueprint_id}'",
        yes=confirm,
        prompt=(
            f"Delete EVERY role binding on blueprint '{blueprint_id}'? "
            "Sign-off gates relying on those roles lose their approvers."
        ),
    )
    try:
        govern = get_govern_client_from_ctx(ctx)
        handler = govern.get_roles_permissions_handler()
        handler.get_role_assignments(blueprint_id).delete()
        success(f"Deleted all role assignments for blueprint '{blueprint_id}'")
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)
