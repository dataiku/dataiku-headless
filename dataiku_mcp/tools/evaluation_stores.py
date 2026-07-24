"""Inspection tools for Dataiku DSS Evaluation Stores."""

from dataikuapi.utils import DataikuException
from fastmcp import Context

from .. import mcp
from .utils.async_executor import run_blocking
from .utils.auth import get_dss_client
from .utils.serialization import columnar, compact_json
from .utils.validation import (
    require_allowed_value,
    require_non_empty_string,
)


@mcp.tool()
async def get_evaluation_store_details(
    project_key: str,
    evaluation_store_id: str,
    ctx: Context,
) -> str:
    """Get metadata and evaluation history for a Model Evaluation Store."""
    project_key = require_non_empty_string(project_key, "project_key")
    evaluation_store_id = require_non_empty_string(
        evaluation_store_id, "evaluation_store_id"
    )
    await ctx.info(
        f"Getting evaluation store {evaluation_store_id} in {project_key}..."
    )

    def _run():
        project = get_dss_client().get_project(project_key)
        try:
            store = project.get_model_evaluation_store(evaluation_store_id)
            store_settings = store.get_settings().settings
        except DataikuException as exc:
            raise ValueError(
                f"Evaluation store '{evaluation_store_id}' not found in project "
                f"'{project_key}': {exc}"
            ) from exc

        evaluations = []
        for evaluation in store.list_evaluations():
            try:
                info = evaluation.get_full_info()
                evaluations.append(
                    {
                        "evaluation_id": evaluation.evaluation_id,
                        "name": info.user_meta.get("name", ""),
                        "labels": info.user_meta.get("labels", []),
                        "created": info.creation_date,
                        "prediction_type": info.prediction_type,
                        "target_variable": info.target_variable,
                        "prediction_variable": info.prediction_variable,
                        "metrics": info.metrics,
                    }
                )
            except Exception as exc:
                evaluations.append(
                    {"evaluation_id": evaluation.evaluation_id, "error": str(exc)}
                )

        evaluations.sort(key=lambda item: item.get("created") or 0, reverse=True)
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
    """List the Evaluation Stores in the project with IDs, names, flavors, and evaluation counts."""
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
                result.append(
                    {
                        "evaluation_store_id": store.id,
                        "name": settings.get("name", ""),
                        "flavor": settings.get("mesFlavor", ""),
                        "evaluation_count": len(store.list_evaluations()),
                    }
                )
            except DataikuException as exc:
                result.append({"evaluation_store_id": store.id, "error": str(exc)})
        return columnar(
            result,
            ["evaluation_store_id", "name", "flavor", "evaluation_count", "error"],
        )

    return compact_json(await run_blocking(_run))
