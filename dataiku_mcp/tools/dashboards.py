"""Dashboard operations for Dataiku DSS."""

from fastmcp import Context

from .. import mcp
from .utils.async_executor import run_blocking
from .utils.auth import get_dss_client
from .utils.parsing import coerce_json_object as _coerce_json_object
from .utils.serialization import columnar, compact_json
from .utils.validation import require_non_empty_string as _require_non_empty_string


def _serialize_dashboard_list_item(item) -> dict:
    return {
        "id": item.id,
        "name": item.name,
        "listed": item.listed,
        "owner": item.owner,
        "num_pages": item.num_pages,
        "num_tiles": item.num_tiles,
        "tags": item.tags,
    }


@mcp.tool()
async def list_dashboards(project_key: str, ctx: Context) -> str:
    """List the dashboards in the project."""
    project_key = _require_non_empty_string(project_key, "project_key")
    await ctx.info(f"Listing dashboards in {project_key}...")

    items = await run_blocking(
        lambda: get_dss_client().get_project(project_key).list_dashboards()
    )
    dashboards = [_serialize_dashboard_list_item(item) for item in items]

    return compact_json(
        {
            "dashboards": columnar(
                dashboards,
                ["id", "name", "listed", "owner", "num_pages", "num_tiles", "tags"],
            )
        }
    )


@mcp.tool()
async def get_dashboard_settings(
    project_key: str,
    dashboard_id: str,
    ctx: Context,
) -> str:
    """Get the full dashboard settings dict for round-trip editing."""
    project_key = _require_non_empty_string(project_key, "project_key")
    dashboard_id = _require_non_empty_string(dashboard_id, "dashboard_id")
    await ctx.info(f"Loading dashboard {dashboard_id} in {project_key}...")

    raw = await run_blocking(
        lambda: (
            get_dss_client()
            .get_project(project_key)
            .get_dashboard(dashboard_id)
            .get_settings()
            .get_raw()
        )
    )
    return compact_json(raw)


@mcp.tool()
async def create_dashboard(
    project_key: str,
    dashboard_name: str,
    ctx: Context,
    settings=None,
) -> str:
    """Create a dashboard in the project.

    Args:
        settings: Optional partial or full dashboard settings object. The tool always
            sets the dashboard name from dashboard_name.
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    dashboard_name = _require_non_empty_string(dashboard_name, "dashboard_name")
    settings_obj = {} if settings is None else _coerce_json_object(settings, "settings")

    await ctx.info(f"Creating dashboard '{dashboard_name}' in {project_key}...")

    def _run():
        project = get_dss_client().get_project(project_key)
        dashboard = project.create_dashboard(dashboard_name, settings=dict(settings_obj))
        return dashboard.get_settings().get_raw()

    created = await run_blocking(_run)
    return compact_json({"dashboard": created})


@mcp.tool()
async def set_dashboard_settings(
    project_key: str,
    dashboard_id: str,
    new_settings,
    ctx: Context,
) -> str:
    """Replace the full dashboard settings dict.

    Args:
        new_settings: A modified version of the object returned by
            get_dashboard_settings
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    dashboard_id = _require_non_empty_string(dashboard_id, "dashboard_id")
    new_settings_obj = _coerce_json_object(new_settings, "new_settings")

    await ctx.info(f"Replacing settings for dashboard {dashboard_id} in {project_key}...")

    def _run():
        dashboard = get_dss_client().get_project(project_key).get_dashboard(dashboard_id)
        settings = dashboard.get_settings()
        settings.settings = dict(new_settings_obj)
        settings.save()
        return dashboard.get_settings().get_raw()

    updated = await run_blocking(_run)
    return compact_json({"dashboard": updated})


@mcp.tool()
async def delete_dashboard(
    project_key: str,
    dashboard_id: str,
    ctx: Context,
) -> str:
    """Delete the dashboard."""
    project_key = _require_non_empty_string(project_key, "project_key")
    dashboard_id = _require_non_empty_string(dashboard_id, "dashboard_id")
    await ctx.info(f"Deleting dashboard {dashboard_id} in {project_key}...")

    await run_blocking(
        lambda: get_dss_client()
        .get_project(project_key)
        .get_dashboard(dashboard_id)
        .delete()
    )
    return compact_json({})
