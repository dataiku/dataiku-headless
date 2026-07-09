"""Clustering analysis creation and update."""

from __future__ import annotations

from typing import Optional

from fastmcp import Context

from ... import mcp
from ..utils.async_executor import run_blocking
from ..utils.serialization import compact_json, omit_empty
from ..utils.auth import get_dss_client
from ..utils.parsing import (
    parse_json_object as _parse_json_object,
    parse_non_empty_string_list as _parse_non_empty_string_list,
)
from ..utils.validation import (
    require_non_empty_string as _require_non_empty_string,
    require_positive_int as _require_positive_int,
)
from .shared.common import (
    build_created_ml_task_response,
    find_analysis_input_dataset,
    require_single_ml_task as _require_single_ml_task,
    set_analysis_name,
)
from .shared.settings import (
    apply_algorithm_selection,
    apply_algorithm_settings_patch,
    apply_env_selection,
    apply_feature_preprocessing_patch,
    apply_feature_selection,
)
from .shared.summaries import build_ml_task_summary


def apply_cluster_count(
    settings, algorithms: list[str] | None, n_clusters: int | None
) -> None:
    if n_clusters is None:
        return

    selected_algorithms = algorithms or settings.get_enabled_algorithm_names()
    for algorithm_name in selected_algorithms:
        algorithm_settings = settings.get_algorithm_settings(algorithm_name)
        if "n_clusters" in algorithm_settings:
            algorithm_settings["n_clusters"] = n_clusters
        elif "k" in algorithm_settings:
            current_k = algorithm_settings["k"]
            if isinstance(current_k, list):
                algorithm_settings["k"] = [n_clusters]
            else:
                algorithm_settings["k"] = n_clusters
        if "range" in algorithm_settings and {"min", "max", "nbValues"}.issubset(
            algorithm_settings["range"].keys()
        ):
            algorithm_settings["range"]["min"] = n_clusters
            algorithm_settings["range"]["max"] = n_clusters
            algorithm_settings["range"]["nbValues"] = 1


@mcp.tool()
async def create_clustering_analysis(
    project_key: str,
    input_dataset: str,
    ctx: Context,
    analysis_name: Optional[str] = None,
    ml_backend_type: str = "PY_MEMORY",
    guess_policy: str = "KMEANS",
) -> str:
    """Create a clustering analysis, wait for DSS guessing, and return created ids/metadata.

    Args:
        input_dataset: Training dataset name
        analysis_name: Visual analysis name (auto-generated if omitted)
        ml_backend_type: DSS ML backend type
        guess_policy: DSS guess policy
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    input_dataset = _require_non_empty_string(input_dataset, "input_dataset")
    ml_backend_type = _require_non_empty_string(ml_backend_type, "ml_backend_type")
    guess_policy = _require_non_empty_string(guess_policy, "guess_policy")
    if analysis_name is not None:
        analysis_name = _require_non_empty_string(analysis_name, "analysis_name")

    await ctx.info(
        f"Creating clustering analysis on dataset '{input_dataset}' and waiting for DSS guessing..."
    )

    def _configure():
        project = get_dss_client().get_project(project_key)
        mltask = project.create_clustering_ml_task(
            input_dataset=input_dataset,
            ml_backend_type=ml_backend_type,
            guess_policy=guess_policy,
            wait_guess_complete=True,
        )
        analysis = project.get_analysis(mltask.analysis_id)
        return build_created_ml_task_response(
            project_key=project_key,
            input_dataset=input_dataset,
            mltask=mltask,
            analysis=analysis,
            analysis_name=analysis_name,
        )

    result = await run_blocking(_configure)
    await ctx.report_progress(1, 1)
    # LEVER 3: drop input-echo fields (caller already has these request args).
    result.pop("project_key", None)
    result.pop("input_dataset", None)
    return compact_json(omit_empty({
            **result,
            "hint": (
                "Inspect raw guessed settings with get_ml_analysis_settings(); "
                "use get_ml_analysis_summary() for a normalized overview, then customize with "
                "update_clustering_analysis() and train with train_ml_analysis()."
            ),
        }))


@mcp.tool()
async def update_clustering_analysis(
    project_key: str,
    analysis_id: str,
    ctx: Context,
    analysis_name: Optional[str] = None,
    algorithms: Optional[str] = None,
    metric: Optional[str] = None,
    n_clusters: Optional[int] = None,
    included_features: Optional[str] = None,
    rejected_features: Optional[str] = None,
    algorithm_settings_patch: Optional[str] = None,
    feature_preprocessing_patch: Optional[str] = None,
    env_mode: Optional[str] = None,
    env_name: Optional[str] = None,
) -> str:
    """Update an existing clustering analysis in place.

    Args:
        analysis_id: Analysis ID from list_ml_analyses
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    analysis_id = _require_non_empty_string(analysis_id, "analysis_id")
    if analysis_name is not None:
        analysis_name = _require_non_empty_string(analysis_name, "analysis_name")

    algo_list = (
        _parse_non_empty_string_list(algorithms, "algorithms")
        if algorithms is not None
        else None
    )
    included_feature_list = (
        _parse_non_empty_string_list(included_features, "included_features")
        if included_features is not None
        else None
    )
    rejected_feature_list = (
        _parse_non_empty_string_list(rejected_features, "rejected_features")
        if rejected_features is not None
        else None
    )
    algorithm_settings_patch_obj = (
        _parse_json_object(algorithm_settings_patch, "algorithm_settings_patch")
        if algorithm_settings_patch is not None
        else None
    )
    feature_preprocessing_patch_obj = (
        _parse_json_object(feature_preprocessing_patch, "feature_preprocessing_patch")
        if feature_preprocessing_patch is not None
        else None
    )
    if n_clusters is not None:
        n_clusters = _require_positive_int(n_clusters, "n_clusters")

    if (
        analysis_name is None
        and algo_list is None
        and metric is None
        and n_clusters is None
        and included_feature_list is None
        and rejected_feature_list is None
        and algorithm_settings_patch_obj is None
        and feature_preprocessing_patch_obj is None
        and env_mode is None
    ):
        raise ValueError("Provide at least one setting to update.")

    await ctx.info(f"Updating clustering analysis {analysis_id}...")

    def _update():
        project = get_dss_client().get_project(project_key)
        analysis = project.get_analysis(analysis_id)
        task_ref = _require_single_ml_task(analysis)
        mltask_id = task_ref["mlTaskId"]
        set_analysis_name(analysis, analysis_name)
        mltask = analysis.get_ml_task(mltask_id)
        settings = mltask.get_settings()
        raw_settings = settings.get_raw()

        if raw_settings.get("taskType") != "CLUSTERING":
            raise ValueError(
                f"ML task '{mltask_id}' is '{raw_settings.get('taskType')}', not a clustering task."
            )

        apply_algorithm_selection(settings, algo_list)
        if metric is not None:
            settings.set_metric(metric=metric)
        apply_cluster_count(settings, algo_list, n_clusters)
        apply_feature_selection(
            settings=settings,
            raw_settings=raw_settings,
            included_features=included_feature_list,
            rejected_features=rejected_feature_list,
        )
        if algorithm_settings_patch_obj is not None:
            apply_algorithm_settings_patch(settings, algorithm_settings_patch_obj)
        if feature_preprocessing_patch_obj is not None:
            apply_feature_preprocessing_patch(
                settings,
                raw_settings,
                feature_preprocessing_patch_obj,
            )

        apply_env_selection(raw_settings, env_mode, env_name)
        settings.save()
        updated_analysis_definition = analysis.get_definition().get_raw()
        return build_ml_task_summary(
            project_key=project_key,
            analysis_id=analysis_id,
            analysis_name=updated_analysis_definition.get("name"),
            input_dataset=find_analysis_input_dataset(project, analysis_id),
            mltask_id=mltask_id,
            mltask=mltask,
            settings=settings,
            include_feature_details=True,
            include_trained_models=False,
        )

    summary = await run_blocking(_update)
    # LEVER 3: drop input-echo fields (caller already has these request args).
    summary.pop("project_key", None)
    summary.pop("analysis_id", None)
    return compact_json(omit_empty(summary))
