"""Semantic model operations for Dataiku DSS."""

from fastmcp import Context

from .. import mcp
from .utils.async_executor import run_blocking
from .utils.serialization import columnar, compact_json, omit_empty
from .utils.auth import get_dss_client
from .utils.parsing import coerce_json_object as _coerce_json_object
from .utils.validation import require_non_empty_string as _require_non_empty_string


@mcp.tool()
async def list_semantic_models(project_key: str, ctx: Context) -> str:
    """List the semantic models in the project with their IDs, names, active version, and all version IDs."""
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
                    "version_ids": [v.get("id") for v in versions],
                }
            )
        return {
            "semantic_models": columnar(
                result,
                ["id", "name", "activeVersionId", "version_ids"],
            ),
        }

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def get_semantic_model_version_settings(
    project_key: str,
    semantic_model_id: str,
    version_id: str,
    ctx: Context,
) -> str:
    """Get the full settings of a semantic model version: entities, relationships, glossary terms, and golden queries.

    Args:
        semantic_model_id: Semantic model ID from list_semantic_models
        version_id: Version ID from list_semantic_models (e.g. "v1")
    """
    semantic_model_id = _require_non_empty_string(semantic_model_id, "semantic_model_id")
    version_id = _require_non_empty_string(version_id, "version_id")
    await ctx.info(
        f"Fetching version {version_id} settings for semantic model {semantic_model_id} in {project_key}..."
    )

    def _run():
        sm = get_dss_client().get_project(project_key).get_semantic_model(semantic_model_id)
        raw = sm.get_version(version_id).get_settings().get_raw()
        return {
            "semantic_model_id": semantic_model_id,
            "version_id": version_id,
            "settings": raw,
        }

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def create_semantic_model(
    project_key: str,
    name: str,
    ctx: Context,
) -> str:
    """Create a new semantic model in the project.

    Args:
        name: Display name for the new semantic model
    """
    name = _require_non_empty_string(name, "name")
    await ctx.info(f"Creating semantic model '{name}' in {project_key}...")

    def _run():
        sm = get_dss_client().get_project(project_key).create_semantic_model(name)
        return {
            "semantic_model_id": sm.id,
            "name": name,
        }

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def delete_semantic_model(
    project_key: str,
    semantic_model_id: str,
    ctx: Context,
) -> str:
    """Delete a semantic model.

    Args:
        semantic_model_id: Semantic model ID from list_semantic_models
    """
    semantic_model_id = _require_non_empty_string(semantic_model_id, "semantic_model_id")
    await ctx.info(f"Deleting semantic model {semantic_model_id} in {project_key}...")

    await run_blocking(
        lambda: get_dss_client()
        .get_project(project_key)
        .get_semantic_model(semantic_model_id)
        .delete()
    )
    return compact_json(
        {
            "semantic_model_id": semantic_model_id,
        }
    )


@mcp.tool()
async def set_semantic_model_active_version(
    project_key: str,
    semantic_model_id: str,
    version_id: str,
    ctx: Context,
) -> str:
    """Set the active version of a semantic model.

    Args:
        semantic_model_id: Semantic model ID from list_semantic_models
        version_id: Version ID from list_semantic_models
    """
    semantic_model_id = _require_non_empty_string(semantic_model_id, "semantic_model_id")
    version_id = _require_non_empty_string(version_id, "version_id")
    await ctx.info(
        f"Setting active version to {version_id} for semantic model {semantic_model_id} in {project_key}..."
    )

    await run_blocking(
        lambda: get_dss_client()
        .get_project(project_key)
        .get_semantic_model(semantic_model_id)
        .set_active_version_id(version_id)
    )
    return compact_json(
        {
            "semantic_model_id": semantic_model_id,
            "activeVersionId": version_id,
        }
    )


@mcp.tool()
async def create_semantic_model_version(
    project_key: str,
    semantic_model_id: str,
    version_id: str,
    ctx: Context,
    duplicate_of: str | None = None,
) -> str:
    """Create a new version of a semantic model.

    Args:
        semantic_model_id: Semantic model ID from list_semantic_models
        version_id: Identifier for the new version (e.g. "v2")
        duplicate_of: Optional version ID to copy settings from; omit for an empty version
    """
    semantic_model_id = _require_non_empty_string(semantic_model_id, "semantic_model_id")
    version_id = _require_non_empty_string(version_id, "version_id")
    await ctx.info(
        f"Creating version '{version_id}' for semantic model {semantic_model_id} in {project_key}"
        + (f" (duplicating {duplicate_of})" if duplicate_of else "")
        + "..."
    )

    def _run():
        sm = get_dss_client().get_project(project_key).get_semantic_model(semantic_model_id)
        version_settings = sm.new_version(version_id, duplicate_of=duplicate_of)
        version_settings.save()
        result = {
            "semantic_model_id": semantic_model_id,
            "version_id": version_id,
        }
        return omit_empty(result)

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def set_semantic_model_version_settings(
    project_key: str,
    semantic_model_id: str,
    version_id: str,
    new_settings,
    ctx: Context,
) -> str:
    """Replace the full settings of a semantic model version (entities, relationships, glossary terms, golden queries).

    Args:
        semantic_model_id: Semantic model ID from list_semantic_models
        version_id: Version ID to update (from list_semantic_models)
        new_settings: A modified version of the object returned by get_semantic_model_version_settings["settings"]
    """
    semantic_model_id = _require_non_empty_string(semantic_model_id, "semantic_model_id")
    version_id = _require_non_empty_string(version_id, "version_id")
    settings_obj = _coerce_json_object(new_settings, "new_settings")

    await ctx.info(
        f"Updating version {version_id} settings for semantic model {semantic_model_id} in {project_key}..."
    )

    def _run():
        sm = get_dss_client().get_project(project_key).get_semantic_model(semantic_model_id)
        current = sm.get_version(version_id).get_settings()
        raw = current.get_raw()
        raw.clear()
        raw.update(settings_obj)
        current.save()
        return {
            "semantic_model_id": semantic_model_id,
            "version_id": version_id,
            "entity_count": len(raw.get("entities", [])),
            "relationship_count": len(raw.get("relationships", [])),
            "golden_query_count": len(raw.get("goldenQueries", [])),
            "glossary_term_count": len(raw.get("glossaryTerms", [])),
        }

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def update_semantic_model_distinct_values(
    project_key: str,
    semantic_model_id: str,
    version_id: str,
    ctx: Context,
) -> str:
    """Trigger and wait for a distinct-values index update on a semantic model version.

    Args:
        semantic_model_id: Semantic model ID from list_semantic_models
        version_id: Version ID to update (from list_semantic_models)
    """
    semantic_model_id = _require_non_empty_string(semantic_model_id, "semantic_model_id")
    version_id = _require_non_empty_string(version_id, "version_id")
    await ctx.info(
        f"Starting distinct-values index update for version {version_id} of semantic model"
        f" {semantic_model_id} in {project_key}..."
    )

    def _run():
        sm = get_dss_client().get_project(project_key).get_semantic_model(semantic_model_id)
        future = sm.get_version(version_id).start_update_distinct_values()
        future.wait_for_result()
        return {
            "semantic_model_id": semantic_model_id,
            "version_id": version_id,
        }

    return compact_json(await run_blocking(_run))
