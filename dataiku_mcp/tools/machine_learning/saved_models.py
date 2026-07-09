"""Saved model listing and version management tools."""

from fastmcp import Context

from ... import mcp
from ..utils.async_executor import run_blocking
from ..utils.serialization import columnar, compact_json
from ..utils.auth import get_dss_client
from ..utils.validation import (
    require_non_empty_list as _require_non_empty_list,
    require_non_empty_string as _require_non_empty_string,
)


@mcp.tool()
async def list_saved_models(project_key: str, ctx: Context) -> str:
    """List the saved models in the project."""
    project_key = _require_non_empty_string(project_key, "project_key")

    raw_models = await run_blocking(
        lambda: get_dss_client().get_project(project_key).list_saved_models()
    )

    result = [
        {
            "id": m["id"],
            "name": m.get("name", ""),
            "type": m.get("type", ""),
            "miniTask": m.get("miniTask", {}).get("taskType", ""),
        }
        for m in raw_models
    ]
    return compact_json(columnar(result, ["id", "name", "type", "miniTask"]))


@mcp.tool()
async def delete_saved_model(
    project_key: str,
    model_id: str,
    ctx: Context,
) -> str:
    """Delete the saved model.

    Args:
        model_id: Saved model ID from list_saved_models
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    model_id = _require_non_empty_string(model_id, "model_id")

    await ctx.info(f"Deleting saved model '{model_id}' in {project_key}...")
    await run_blocking(
        lambda: (
            get_dss_client().get_project(project_key).get_saved_model(model_id).delete()
        )
    )
    return compact_json({})


@mcp.tool()
async def list_saved_model_versions(
    project_key: str,
    model_id: str,
    ctx: Context,
) -> str:
    """List the versions of a saved model with their IDs, active status, and metadata.

    Args:
        model_id: Saved model ID from list_saved_models
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    model_id = _require_non_empty_string(model_id, "model_id")
    await ctx.info(f"Listing versions for saved model {model_id} in {project_key}...")

    versions = await run_blocking(
        lambda: (
            get_dss_client()
            .get_project(project_key)
            .get_saved_model(model_id)
            .list_versions()
        )
    )
    return compact_json(
        {
            "versions": versions,
        }
    )


@mcp.tool()
async def set_active_model_version(
    project_key: str,
    model_id: str,
    version_id: str,
    ctx: Context,
) -> str:
    """Set a specific version of a saved model as the active version.

    Args:
        model_id: Saved model ID from list_saved_models
        version_id: Version ID from list_saved_model_versions
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    model_id = _require_non_empty_string(model_id, "model_id")
    version_id = _require_non_empty_string(version_id, "version_id")
    await ctx.info(
        f"Setting version {version_id} as active for saved model {model_id} in {project_key}..."
    )

    await run_blocking(
        lambda: (
            get_dss_client()
            .get_project(project_key)
            .get_saved_model(model_id)
            .set_active_version(version_id)
        )
    )
    return compact_json({})


@mcp.tool()
async def delete_model_versions(
    project_key: str,
    model_id: str,
    version_ids: list,
    ctx: Context,
    remove_intermediate: bool = True,
) -> str:
    """Delete one or more versions of a saved model.

    Args:
        model_id: Saved model ID from list_saved_models
        version_ids: Version IDs to delete (from list_saved_model_versions)
        remove_intermediate: Also remove intermediate versions created during partitioned model training
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    model_id = _require_non_empty_string(model_id, "model_id")
    version_ids = _require_non_empty_list(version_ids, "version_ids")
    version_ids = [
        _require_non_empty_string(version_id, f"version_ids[{i}]")
        for i, version_id in enumerate(version_ids)
    ]

    await ctx.info(
        f"Deleting {len(version_ids)} version(s) from saved model {model_id} in {project_key}..."
    )

    await run_blocking(
        lambda: (
            get_dss_client()
            .get_project(project_key)
            .get_saved_model(model_id)
            .delete_versions(version_ids, remove_intermediate=remove_intermediate)
        )
    )
    return compact_json({})


@mcp.tool()
async def get_saved_model_version_details(
    project_key: str,
    model_id: str,
    version_id: str,
    ctx: Context,
) -> str:
    """Get the snippet for a saved model version: algorithm, performance metrics, hyperparameters, feature importances, ML diagnostics, and train/test row counts. Same shape as get_ml_model_details but for a flow saved model version.

    Args:
        model_id: Saved model ID from list_saved_models
        version_id: Version ID from list_saved_model_versions
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    model_id = _require_non_empty_string(model_id, "model_id")
    version_id = _require_non_empty_string(version_id, "version_id")
    await ctx.info(
        f"Fetching details for version {version_id} of saved model {model_id} in {project_key}..."
    )

    def _run():
        details = (
            get_dss_client()
            .get_project(project_key)
            .get_saved_model(model_id)
            .get_version_details(version_id)
        )
        return {
            "details_class": details.__class__.__name__,
            "snippet": details.get_raw_snippet(),
        }

    return compact_json(await run_blocking(_run))
