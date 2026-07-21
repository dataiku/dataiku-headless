"""Data Collections — instance-wide curated catalog of datasets."""

from fastmcp import Context

from .. import mcp
from .utils.async_executor import run_blocking
from .utils.serialization import bounded_compact_json, columnar, compact_json
from .utils.auth import get_dss_client
from .utils.validation import (
    require_non_empty_string as _require_non_empty_string,
    require_positive_int as _require_positive_int,
)


_DEFAULT_OBJECTS = 200
_MAX_OBJECTS = 1_000
_MAX_OBJECT_RESPONSE_BYTES = 1_000_000


def _bounded_max_items(value: int) -> int:
    value = _require_positive_int(value, "max_items")
    if value > _MAX_OBJECTS:
        raise ValueError(f"'max_items' must be <= {_MAX_OBJECTS}")
    return value


@mcp.tool()
async def list_data_collections(ctx: Context) -> str:
    """List the Data Collections accessible on the instance."""
    await ctx.info("Listing data collections...")

    def _run():
        return [
            {"id": dc.id, "name": dc.display_name, "description": dc.description,
             "tags": dc.tags, "item_count": dc.item_count}
            for dc in get_dss_client().list_data_collections()
        ]

    return compact_json(columnar(await run_blocking(_run), ["id", "name", "description", "tags", "item_count"]))


@mcp.tool()
async def list_data_collection_objects(
    collection_id: str,
    ctx: Context,
    max_items: int = _DEFAULT_OBJECTS,
) -> str:
    """List a bounded stable-identity summary of Data Collection objects.

    Projects each object to its stable identity (type, project_key, id) and caps
    the rows at ``max_items``. Both ``max_items`` and the response byte ceiling
    bound the *response*, not the upstream server fetch: DSS still returns the
    full object list, which this tool truncates before serializing.
    """
    collection_id = _require_non_empty_string(collection_id, "collection_id")
    max_items = _bounded_max_items(max_items)
    await ctx.info(
        f"Listing objects in collection {collection_id} (max_items={max_items})..."
    )

    def _run():
        items = (
            get_dss_client()
            .get_data_collection(collection_id)
            .list_objects(as_type="dict")
        )
        rows = [
            {
                "type": item.get("type"),
                "project_key": item.get("projectKey"),
                "id": item.get("id"),
            }
            for item in items[:max_items]
        ]
        return {
            "collection_id": collection_id,
            "objects": columnar(rows, ["type", "project_key", "id"]),
            "returned_items": len(rows),
            "total_items": len(items),
            "truncated": len(items) > max_items,
        }

    return bounded_compact_json(await run_blocking(_run), _MAX_OBJECT_RESPONSE_BYTES)
