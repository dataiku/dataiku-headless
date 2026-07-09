"""Chart insight operations for Dataiku DSS."""

from fastmcp import Context

from .. import mcp
from .utils.async_executor import run_blocking
from .utils.auth import get_dss_client
from .utils.parsing import coerce_json_object as _coerce_json_object
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


@mcp.tool()
async def get_insight_settings(
    project_key: str,
    insight_id: str,
    ctx: Context,
) -> str:
    """Get the full insight settings dict for round-trip editing."""
    project_key = _require_non_empty_string(project_key, "project_key")
    insight_id = _require_non_empty_string(insight_id, "insight_id")
    await ctx.info(f"Loading insight {insight_id} in {project_key}...")

    raw = await run_blocking(
        lambda: (
            get_dss_client()
            .get_project(project_key)
            .get_insight(insight_id)
            .get_settings()
            .get_raw()
        )
    )
    return compact_json(raw)


@mcp.tool()
async def create_insight(
    project_key: str,
    insight_prototype,
    ctx: Context,
) -> str:
    """Create an insight in the project.

    Args:
        insight_prototype: The raw insight definition object, without the
            outer {"insightPrototype": ...} wrapper.
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    prototype_obj = _coerce_json_object(insight_prototype, "insight_prototype")
    await ctx.info(f"Creating insight '{prototype_obj.get('name', '')}' in {project_key}...")

    def _run():
        project = get_dss_client().get_project(project_key)
        insight = project.create_insight(prototype_obj)
        return insight.get_settings().get_raw()

    created = await run_blocking(_run)
    return compact_json({"insight": created})


@mcp.tool()
async def set_insight_settings(
    project_key: str,
    insight_id: str,
    new_settings,
    ctx: Context,
) -> str:
    """Replace the full insight settings dict.

    Args:
        new_settings: A modified version of the object returned by
            get_insight_settings
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    insight_id = _require_non_empty_string(insight_id, "insight_id")
    new_settings_obj = _coerce_json_object(new_settings, "new_settings")

    await ctx.info(f"Replacing settings for insight {insight_id} in {project_key}...")

    def _run():
        insight = get_dss_client().get_project(project_key).get_insight(insight_id)
        settings = insight.get_settings()
        settings.settings = dict(new_settings_obj)
        settings.save()
        return insight.get_settings().get_raw()

    updated = await run_blocking(_run)
    return compact_json({"insight": updated})


@mcp.tool()
async def delete_insight(
    project_key: str,
    insight_id: str,
    ctx: Context,
) -> str:
    """Delete the insight."""
    project_key = _require_non_empty_string(project_key, "project_key")
    insight_id = _require_non_empty_string(insight_id, "insight_id")
    await ctx.info(f"Deleting insight {insight_id} in {project_key}...")

    await run_blocking(
        lambda: get_dss_client()
        .get_project(project_key)
        .get_insight(insight_id)
        .delete()
    )
    return compact_json({})
