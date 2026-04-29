"""dku workspace — list, create, get, delete, list-objects for workspace management."""

from __future__ import annotations

import typer

from dku_cli.errors import handle_api_error
from dku_cli.helpers import get_client_from_ctx
from dku_cli.output import info, render, render_raw, resolve_output_format, success

app = typer.Typer(help="Manage DSS workspaces.")


@app.command("list")
def list_workspaces(
    ctx: typer.Context,
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List all workspaces."""
    fmt = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        items = client.list_workspaces()

        if fmt == "json":
            render_raw(items, output_format="json")
        else:
            if not items:
                info("No workspaces found.")
                return

            data = []
            for w in items:
                data.append(
                    {
                        "key": w.get("workspaceKey", ""),
                        "name": w.get("displayName", ""),
                        "color": w.get("color", ""),
                    }
                )
            render(
                data,
                ["key", "name", "color"],
                output_format=fmt,
                title="Workspaces",
                headers={"key": "KEY", "name": "NAME", "color": "COLOR"},
            )
    except Exception as e:
        handle_api_error(e)


@app.command()
def create(
    ctx: typer.Context,
    workspace_key: str = typer.Argument(help="Workspace key (unique identifier)"),
    name: str = typer.Option(..., "--name", "-n", help="Display name"),
    description: str | None = typer.Option(
        None, "--description", "-d", help="Description"
    ),
    color: str | None = typer.Option(None, "--color", help="Color (e.g. #4CAF50)"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Create a new workspace.

    Example:
      dku workspace create ANALYTICS --name "Analytics Hub"
      dku workspace create TEAM_DS --name "Data Science" --color "#4CAF50"
    """
    fmt = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        client.create_workspace(
            workspace_key, name, description=description, color=color
        )

        if fmt == "json":
            render_raw(
                {"key": workspace_key, "name": name},
                output_format="json",
            )
        else:
            success(f"Created workspace '{name}' (key: {workspace_key})")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def get(
    ctx: typer.Context,
    workspace_key: str = typer.Argument(help="Workspace key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Get workspace settings."""
    output = resolve_output_format(output, allowed=("json",), default="json")
    try:
        client = get_client_from_ctx(ctx)
        ws = client.get_workspace(workspace_key)
        settings = ws.get_settings()
        render_raw(settings.get_raw(), output_format=output)
    except Exception as e:
        handle_api_error(e)


@app.command("list-objects")
def list_objects(
    ctx: typer.Context,
    workspace_key: str = typer.Argument(help="Workspace key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List objects in a workspace (datasets, dashboards, articles, etc).

    Example:
      dku workspace list-objects ANALYTICS
    """
    fmt = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        ws = client.get_workspace(workspace_key)
        objects = ws.list_objects()

        if fmt == "json":
            raw = [o.get_raw() for o in objects]
            render_raw(raw, output_format="json")
        else:
            if not objects:
                info(f"No objects in workspace '{workspace_key}'.")
                return

            data = []
            for o in objects:
                raw = o.get_raw()
                ref = raw.get("reference", {})
                data.append(
                    {
                        "type": ref.get("type", raw.get("objectType", "")),
                        "id": ref.get("id", ""),
                        "project": ref.get("projectKey", ""),
                    }
                )
            render(
                data,
                ["type", "id", "project"],
                output_format=fmt,
                title=f"Objects ({workspace_key})",
                headers={"type": "TYPE", "id": "ID", "project": "PROJECT"},
            )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def delete(
    ctx: typer.Context,
    workspace_key: str = typer.Argument(help="Workspace key"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Delete a workspace (requires admin rights).

    Example:
      dku workspace delete ANALYTICS --yes
    """
    from dku_cli.safety import Tier, guard

    guard(
        ctx,
        tier=Tier.DELETE,
        action="workspace.delete",
        subject=f"workspace '{workspace_key}'",
        yes=yes,
        prompt=f"Delete workspace '{workspace_key}'?",
    )
    try:
        client = get_client_from_ctx(ctx)
        ws = client.get_workspace(workspace_key)
        ws.delete()
        success(f"Deleted workspace '{workspace_key}'")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)
