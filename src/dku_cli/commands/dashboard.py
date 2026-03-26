"""dku dashboard — list, get, create, delete, get/set-definition."""

from __future__ import annotations

import typer

from dku_cli.errors import handle_api_error, is_already_exists_error
from dku_cli.helpers import get_client_from_ctx, read_json_input, resolve_project
from dku_cli.output import render, render_raw, resolve_output_format, success, warn

app = typer.Typer(help="Manage DSS dashboards.")


@app.command("list")
def list_dashboards(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List dashboards in a project."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        dashboards = proj.list_dashboards()

        data = []
        for d in dashboards:
            data.append({
                "id": d.get("id", ""),
                "name": d.get("name", ""),
            })

        render(
            data,
            ["id", "name"],
            output_format=output,
            title=f"Dashboards ({project_key})",
        )
    except Exception as e:
        handle_api_error(e)


@app.command()
def get(
    ctx: typer.Context,
    dashboard_id: str = typer.Argument(help="Dashboard ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Get dashboard details."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        dashboard = proj.get_dashboard(dashboard_id)
        raw = dashboard.get_settings().get_raw()

        if output == "json":
            render_raw(raw, output_format=output)
        else:
            pages = raw.get("pages", [])
            tiles = sum(
                len(p.get("grid", {}).get("tiles", p.get("tiles", [])))
                for p in pages
            )
            data = [
                {"field": "ID", "value": raw.get("id", dashboard_id)},
                {"field": "Name", "value": raw.get("name", "")},
                {"field": "Pages", "value": str(len(pages))},
                {"field": "Tiles", "value": str(tiles)},
            ]
            render(data, ["field", "value"], output_format="table", title=f"Dashboard: {dashboard_id}")
    except Exception as e:
        handle_api_error(e)


@app.command()
def create(
    ctx: typer.Context,
    name: str = typer.Argument(help="Dashboard name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    definition: str | None = typer.Option(
        None, "--definition", "-d", help="JSON settings (string, @file.json, or - for stdin)"
    ),
    if_not_exists: bool = typer.Option(False, "--if-not-exists", help="Skip if dashboard already exists"),
) -> None:
    """Create a new dashboard."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        settings = read_json_input(definition)
        kwargs: dict = {"dashboard_name": name}
        if settings is not None:
            kwargs["settings"] = settings
        dashboard = proj.create_dashboard(**kwargs)
        success(f"Created dashboard '{name}' (id={dashboard.dashboard_id})")
    except Exception as e:
        if if_not_exists and is_already_exists_error(e):
            warn(f"Dashboard '{name}' already exists in {project_key}, skipping create")
            return
        handle_api_error(e)


@app.command()
def delete(
    ctx: typer.Context,
    dashboard_id: str = typer.Argument(help="Dashboard ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Delete a dashboard."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        dashboard = proj.get_dashboard(dashboard_id)
        dashboard.delete()
        success(f"Deleted dashboard '{dashboard_id}'")
    except Exception as e:
        handle_api_error(e)


@app.command("get-definition")
def get_definition(
    ctx: typer.Context,
    dashboard_id: str = typer.Argument(help="Dashboard ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Get the raw definition of a dashboard as JSON."""
    project_key = resolve_project(project)
    output = resolve_output_format(output, allowed=("json",), default="json")
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        dashboard = proj.get_dashboard(dashboard_id)
        defn = dashboard.get_settings().get_raw()
        render_raw(defn, output_format=output)
    except Exception as e:
        handle_api_error(e)


@app.command("set-definition")
def set_definition(
    ctx: typer.Context,
    dashboard_id: str = typer.Argument(help="Dashboard ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    definition: str = typer.Option(
        ..., "--definition", "-d", help="JSON definition (string, @file.json, or - for stdin)"
    ),
) -> None:
    """Update a dashboard's definition from JSON."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        dashboard = proj.get_dashboard(dashboard_id)
        new_def = read_json_input(definition)
        settings = dashboard.get_settings()
        raw = settings.get_raw()
        raw.clear()
        raw.update(new_def)
        settings.save()
        success(f"Updated definition for dashboard '{dashboard_id}'")
    except Exception as e:
        handle_api_error(e)
