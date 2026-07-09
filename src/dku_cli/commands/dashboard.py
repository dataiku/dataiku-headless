"""dku dashboard — list, get, create, delete, get/set-definition, set-metadata."""

from __future__ import annotations

import typer

from dku_cli.commands._dashboard_page import _default_page
from dku_cli.errors import handle_api_error, is_already_exists_error
from dku_cli.helpers import (
    dashboard_url,
    get_client_from_ctx,
    locked_settings,
    object_write_lock,
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
        pages = raw.get("pages", [])
        tile_count = sum(
            len(p.get("grid", {}).get("tiles", p.get("tiles", []))) for p in pages
        )
        raw["working_url"] = dashboard_url(client, project_key, dashboard_id)
        raw["tile_count"] = tile_count
        render_raw(raw, output_format=output)
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
        url = dashboard_url(client, project_key, dashboard.dashboard_id)
        if output == "json":
            render_raw(
                {"id": dashboard.dashboard_id, "name": name, "url": url},
                output_format=output,
            )
        else:
            success(f"Created dashboard '{name}' (id={dashboard.dashboard_id})")
            hint(f"URL (cite this exact form; the trailing slash matters): {url}")
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
        with locked_settings(
            client, project_key, "dashboard", dashboard_id, dashboard.get_settings
        ) as settings:
            raw = settings.get_raw()
            raw.clear()
            raw.update(new_def)
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
        with object_write_lock(client, project_key, "dashboard", dashboard_id):
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


# Dashboard pages are a 36-column grid; rows are the same size as columns, and
# the whole grid scales with the viewport width (no reflow at narrow sizes).
GRID_COLUMNS = 36


def _flow_box(tiles: list[dict], width: int, height: int) -> dict:
    """Next slot in reading order: beside the last row if it fits, else below."""
    if not tiles:
        return {"top": 0, "left": 0, "width": width, "height": height}
    boxes = [t.get("box", {}) for t in tiles]
    row_top = max(b.get("top", 0) for b in boxes)
    row = [b for b in boxes if b.get("top", 0) == row_top]
    row_right = max(b.get("left", 0) + b.get("width", 0) for b in row)
    if row_right + width <= GRID_COLUMNS:
        return {"top": row_top, "left": row_right, "width": width, "height": height}
    bottom = max(b.get("top", 0) + b.get("height", 0) for b in boxes)
    return {"top": bottom, "left": 0, "width": width, "height": height}


@app.command("add-tile")
def add_tile(
    ctx: typer.Context,
    dashboard_id: str = typer.Argument(help="Dashboard ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    insight_id: str = typer.Option(..., "--insight", "-i", help="Insight ID to add"),
    page: int = typer.Option(0, "--page", help="Page index (0-based)"),
    width: int = typer.Option(
        18,
        "--width",
        "-w",
        min=1,
        max=GRID_COLUMNS,
        help="Tile width in grid columns (a page is 36 wide; 18 = half, 36 = full)",
    ),
    height: int = typer.Option(
        10,
        "--height",
        min=1,
        help="Tile height in grid rows (a row is as tall as a column is wide)",
    ),
) -> None:
    """Add an insight tile to a dashboard page.

    Tiles flow left-to-right, wrapping to a new row when the current one is
    full. For explicit placement, edit box {top,left,width,height} via
    set-definition.

    dku dashboard add-tile DASH_ID --insight INSIGHT_ID -P PROJ
    dku dashboard add-tile DASH_ID --insight INSIGHT_ID --width 36 --height 4 -P PROJ
    """
    from dku_cli.errors import exit_with_error

    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        dashboard = proj.get_dashboard(dashboard_id)
        with locked_settings(
            client, project_key, "dashboard", dashboard_id, dashboard.get_settings
        ) as settings:
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
                insight_name = insight_raw.get("name") or insight_id
            except Exception:
                insight_type = None
                insight_name = insight_id
            if not insight_type:
                exit_with_error(
                    f"Could not resolve the type of insight '{insight_id}' — cannot build the tile",
                    details=[
                        f"dku insight list -P {project_key}  # confirm the insight ID exists",
                        "A tile needs insightType (chart, dataset_table, ...); DSS does not infer it.",
                    ],
                )
            tiles = pages[page].setdefault("grid", {}).setdefault("tiles", [])
            # DSS drops unknown tile fields on save (a top-level showTitle or
            # resizeMode comes back null) — titles live in titleOptions, and a
            # dataset_table tile without viewKind EXPLORE stays blank in view mode.
            tile = {
                "tileType": "INSIGHT",
                "insightId": insight_id,
                "insightType": insight_type,
                "displayMode": "INSIGHT",
                "box": _flow_box(tiles, width, height),
                "clickAction": "DO_NOTHING",
                "autoLoad": True,
                "titleOptions": {
                    "showTitle": "YES",
                    "title": insight_name,
                    "displayedTitle": insight_name,
                },
                "tileParams": {},
            }
            if insight_type == "chart":
                # dashboard tiles hide the chart's legend by default even though
                # the insight's own page shows it — multi-series charts are
                # unreadable without it
                tile["tileParams"].update(
                    {"showLegend": True, "inheritLegendPlacement": True}
                )
            if insight_type == "dataset_table":
                tile["tileParams"]["viewKind"] = "EXPLORE"
            tiles.append(tile)
        box = tile["box"]
        success(
            f"Added insight '{insight_id}' to page {page} of dashboard "
            f"'{dashboard_id}' at (top {box['top']}, left {box['left']}, "
            f"{box['width']}x{box['height']})"
        )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


def _tile_label(tile: dict) -> str:
    title = (tile.get("titleOptions") or {}).get("title")
    ref = tile.get("insightId") or tile.get("tileType", "tile")
    return f"'{title}' ({ref})" if title else f"{ref}"


def _box_desc(box: dict) -> str:
    return (
        f"(top {box.get('top', 0)}, left {box.get('left', 0)}, "
        f"{box.get('width', 0)}x{box.get('height', 0)})"
    )


def _boxes_overlap(a: dict, b: dict) -> bool:
    ax, ay = a.get("left", 0), a.get("top", 0)
    bx, by = b.get("left", 0), b.get("top", 0)
    return (
        ax < bx + b.get("width", 0)
        and bx < ax + a.get("width", 0)
        and ay < by + b.get("height", 0)
        and by < ay + a.get("height", 0)
    )


def _box_issue(page_idx: int, tile: dict) -> str | None:
    label = _tile_label(tile)
    box = tile.get("box") or {}
    left, width = box.get("left", 0), box.get("width", 0)
    if left < 0 or box.get("top", 0) < 0 or width < 1 or box.get("height", 0) < 1:
        return (
            f"page {page_idx}: {label} has a degenerate box {box} — "
            "fix top/left >= 0 and width/height >= 1"
        )
    if left + width > GRID_COLUMNS:
        return (
            f"page {page_idx}: {label} overflows the {GRID_COLUMNS}-column grid "
            f"(left {left} + width {width} = {left + width}) — the overflow is "
            f"clipped offscreen; keep left+width <= {GRID_COLUMNS}"
        )
    return None


def _insight_tile_issues(page_idx: int, tile: dict, insight_types: dict) -> list[str]:
    if tile.get("tileType") != "INSIGHT":
        return []
    issues = []
    label = _tile_label(tile)
    iid = tile.get("insightId")
    if not tile.get("insightType"):
        issues.append(
            f"page {page_idx}: {label} has no insightType — the dashboard "
            "fails to load ('Insight type null is unknown'); set it to the "
            "insight's own type"
        )
    if iid and insight_types and iid not in insight_types:
        issues.append(
            f"page {page_idx}: {label} references insight '{iid}' which "
            "does not exist in the project — the tile shows an error"
        )
    if (
        tile.get("insightType") == "dataset_table"
        and (tile.get("tileParams") or {}).get("viewKind") != "EXPLORE"
    ):
        issues.append(
            f"page {page_idx}: {label} is a dataset_table tile without "
            'tileParams.viewKind "EXPLORE" — it stays blank in view mode '
            "(clicking does nothing)"
        )
    return issues


def _page_tile_issues(page_idx: int, page: dict, insight_types: dict) -> list[str]:
    issues: list[str] = []
    if page.get("tiles"):
        issues.append(
            f"page {page_idx}: tiles found at pages[{page_idx}].tiles — DSS "
            "ignores them (dashboard loads, tiles vanish); move them to "
            f"pages[{page_idx}].grid.tiles"
        )
    tiles = page.get("grid", {}).get("tiles", [])
    for tile in tiles:
        box_issue = _box_issue(page_idx, tile)
        if box_issue:
            issues.append(box_issue)
        issues.extend(_insight_tile_issues(page_idx, tile, insight_types))
    for i, a in enumerate(tiles):
        for b in tiles[i + 1 :]:
            if a.get("box") and b.get("box") and _boxes_overlap(a["box"], b["box"]):
                issues.append(
                    f"page {page_idx}: {_tile_label(a)} {_box_desc(a['box'])} and "
                    f"{_tile_label(b)} {_box_desc(b['box'])} overlap — the renderer "
                    "silently displaces one of them, so the shown layout differs "
                    "from this definition; give them disjoint boxes"
                )
    return issues


@app.command()
def validate(
    ctx: typer.Context,
    dashboard_id: str = typer.Argument(help="Dashboard ID to validate"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Pre-flight a dashboard layout before a human loads it.

    Layout mistakes do not error at save time: DSS stores an out-of-bounds box
    verbatim and clips it offscreen, silently displaces overlapping tiles, drops
    tiles placed outside pages[].grid.tiles, and shows a dataset_table tile as
    permanently blank without viewKind EXPLORE. This surfaces those before the
    browser does. Chart content is validated per insight: dku insight validate.
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        raw = proj.get_dashboard(dashboard_id).get_settings().get_raw()
        try:
            insight_types = {i["id"]: i.get("type") for i in proj.list_insights()}
        except Exception:
            insight_types = {}
        issues: list[str] = []
        n_tiles = 0
        for page_idx, page in enumerate(raw.get("pages", [])):
            n_tiles += len(page.get("grid", {}).get("tiles", []))
            issues.extend(_page_tile_issues(page_idx, page, insight_types))
        if issues:
            error(
                f"{len(issues)} layout issue(s) — dashboard '{dashboard_id}' will "
                "not display as defined:"
            )
            for msg in issues:
                hint(f"  - {msg}")
            hint(
                f"  After fixing: dku dashboard set-definition {dashboard_id} "
                f"-d @fixed.json -P {project_key}"
            )
            raise SystemExit(1)
        success(
            f"dashboard '{dashboard_id}' passes pre-flight: {n_tiles} tile(s) "
            f"within the {GRID_COLUMNS}-column grid, no overlaps, references valid"
        )
        hint(
            f"charts are validated per insight: dku insight validate INSIGHT_ID "
            f"-P {project_key}"
        )
    except SystemExit:
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
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip safety guard"),
) -> None:
    """Remove all tiles referencing an insight from a dashboard.

    dku dashboard remove-tile DASH_ID --insight INSIGHT_ID -P PROJ
    dku dashboard remove-tile DASH_ID --insight INSIGHT_ID --page 0 -P PROJ
    """
    from dku_cli.errors import exit_with_error
    from dku_cli.safety import Tier, guard

    project_key = resolve_project(project)
    guard(
        ctx,
        tier=Tier.DELETE,
        action="dashboard.remove_tile",
        subject=f"tiles referencing insight '{insight_id}' in dashboard "
        f"'{dashboard_id}' in {project_key}",
        yes=yes,
        prompt=f"Remove tiles referencing '{insight_id}' from dashboard "
        f"'{dashboard_id}'?",
    )
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        dashboard = proj.get_dashboard(dashboard_id)
        with locked_settings(
            client, project_key, "dashboard", dashboard_id, dashboard.get_settings
        ) as settings:
            raw = settings.get_raw()
            removed = 0
            for page_idx, pg in enumerate(raw.get("pages", [])):
                if page is not None and page_idx != page:
                    continue
                tiles = pg.get("grid", {}).get("tiles", [])
                before = len(tiles)
                pg["grid"]["tiles"] = [
                    t for t in tiles if t.get("insightId") != insight_id
                ]
                removed += before - len(pg["grid"]["tiles"])
            if removed == 0:
                exit_with_error(
                    f"Insight '{insight_id}' not found in dashboard '{dashboard_id}'",
                    details=[
                        f"dku dashboard list-tiles {dashboard_id} -P {project_key}  # check tile insight IDs"
                    ],
                )
        success(
            f"Removed {removed} tile(s) referencing '{insight_id}' from dashboard '{dashboard_id}'"
        )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)
