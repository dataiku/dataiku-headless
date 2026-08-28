"""Data Collections — instance-wide curated catalog of datasets."""

from fastmcp import Context

from ..server import mcp
from ..executors import run_blocking
from .utils.serialization import columnar, compact_json
from ..auth import get_dss_client
from .utils.validation import require_non_empty_string as _require_non_empty_string


@mcp.tool()
async def list_data_collections(ctx: Context) -> str:
    """List the Data Collections accessible on the instance."""
    await ctx.info("Listing data collections...")

    def _run():
        return [
            {
                "id": dc.id,
                "name": dc.display_name,
                "description": dc.description,
                "tags": dc.tags,
                "item_count": dc.item_count,
            }
            for dc in get_dss_client().list_data_collections()
        ]

    return compact_json(
        columnar(
            await run_blocking(_run),
            ["id", "name", "description", "tags", "item_count"],
        )
    )


@mcp.tool()
async def list_data_collection_objects(collection_id: str, ctx: Context) -> str:
    """List the objects in a Data Collection."""
    collection_id = _require_non_empty_string(collection_id, "collection_id")
    await ctx.info(f"Listing objects in collection {collection_id}...")

    def _run():
        items = (
            get_dss_client()
            .get_data_collection(collection_id)
            .list_objects(as_type="dict")
        )
        for i in items:
            if "projectKey" in i:
                i["project_key"] = i.pop("projectKey")
        return items

    return compact_json(await run_blocking(_run))
