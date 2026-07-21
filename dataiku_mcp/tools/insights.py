"""Chart insight inspection for Dataiku DSS."""

from fastmcp import Context

from .. import mcp
from .utils.async_executor import run_blocking
from .utils.auth import get_dss_client
from .utils.serialization import columnar, compact_json
from .utils.validation import require_non_empty_string as _require_non_empty_string


def _serialize_insight_list_item(item) -> dict:
    return {
        "id": item.id,
        "name": item.name,
        "type": item.type,
        "listed": item.listed,
        "owner": item.owner,
        "tags": item.tags,
    }


@mcp.tool()
async def list_insights(project_key: str, ctx: Context) -> str:
    """List the insights in the project."""
    project_key = _require_non_empty_string(project_key, "project_key")
    await ctx.info(f"Listing insights in {project_key}...")

    items = await run_blocking(
        lambda: get_dss_client().get_project(project_key).list_insights()
    )
    insights = [_serialize_insight_list_item(item) for item in items]
    return compact_json(
        {
            "insights": columnar(
                insights,
                ["id", "name", "type", "listed", "owner", "tags"],
            )
        }
    )
