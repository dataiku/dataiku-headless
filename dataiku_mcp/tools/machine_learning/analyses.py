"""Inspection tools for generic ML analyses and trained models."""

from __future__ import annotations

from typing import Any

from fastmcp import Context

from ... import mcp
from ..utils.async_executor import run_blocking
from ..utils.auth import get_dss_client
from ..utils.serialization import columnar, compact_json
from ..utils.validation import require_non_empty_string as _require_non_empty_string
from .shared.common import find_analysis_input_dataset, require_single_ml_task
from .shared.summaries import build_ml_task_summary


def get_single_task_bundle(project_key: str, analysis_id: str):
    project = get_dss_client().get_project(project_key)
    analysis = project.get_analysis(analysis_id)
    task_ref = require_single_ml_task(analysis)
    mltask_id = task_ref["mlTaskId"]
    mltask = analysis.get_ml_task(mltask_id)
    return project, analysis, mltask_id, mltask


def slim_model_data(data: Any) -> Any:
    if isinstance(data, dict):
        return {
            key: slim_model_data(value)
            for key, value in data.items()
            if not key.endswith("PerFeature")
        }
    if isinstance(data, list):
        return [slim_model_data(item) for item in data]
    return data


@mcp.tool()
async def list_ml_analyses(
    project_key: str,
    ctx: Context,
    input_dataset: str | None = None,
) -> str:
    """List the ML analyses in the project with their single-task summaries."""
    project_key = _require_non_empty_string(project_key, "project_key")
    if input_dataset is not None:
        input_dataset = _require_non_empty_string(input_dataset, "input_dataset")
    await ctx.info(f"Listing ML analyses in {project_key}...")

    def _list() -> dict[str, Any]:
        project = get_dss_client().get_project(project_key)
        analyses = []
        for analysis_item in project.list_analyses():
            if input_dataset and analysis_item.get("inputDataset") != input_dataset:
                continue
            analysis_id = analysis_item["analysisId"]
            analysis = project.get_analysis(analysis_id)
            analysis_definition = analysis.get_definition().get_raw()
            task_ref = require_single_ml_task(analysis)
            mltask_id = task_ref["mlTaskId"]
            mltask = analysis.get_ml_task(mltask_id)
            settings = mltask.get_settings()
            analyses.append(
                build_ml_task_summary(
                    project_key=project_key,
                    analysis_id=analysis_id,
                    analysis_name=analysis_definition.get("name"),
                    input_dataset=analysis_item.get("inputDataset"),
                    mltask_id=mltask_id,
                    mltask=mltask,
                    settings=settings,
                    include_feature_details=False,
                    include_trained_models=False,
                )
            )
        return {
            "analyses": columnar(
                analyses,
                [
                    "analysis_id",
                    "analysis_name",
                    "input_dataset",
                    "mltask_id",
                    "task_type",
                    "prediction_type",
                    "target_column",
                    "backend_type",
                    "metric",
                    "metric_details",
                    "enabled_algorithms",
                    "guessing",
                    "training",
                    "trained_model_count",
                    "split",
                    "hyperparameter_search",
                    "weighting",
                    "diagnostics",
                    "feature_role_counts",
                    "features",
                ],
            )
        }

    return compact_json(await run_blocking(_list))


@mcp.tool()
async def get_ml_analysis_summary(
    project_key: str,
    analysis_id: str,
    ctx: Context,
) -> str:
    """Get the normalized single-task summary for an ML analysis."""
    project_key = _require_non_empty_string(project_key, "project_key")
    analysis_id = _require_non_empty_string(analysis_id, "analysis_id")
    await ctx.info(f"Loading ML analysis summary for {analysis_id}...")

    def _get() -> dict[str, Any]:
        project, analysis, mltask_id, mltask = get_single_task_bundle(
            project_key, analysis_id
        )
        analysis_definition = analysis.get_definition().get_raw()
        settings = mltask.get_settings()
        return build_ml_task_summary(
            project_key=project_key,
            analysis_id=analysis_id,
            analysis_name=analysis_definition.get("name"),
            input_dataset=find_analysis_input_dataset(project, analysis_id),
            mltask_id=mltask_id,
            mltask=mltask,
            settings=settings,
            include_feature_details=True,
            include_trained_models=False,
        )

    return compact_json(await run_blocking(_get))


@mcp.tool()
async def list_ml_analysis_models(
    project_key: str,
    analysis_id: str,
    ctx: Context,
) -> str:
    """List the trained models for the single ML task in an analysis."""
    project_key = _require_non_empty_string(project_key, "project_key")
    analysis_id = _require_non_empty_string(analysis_id, "analysis_id")
    await ctx.info(f"Listing trained models for ML analysis {analysis_id}...")

    def _list() -> dict[str, Any]:
        _, _, mltask_id, mltask = get_single_task_bundle(project_key, analysis_id)
        trained_model_ids = mltask.get_trained_models_ids()
        snippets = (
            mltask.get_trained_model_snippet(ids=trained_model_ids)
            if trained_model_ids
            else {}
        )
        models = []
        for trained_model_id in trained_model_ids:
            snippet = snippets.get(trained_model_id, {})
            models.append(
                {"trained_model_id": trained_model_id, "snippet": slim_model_data(snippet)}
            )
        return {
            "mltask_id": mltask_id,
            "models": columnar(models, ["trained_model_id", "snippet"]),
        }

    return compact_json(await run_blocking(_list))


@mcp.tool()
async def get_ml_model_details(
    project_key: str,
    analysis_id: str,
    trained_model_id: str,
    ctx: Context,
) -> str:
    """Get the snippet for a trained model."""
    project_key = _require_non_empty_string(project_key, "project_key")
    analysis_id = _require_non_empty_string(analysis_id, "analysis_id")
    trained_model_id = _require_non_empty_string(trained_model_id, "trained_model_id")
    await ctx.info(
        f"Loading trained model {trained_model_id} from analysis {analysis_id}..."
    )

    def _get() -> dict[str, Any]:
        _, _, mltask_id, mltask = get_single_task_bundle(project_key, analysis_id)
        details = mltask.get_trained_model_details(trained_model_id)
        return {
            "mltask_id": mltask_id,
            "full_model_id": details.full_id,
            "details_class": details.__class__.__name__,
            "snippet": details.get_raw_snippet(),
        }

    return compact_json(await run_blocking(_get))
