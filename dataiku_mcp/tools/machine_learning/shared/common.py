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


def set_analysis_name(analysis, analysis_name: str | None) -> None:
    if not analysis_name:
        return
    definition = analysis.get_definition()
    raw_definition = definition.get_raw()
    raw_definition["name"] = analysis_name
    analysis.set_definition(raw_definition)


def build_created_analysis_response(
    *,
    project_key: str,
    analysis_id: str,
    analysis_name: str | None,
    input_dataset: str | None,
    mltask_id: str,
    task_type: str | None,
    target_column: str | None = None,
    prediction_type: str | None = None,
) -> dict:
    response = {
        "status": "created",
        "project_key": project_key,
        "analysis_id": analysis_id,
        "analysis_name": analysis_name,
        "input_dataset": input_dataset,
        "mltask_id": mltask_id,
        "task_type": task_type,
    }
    if target_column is not None:
        response["target_column"] = target_column
    if prediction_type is not None:
        response["prediction_type"] = prediction_type
    return response


def build_created_ml_task_response(
    *,
    project_key: str,
    input_dataset: str | None,
    mltask,
    analysis,
    analysis_name: str | None = None,
    include_target_column: bool = False,
    include_prediction_type: bool = False,
) -> dict:
    set_analysis_name(analysis, analysis_name)

    settings = mltask.get_settings()
    analysis_definition = analysis.get_definition().get_raw()
    raw_settings = settings.get_raw()

    return build_created_analysis_response(
        project_key=project_key,
        analysis_id=mltask.analysis_id,
        analysis_name=analysis_definition.get("name"),
        input_dataset=input_dataset,
        mltask_id=mltask.mltask_id,
        task_type=raw_settings.get("taskType"),
        target_column=(
            raw_settings.get("targetVariable") if include_target_column else None
        ),
        prediction_type=(
            raw_settings.get("predictionType") if include_prediction_type else None
        ),
    )
