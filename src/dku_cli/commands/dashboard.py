"""dku dashboard — list, get, create, delete, get/set-definition, set-metadata."""

from __future__ import annotations

import typer

from dku_cli.errors import handle_api_error, is_already_exists_error
from dku_cli.helpers import (
    get_client_from_ctx,
    read_json_input,
    resolve_project,
    update_taggable_metadata,
)
from dku_cli.output import (
    error,
    hint,
    render,
    render_raw,
    resolve_output_format,
    success,
    warn,
)

app = typer.Typer(help="Manage DSS dashboards.")


def _default_page() -> dict:
    return {
        "id": "page1",
        "title": "Page 1",
        "displayedTitle": "Page 1",
        "show": True,
        "showTitle": False,
        "titleAlign": "CENTER",
        "titleFontColor": "#333",
        "titleFontSize": 28,
        "enableCrossFilters": True,
        "backgroundColor": "#FFFEF9",
        "showFilterPanel": False,
        "filtersParams": {"panelPosition": "TOP"},
        "grid": {"tiles": []},
    }


@app.command("list")
def list_dashboards(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """List dashboards in a project."""
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        dashboards = proj.list_dashboards()

        data = []
        for d in dashboards:
            data.append(
                {
                    "id": d.get("id", ""),
                    "name": d.get("name", ""),
                }
            )

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
) -> None:
    """Get dashboard details."""
    project_key = resolve_project(project)
    output = resolve_output_format()
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
                len(p.get("grid", {}).get("tiles", p.get("tiles", []))) for p in pages
            )
            data = [
                {"field": "ID", "value": raw.get("id", dashboard_id)},
                {"field": "Name", "value": raw.get("name", "")},
                {"field": "Pages", "value": str(len(pages))},
                {"field": "Tiles", "value": str(tiles)},
            ]
            render(
                data,
                ["field", "value"],
                title=f"Dashboard: {dashboard_id}",
            )
    except Exception as e:
        handle_api_error(e)


@app.command()
def create(
    ctx: typer.Context,
    name: str = typer.Argument(help="Dashboard name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    definition: str | None = typer.Option(
        None,
        "--definition",
        "-d",
        help="JSON settings (string, @file.json, or - for stdin)",
    ),
    if_not_exists: bool = typer.Option(
        False, "--if-not-exists", help="Skip if dashboard already exists"
    ),
) -> None:
    """Create a new dashboard."""
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        settings = read_json_input(definition)
        kwargs: dict = {"dashboard_name": name}
        if settings is not None:
            kwargs["settings"] = settings
        else:
            kwargs["settings"] = {"pages": [_default_page()]}
        dashboard = proj.create_dashboard(**kwargs)
        if output == "json":
            render_raw(
                {"id": dashboard.dashboard_id, "name": name},
                output_format=output,
            )
        else:
            success(f"Created dashboard '{name}' (id={dashboard.dashboard_id})")
            hint(f"dku dashboard get {dashboard.dashboard_id} -P {project_key}")
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
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip safety guard"),
) -> None:
    """Delete a dashboard."""
    from dku_cli.safety import Tier, guard

    project_key = resolve_project(project)
    guard(
        ctx,
        tier=Tier.DELETE,
        action="dashboard.delete",
        subject=f"dashboard '{dashboard_id}' in {project_key}",
        yes=yes,
        prompt=f"Delete dashboard '{dashboard_id}' from {project_key}?",
    )
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        dashboard = proj.get_dashboard(dashboard_id)
        dashboard.delete()
        success(f"Deleted dashboard '{dashboard_id}'")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("get-definition")
def get_definition(
    ctx: typer.Context,
    dashboard_id: str = typer.Argument(help="Dashboard ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Get the raw definition of a dashboard as JSON."""
    project_key = resolve_project(project)
    output = resolve_output_format()
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
        ...,
        "--definition",
        "-d",
        help="JSON definition (string, @file.json, or - for stdin)",
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


@app.command("set-metadata")
def set_metadata(
    ctx: typer.Context,
    dashboard_id: str = typer.Argument(help="Dashboard ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    description: str | None = typer.Option(
        None, "--description", "-d", help="Dashboard description"
    ),
    short_desc: str | None = typer.Option(
        None, "--short-desc", help="Short description"
    ),
    tags: str | None = typer.Option(
        None, "--tags", help="Comma-separated tags (replaces existing)"
    ),
) -> None:
    """Update dashboard description, short description, and/or tags.

    No JSON needed — updates metadata fields directly.
    """
    if description is None and short_desc is None and tags is None:
        error("Provide --description, --short-desc, and/or --tags to update.")
        raise typer.Exit(1)
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        dashboard = proj.get_dashboard(dashboard_id)
        settings = dashboard.get_settings()
        update_taggable_metadata(settings, description, short_desc, tags)
        success(f"Updated metadata for dashboard '{dashboard_id}'")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("list-tiles")
def list_tiles(
    ctx: typer.Context,
    dashboard_id: str = typer.Argument(help="Dashboard ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """List tiles across all pages of a dashboard.

    dku dashboard list-tiles DASH_ID -P PROJ
    """
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        raw = proj.get_dashboard(dashboard_id).get_settings().get_raw()
        data = []
        for page_idx, page in enumerate(raw.get("pages", [])):
            for tile in page.get("grid", {}).get("tiles", []):
                data.append(
                    {
                        "page": page_idx,
                        "page_id": page.get("id", ""),
                        "insight_id": tile.get("insightId", ""),
                        "display_mode": tile.get("displayMode", ""),
                        "show_title": tile.get("showTitle", ""),
                    }
                )
        render(
            data,
            ["page", "page_id", "insight_id", "display_mode", "show_title"],
            output_format=output,
            title=f"Tiles in dashboard {dashboard_id}",
        )
    except Exception as e:
        handle_api_error(e)


@app.command("add-tile")
def add_tile(
    ctx: typer.Context,
    dashboard_id: str = typer.Argument(help="Dashboard ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    insight_id: str = typer.Option(..., "--insight", "-i", help="Insight ID to add"),
    page: int = typer.Option(0, "--page", help="Page index (0-based)"),
    width: int = typer.Option(6, "--width", "-w", help="Tile width (grid units, 1-12)"),
    height: int = typer.Option(4, "--height", help="Tile height (grid units)"),
) -> None:
    """Add an insight tile to a dashboard page.

    dku dashboard add-tile DASH_ID --insight INSIGHT_ID -P PROJ
    dku dashboard add-tile DASH_ID --insight INSIGHT_ID --page 1 --width 12 -P PROJ
    """
    from dku_cli.errors import exit_with_error

    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        dashboard = proj.get_dashboard(dashboard_id)
        settings = dashboard.get_settings()
        raw = settings.get_raw()
        pages = raw.get("pages", [])
        if page >= len(pages):
            exit_with_error(
                f"Page index {page} out of range (dashboard has {len(pages)} page(s))",
                details=[
                    f"dku dashboard get {dashboard_id} -P {project_key}  # check page count"
                ],
            )
        # DSS requires every INSIGHT tile to carry `tileType` AND `insightType`.
        # Omitting them makes the dashboard fail to render with the cryptic
        # `JsonParseException: Insight type null is unknown` — DSS does NOT infer
        # the type from the linked insight. Look it up from the insight itself.
        try:
            insight_raw = proj.get_insight(insight_id).get_settings().get_raw()
            insight_type = insight_raw.get("type")
        except Exception:
            insight_type = None
        if not insight_type:
            exit_with_error(
                f"Could not resolve the type of insight '{insight_id}' — cannot build the tile",
                details=[
                    f"dku insight list -P {project_key}  # confirm the insight ID exists",
                    "A tile needs insightType (chart, dataset_table, ...); DSS does not infer it.",
                ],
            )
        tiles = pages[page].setdefault("grid", {}).setdefault("tiles", [])
        top = max(
            (
                t.get("box", {}).get("top", 0) + t.get("box", {}).get("height", 4)
                for t in tiles
            ),
            default=0,
        )
        tiles.append(
            {
                "tileType": "INSIGHT",
                "insightId": insight_id,
                "insightType": insight_type,
                "box": {"left": 0, "top": top, "width": width, "height": height},
                "displayMode": "INSIGHT",
                "showTitle": True,
                "resizeMode": "FIT_INSIGHT",
            }
        )
        settings.save()
        success(
            f"Added insight '{insight_id}' to page {page} of dashboard '{dashboard_id}'"
        )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("remove-tile")
def remove_tile(
    ctx: typer.Context,
    dashboard_id: str = typer.Argument(help="Dashboard ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    insight_id: str = typer.Option(..., "--insight", "-i", help="Insight ID to remove"),
    page: int = typer.Option(
        None, "--page", help="Page index to limit removal to (default: all pages)"
    ),
) -> None:
    """Remove all tiles referencing an insight from a dashboard.

    dku dashboard remove-tile DASH_ID --insight INSIGHT_ID -P PROJ
    dku dashboard remove-tile DASH_ID --insight INSIGHT_ID --page 0 -P PROJ
    """
    from dku_cli.errors import exit_with_error

    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        dashboard = proj.get_dashboard(dashboard_id)
        settings = dashboard.get_settings()
        raw = settings.get_raw()
        removed = 0
        for page_idx, pg in enumerate(raw.get("pages", [])):
            if page is not None and page_idx != page:
                continue
            tiles = pg.get("grid", {}).get("tiles", [])
            before = len(tiles)
            pg["grid"]["tiles"] = [t for t in tiles if t.get("insightId") != insight_id]
            removed += before - len(pg["grid"]["tiles"])
        if removed == 0:
            exit_with_error(
                f"Insight '{insight_id}' not found in dashboard '{dashboard_id}'",
                details=[
                    f"dku dashboard list-tiles {dashboard_id} -P {project_key}  # check tile insight IDs"
                ],
            )
        settings.save()
        success(
            f"Removed {removed} tile(s) referencing '{insight_id}' from dashboard '{dashboard_id}'"
        )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)
