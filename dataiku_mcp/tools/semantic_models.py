"""Semantic model inspection for Dataiku DSS."""

from fastmcp import Context

from .. import mcp
from .utils.async_executor import run_blocking
from .utils.auth import get_dss_client
from .utils.serialization import columnar, compact_json
from .utils.validation import require_non_empty_string as _require_non_empty_string


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


@mcp.tool()
async def get_semantic_model_version_settings(
    project_key: str,
    semantic_model_id: str,
    version_id: str,
    ctx: Context,
) -> str:
    """Get the full settings of a semantic model version."""
    semantic_model_id = _require_non_empty_string(
        semantic_model_id, "semantic_model_id"
    )
    version_id = _require_non_empty_string(version_id, "version_id")
    await ctx.info(
        f"Fetching version {version_id} settings for semantic model "
        f"{semantic_model_id} in {project_key}..."
    )

    def _run():
        semantic_model = (
            get_dss_client()
            .get_project(project_key)
            .get_semantic_model(semantic_model_id)
        )
        raw = semantic_model.get_version(version_id).get_settings().get_raw()
        return {
            "semantic_model_id": semantic_model_id,
            "version_id": version_id,
            "settings": raw,
        }

    return compact_json(await run_blocking(_run))
