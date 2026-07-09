"""Tools for managing Dataiku DSS Evaluation Stores."""

from dataikuapi.utils import DataikuException
from fastmcp import Context

from .. import mcp
from .utils.async_executor import run_blocking
from .utils.serialization import columnar, compact_json
from .utils.auth import get_dss_client
from .utils.validation import require_non_empty_string, require_allowed_value


@mcp.tool()
async def create_evaluation_store(
    project_key: str,
    name: str,
    ctx: Context,
    flavor: str = "TABULAR",
) -> str:
    """Create a new Model Evaluation Store in the project.

    Args:
        name: Display name for the evaluation store
        flavor: "TABULAR" (default), "AGENT", or "LLM" — must match the recipe type that writes to it
    """
    project_key = require_non_empty_string(project_key, "project_key")
    name = require_non_empty_string(name, "name")
    flavor = require_allowed_value(flavor, "flavor", {"TABULAR", "AGENT", "LLM"})
    await ctx.info(f"Creating {flavor} evaluation store '{name}' in {project_key}...")

    def _run():
        project = get_dss_client().get_project(project_key)
        store = project.create_evaluation_store(name, flavor=flavor)
        return {"evaluation_store_id": store.id, "name": name, "flavor": flavor}

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def get_evaluation_store_details(
    project_key: str,
    evaluation_store_id: str,
    ctx: Context,
) -> str:
    """Get metadata and evaluation history for a Model Evaluation Store.

    Returns store name and flavor, plus a list of evaluations (newest first) with
    their IDs, names, labels, prediction type, target variable, and scalar performance metrics.

    Args:
        evaluation_store_id: ID of the evaluation store (e.g. "Fa3t8F9A")
    """
    project_key = require_non_empty_string(project_key, "project_key")
    evaluation_store_id = require_non_empty_string(evaluation_store_id, "evaluation_store_id")
    await ctx.info(f"Getting evaluation store {evaluation_store_id} in {project_key}...")

    def _run():
        project = get_dss_client().get_project(project_key)
        try:
            store = project.get_model_evaluation_store(evaluation_store_id)
            store_settings = store.get_settings().settings
        except DataikuException as e:
            raise ValueError(f"Evaluation store '{evaluation_store_id}' not found in project '{project_key}': {e}") from e

        evaluations = []
        for ev in store.list_evaluations():
            try:
                info = ev.get_full_info()
                evaluations.append({
                    "evaluation_id": ev.evaluation_id,
                    "name": info.user_meta.get("name", ""),
                    "labels": info.user_meta.get("labels", []),
                    "created": info.creation_date,
                    "prediction_type": info.prediction_type,
                    "target_variable": info.target_variable,
                    "prediction_variable": info.prediction_variable,
                    "metrics": info.metrics,
                })
            except Exception as e:
                evaluations.append({"evaluation_id": ev.evaluation_id, "error": str(e)})

        evaluations.sort(key=lambda e: e.get("created") or 0, reverse=True)

        return {
            "evaluation_store_id": evaluation_store_id,
            "name": store_settings.get("name", ""),
            "flavor": store_settings.get("mesFlavor", ""),
            "evaluations": evaluations,
        }

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def list_evaluation_stores(
    project_key: str,
    flavor: str,
    ctx: Context,
) -> str:
    """List the Evaluation Stores in the project with their IDs, names, flavors, and evaluation counts.

    Args:
        flavor: "TABULAR", "AGENT", or "LLM"
    """
    project_key = require_non_empty_string(project_key, "project_key")
    flavor = require_allowed_value(flavor, "flavor", {"TABULAR", "AGENT", "LLM"})
    await ctx.info(f"Listing {flavor} evaluation stores in {project_key}...")

    def _run():
        project = get_dss_client().get_project(project_key)
        stores = project.list_evaluation_stores(flavor=flavor)
        result = []
        for store in stores:
            try:
                settings = store.get_settings().settings
                result.append({
                    "evaluation_store_id": store.id,
                    "name": settings.get("name", ""),
                    "flavor": settings.get("mesFlavor", ""),
                    "evaluation_count": len(store.list_evaluations()),
                })
            except DataikuException as e:
                result.append({"evaluation_store_id": store.id, "error": str(e)})
        return columnar(result, ["evaluation_store_id", "name", "flavor", "evaluation_count", "error"])

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def delete_evaluation_store(
    project_key: str,
    evaluation_store_id: str,
    ctx: Context,
) -> str:
    """Delete a Model Evaluation Store from the project.

    Args:
        evaluation_store_id: ID of the evaluation store to delete (e.g. "Fa3t8F9A")
    """
    project_key = require_non_empty_string(project_key, "project_key")
    evaluation_store_id = require_non_empty_string(evaluation_store_id, "evaluation_store_id")
    await ctx.info(f"Deleting evaluation store {evaluation_store_id} in {project_key}...")

    def _run():
        try:
            get_dss_client().get_project(project_key).get_model_evaluation_store(evaluation_store_id).delete()
        except DataikuException as e:
            raise ValueError(f"Evaluation store '{evaluation_store_id}' not found in project '{project_key}': {e}") from e
        return {}

    return compact_json(await run_blocking(_run))
