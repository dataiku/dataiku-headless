"""Training helpers for machine learning tools."""

from __future__ import annotations

from typing import Any

from ...utils.auth import get_dss_client
from .summaries import summarize_trained_models


def train_models(
    project_key: str,
    analysis_id: str,
    mltask_id: str,
    session_name: str | None,
    session_description: str | None,
    run_queue: bool,
) -> list[dict[str, Any]]:
    project = get_dss_client().get_project(project_key)
    mltask = project.get_analysis(analysis_id).get_ml_task(mltask_id)
    trained_model_ids = mltask.train(
        session_name=session_name,
        session_description=session_description,
        run_queue=run_queue,
    )
    return summarize_trained_models(mltask, trained_model_ids)
