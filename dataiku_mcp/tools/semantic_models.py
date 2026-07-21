"""Semantic model inspection for Dataiku DSS."""

from fastmcp import Context

from .. import mcp
from .utils.async_executor import run_blocking
from .utils.auth import get_dss_client
from .utils.serialization import columnar, compact_json


@mcp.tool()
async def list_semantic_models(project_key: str, ctx: Context) -> str:
    """List semantic models with IDs, names, active version, and version IDs."""
    await ctx.info(f"Listing semantic models in {project_key}...")

    def _run():
        project = get_dss_client().get_project(project_key)
        items = project.list_semantic_models()
        result = []
        for item in items:
            raw = item._data
            versions = raw.get("versions", [])
            result.append(
                {
                    "id": item.id,
                    "name": item.name,
                    "activeVersionId": raw.get("activeVersionId"),
                    "version_ids": [version.get("id") for version in versions],
                }
            )
        return {
            "semantic_models": columnar(
                result,
                ["id", "name", "activeVersionId", "version_ids"],
            )
        }

    return compact_json(await run_blocking(_run))
