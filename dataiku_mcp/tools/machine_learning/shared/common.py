"""Common analysis metadata helpers for machine learning tools."""

from __future__ import annotations


def require_single_ml_task(analysis) -> dict:
    tasks = analysis.list_ml_tasks().get("mlTasks", [])
    if len(tasks) != 1:
        raise ValueError(
            f"Expected exactly 1 ML task in analysis '{analysis.analysis_id}', found {len(tasks)}."
        )
    return tasks[0]


def find_analysis_input_dataset(project, analysis_id: str) -> str | None:
    for analysis_item in project.list_analyses():
        if analysis_item.get("analysisId") == analysis_id:
            return analysis_item.get("inputDataset")
    return None
