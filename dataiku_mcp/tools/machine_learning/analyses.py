"""Inspection tools for generic ML analyses."""

from __future__ import annotations

from typing import Any

from fastmcp import Context

from ... import mcp
from ..utils.async_executor import run_blocking
from ..utils.auth import get_dss_client
from ..utils.serialization import columnar, compact_json
from ..utils.validation import require_non_empty_string as _require_non_empty_string
from .shared.common import require_single_ml_task
from .shared.summaries import build_ml_task_summary


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
                ],
            )
        }

    return compact_json(await run_blocking(_list))
