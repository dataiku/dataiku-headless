"""Dashboard inspection for Dataiku DSS."""

from fastmcp import Context

from .. import mcp
from .utils.async_executor import run_blocking
from .utils.auth import get_dss_client
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
