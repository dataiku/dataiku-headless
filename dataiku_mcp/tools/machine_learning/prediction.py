"""Prediction analysis discovery, configuration, training, and deployment."""

from __future__ import annotations

from typing import Any, Optional

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
    require_allowed_value as _require_allowed_value,
    require_fraction as _require_fraction,
    require_int_at_least as _require_int_at_least,
    require_non_empty_string as _require_non_empty_string,
    require_non_negative_int as _require_non_negative_int,
    require_positive_int as _require_positive_int,
)
from .shared.common import (
    build_created_ml_task_response,
    find_analysis_input_dataset,
    require_single_ml_task as _require_single_ml_task,
    set_analysis_name,
)
from .shared.constants import (
    FEATURE_REDUCTION_METHODS as _FEATURE_REDUCTION_METHODS,
    HYPERPARAMETER_SEARCH_STRATEGIES as _HYPERPARAMETER_SEARCH_STRATEGIES,
    HYPERPARAMETER_SEARCH_VALIDATION_MODES as _HYPERPARAMETER_SEARCH_VALIDATION_MODES,
    PREDICTION_SPLIT_METHODS as _PREDICTION_SPLIT_METHODS,
    PREDICTION_TYPES as _PREDICTION_TYPES,
    WEIGHTING_METHODS as _WEIGHTING_METHODS,
)
from .shared.settings import (
    apply_algorithm_selection,
    apply_algorithm_settings_patch,
    apply_custom_metric,
    apply_diagnostics_settings,
    apply_env_selection,
    apply_feature_preprocessing_patch,
    apply_feature_reduction_settings,
    apply_feature_selection,
    apply_hyperparameter_search_settings,
    apply_split_settings,
    validate_feature_names,
)
from .shared.summaries import build_ml_task_summary

def apply_prediction_settings(
    *,
    settings,
    algorithms: list[str] | None,
    split_method: str | None,
    metric: str | None,
    custom_metric_code: str | None,
    custom_metric_name: str | None,
    custom_metric_greater_is_better: bool,
    custom_metric_use_probabilities: bool,
    train_ratio: float | None,
    n_folds: int | None,
    stratified: bool | None,
    time_ordering_feature: str | None,
    time_ordering_ascending: bool,
    disable_time_ordering: bool,
    split_seed: int | None,
    included_features: list[str] | None,
    rejected_features: list[str] | None,
    weighting_method: str | None,
    weighting_feature: str | None,
    search_strategy: str | None,
    search_randomize_grid: bool | None,
    search_seed: int | None,
    search_n_iter: int | None,
    search_timeout: int | None,
    search_parallelism: int | None,
    search_distributed: bool | None,
    search_n_containers: int | None,
    search_validation_mode: str | None,
    search_validation_ratio: float | None,
    search_n_folds: int | None,
    search_stratified: bool | None,
    search_cv_seed: int | None,
    custom_search_validation_code: str | None,
    diagnostics_enabled: bool | None,
    diagnostic_type_overrides: dict[str, bool] | None,
    algorithm_settings_patch: dict[str, Any] | None,
    feature_preprocessing_patch: dict[str, Any] | None,
    feature_reduction_method: str | None,
    feature_reduction_n_features: int | None,
    feature_reduction_variance_proportion: float | None,
    env_mode: str | None = None,
    env_name: str | None = None,
) -> dict[str, Any]:
    raw_settings = settings.get_raw()

    if weighting_feature and not weighting_method:
        raise ValueError(
            "'weighting_feature' requires 'weighting_method' to be set in the same call."
        )

    apply_algorithm_selection(settings, algorithms)

    prediction_type = raw_settings.get("predictionType")
    apply_custom_metric(
        settings=settings,
        prediction_type=prediction_type,
        metric=metric,
        custom_metric_code=custom_metric_code,
        custom_metric_name=custom_metric_name,
        custom_metric_greater_is_better=custom_metric_greater_is_better,
        custom_metric_use_probabilities=custom_metric_use_probabilities,
    )

    apply_split_settings(
        settings=settings,
        raw_settings=raw_settings,
        split_method=split_method,
        train_ratio=train_ratio,
        n_folds=n_folds,
        stratified=stratified,
        time_ordering_feature=time_ordering_feature,
        time_ordering_ascending=time_ordering_ascending,
        disable_time_ordering=disable_time_ordering,
        split_seed=split_seed,
    )

    apply_feature_selection(
        settings=settings,
        raw_settings=raw_settings,
        included_features=included_features,
        rejected_features=rejected_features,
        protected_roles={"TARGET"},
        protected_feature_names={
            raw_settings.get("targetVariable")
        }
        if raw_settings.get("targetVariable") is not None
        else set(),
    )

    if weighting_method is not None:
        if (
            weighting_method in {"SAMPLE_WEIGHT", "CLASS_AND_SAMPLE_WEIGHT"}
            and not weighting_feature
        ):
            raise ValueError(
                f"'weighting_feature' is required when weighting_method='{weighting_method}'."
            )
        if weighting_feature is not None:
            validate_feature_names(raw_settings, [weighting_feature], "weighting_feature")
        settings.set_weighting(method=weighting_method, feature_name=weighting_feature)

    apply_hyperparameter_search_settings(
        settings=settings,
        search_strategy=search_strategy,
        search_randomize_grid=search_randomize_grid,
        search_seed=search_seed,
        search_n_iter=search_n_iter,
        search_timeout=search_timeout,
        search_parallelism=search_parallelism,
        search_distributed=search_distributed,
        search_n_containers=search_n_containers,
        search_validation_mode=search_validation_mode,
        search_validation_ratio=search_validation_ratio,
        search_n_folds=search_n_folds,
        search_stratified=search_stratified,
        search_cv_seed=search_cv_seed,
        custom_search_validation_code=custom_search_validation_code,
    )
    apply_diagnostics_settings(
        settings=settings,
        diagnostics_enabled=diagnostics_enabled,
        diagnostic_type_overrides=diagnostic_type_overrides,
    )

    if algorithm_settings_patch is not None:
        apply_algorithm_settings_patch(settings, algorithm_settings_patch)

    if feature_preprocessing_patch is not None:
        apply_feature_preprocessing_patch(
            settings,
            raw_settings,
            feature_preprocessing_patch,
        )

    apply_feature_reduction_settings(
        raw_settings=raw_settings,
        feature_reduction_method=feature_reduction_method,
        feature_reduction_n_features=feature_reduction_n_features,
        feature_reduction_variance_proportion=feature_reduction_variance_proportion,
    )

    apply_env_selection(raw_settings, env_mode, env_name)

    settings.save()
    return raw_settings


@mcp.tool()
async def create_prediction_analysis(
    project_key: str,
    input_dataset: str,
    target_column: str,
    ctx: Context,
    analysis_name: Optional[str] = None,
    prediction_type: Optional[str] = None,
    ml_backend_type: str = "PY_MEMORY",
    guess_policy: str = "DEFAULT",
) -> str:
    """Create a prediction analysis, wait for DSS guessing, and return created ids/metadata.

    Args:
        input_dataset: Training dataset name
        target_column: Column to predict
        analysis_name: Visual analysis name (auto-generated if omitted)
        prediction_type: One of BINARY_CLASSIFICATION, REGRESSION, MULTICLASS (auto-detected if omitted)
        ml_backend_type: DSS ML backend type
        guess_policy: DSS guess policy
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    input_dataset = _require_non_empty_string(input_dataset, "input_dataset")
    target_column = _require_non_empty_string(target_column, "target_column")
    ml_backend_type = _require_non_empty_string(ml_backend_type, "ml_backend_type")
    guess_policy = _require_non_empty_string(guess_policy, "guess_policy")
    if analysis_name is not None:
        analysis_name = _require_non_empty_string(analysis_name, "analysis_name")

    if prediction_type is not None:
        prediction_type = _require_allowed_value(
            prediction_type,
            "prediction_type",
            _PREDICTION_TYPES,
        )

    await ctx.info(
        f"Creating prediction analysis for target '{target_column}' on dataset '{input_dataset}' and waiting for DSS guessing..."
    )

    def _configure():
        project = get_dss_client().get_project(project_key)
        mltask = project.create_prediction_ml_task(
            input_dataset=input_dataset,
            target_variable=target_column,
            ml_backend_type=ml_backend_type,
            guess_policy=guess_policy,
            prediction_type=prediction_type,
            wait_guess_complete=True,
        )
        analysis = project.get_analysis(mltask.analysis_id)
        return build_created_ml_task_response(
            project_key=project_key,
            input_dataset=input_dataset,
            mltask=mltask,
            analysis=analysis,
            analysis_name=analysis_name,
            include_target_column=True,
            include_prediction_type=True,
        )

    summary = await run_blocking(_configure)
    await ctx.report_progress(1, 1)

    # Drop pure input echoes (caller already has these args in context).
    summary.pop("project_key", None)
    summary.pop("input_dataset", None)

    return compact_json(omit_empty({
            **summary,
            "hint": (
                "Inspect raw guessed settings with get_ml_analysis_settings(); "
                "use get_ml_analysis_summary() for a normalized overview, then customize with "
                "update_prediction_analysis() and train with train_ml_analysis()."
            ),
        }))


@mcp.tool()
async def update_prediction_analysis(
    project_key: str,
    analysis_id: str,
    ctx: Context,
    analysis_name: Optional[str] = None,
    target_column: Optional[str] = None,
    prediction_type: Optional[str] = None,
    algorithms: Optional[str] = None,
    split_method: Optional[str] = None,
    metric: Optional[str] = None,
    custom_metric_code: Optional[str] = None,
    custom_metric_name: Optional[str] = None,
    custom_metric_greater_is_better: bool = True,
    custom_metric_use_probabilities: bool = False,
    train_ratio: Optional[float] = None,
    n_folds: Optional[int] = None,
    stratified: Optional[bool] = None,
    time_ordering_feature: Optional[str] = None,
    time_ordering_ascending: bool = True,
    disable_time_ordering: bool = False,
    split_seed: Optional[int] = None,
    weighting_method: Optional[str] = None,
    weighting_feature: Optional[str] = None,
    search_strategy: Optional[str] = None,
    search_randomize_grid: Optional[bool] = None,
    search_seed: Optional[int] = None,
    search_n_iter: Optional[int] = None,
    search_timeout: Optional[int] = None,
    search_parallelism: Optional[int] = None,
    search_distributed: Optional[bool] = None,
    search_n_containers: Optional[int] = None,
    search_validation_mode: Optional[str] = None,
    search_validation_ratio: Optional[float] = None,
    search_n_folds: Optional[int] = None,
    search_stratified: Optional[bool] = None,
    search_cv_seed: Optional[int] = None,
    custom_search_validation_code: Optional[str] = None,
    diagnostics_enabled: Optional[bool] = None,
    diagnostic_type_overrides: Optional[str] = None,
    included_features: Optional[str] = None,
    rejected_features: Optional[str] = None,
    algorithm_settings_patch: Optional[str] = None,
    feature_preprocessing_patch: Optional[str] = None,
    feature_reduction_method: Optional[str] = None,
    feature_reduction_n_features: Optional[int] = None,
    feature_reduction_variance_proportion: Optional[float] = None,
    env_mode: Optional[str] = None,
    env_name: Optional[str] = None,
    full_reguess: bool = False,
) -> str:
    """Update an existing prediction ML task in place.

    Args:
        analysis_id: Analysis ID from list_ml_analyses
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    analysis_id = _require_non_empty_string(analysis_id, "analysis_id")
    if analysis_name is not None:
        analysis_name = _require_non_empty_string(analysis_name, "analysis_name")
    if target_column is not None:
        target_column = _require_non_empty_string(target_column, "target_column")
    if weighting_feature is not None:
        weighting_feature = _require_non_empty_string(
            weighting_feature, "weighting_feature"
        )
    if time_ordering_feature is not None:
        time_ordering_feature = _require_non_empty_string(
            time_ordering_feature, "time_ordering_feature"
        )

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
    diagnostic_type_overrides_obj = (
        _parse_json_object(diagnostic_type_overrides, "diagnostic_type_overrides")
        if diagnostic_type_overrides is not None
        else None
    )

    if prediction_type is not None:
        prediction_type = _require_allowed_value(
            prediction_type,
            "prediction_type",
            _PREDICTION_TYPES,
        )
    if split_method is not None:
        split_method = _require_allowed_value(
            split_method,
            "split_method",
            _PREDICTION_SPLIT_METHODS,
        )
    if weighting_method is not None:
        weighting_method = _require_allowed_value(
            weighting_method,
            "weighting_method",
            _WEIGHTING_METHODS,
        )
    if search_strategy is not None:
        search_strategy = _require_allowed_value(
            search_strategy,
            "search_strategy",
            _HYPERPARAMETER_SEARCH_STRATEGIES,
        )
    if search_validation_mode is not None:
        search_validation_mode = _require_allowed_value(
            search_validation_mode,
            "search_validation_mode",
            _HYPERPARAMETER_SEARCH_VALIDATION_MODES,
        )
    if train_ratio is not None:
        train_ratio = _require_fraction(train_ratio, "train_ratio")
    if search_validation_ratio is not None:
        search_validation_ratio = _require_fraction(
            search_validation_ratio,
            "search_validation_ratio",
        )
    if n_folds is not None:
        n_folds = _require_int_at_least(n_folds, "n_folds", 2)
    if search_n_folds is not None:
        search_n_folds = _require_int_at_least(search_n_folds, "search_n_folds", 2)
    if split_seed is not None:
        split_seed = _require_positive_int(split_seed, "split_seed")
    if search_seed is not None:
        search_seed = _require_positive_int(search_seed, "search_seed")
    if search_n_iter is not None:
        search_n_iter = _require_positive_int(search_n_iter, "search_n_iter")
    if search_timeout is not None:
        search_timeout = _require_non_negative_int(search_timeout, "search_timeout")
    if search_parallelism is not None:
        search_parallelism = _require_positive_int(
            search_parallelism, "search_parallelism"
        )
    if search_n_containers is not None:
        search_n_containers = _require_positive_int(
            search_n_containers, "search_n_containers"
        )
    if search_cv_seed is not None:
        search_cv_seed = _require_positive_int(search_cv_seed, "search_cv_seed")
    if feature_reduction_method is not None:
        feature_reduction_method = _require_allowed_value(
            feature_reduction_method,
            "feature_reduction_method",
            _FEATURE_REDUCTION_METHODS,
        )
    if feature_reduction_n_features is not None:
        feature_reduction_n_features = _require_positive_int(
            feature_reduction_n_features, "feature_reduction_n_features"
        )
    if feature_reduction_variance_proportion is not None:
        feature_reduction_variance_proportion = _require_fraction(
            feature_reduction_variance_proportion,
            "feature_reduction_variance_proportion",
        )
    if disable_time_ordering and time_ordering_feature is not None:
        raise ValueError(
            "Use either 'time_ordering_feature' to set time ordering or 'disable_time_ordering=true' to unset it, not both."
        )
    if custom_metric_name is not None and custom_metric_code is None:
        raise ValueError(
            "'custom_metric_name' requires 'custom_metric_code' to be set in the same call."
        )
    if custom_search_validation_code is not None and search_validation_mode not in {
        None,
        "CUSTOM",
    }:
        raise ValueError(
            "'custom_search_validation_code' can only be used when search_validation_mode is 'CUSTOM'."
        )

    if (
        analysis_name is None
        and target_column is None
        and prediction_type is None
        and algo_list is None
        and split_method is None
        and metric is None
        and custom_metric_code is None
        and custom_metric_name is None
        and train_ratio is None
        and n_folds is None
        and stratified is None
        and time_ordering_feature is None
        and time_ordering_ascending is True
        and disable_time_ordering is False
        and split_seed is None
        and weighting_method is None
        and weighting_feature is None
        and search_strategy is None
        and search_randomize_grid is None
        and search_seed is None
        and search_n_iter is None
        and search_timeout is None
        and search_parallelism is None
        and search_distributed is None
        and search_n_containers is None
        and search_validation_mode is None
        and search_validation_ratio is None
        and search_n_folds is None
        and search_stratified is None
        and search_cv_seed is None
        and custom_search_validation_code is None
        and diagnostics_enabled is None
        and diagnostic_type_overrides_obj is None
        and included_feature_list is None
        and rejected_feature_list is None
        and algorithm_settings_patch_obj is None
        and feature_preprocessing_patch_obj is None
        and feature_reduction_method is None
        and feature_reduction_n_features is None
        and feature_reduction_variance_proportion is None
        and env_mode is None
    ):
        raise ValueError("Provide at least one setting to update.")

    await ctx.info(f"Updating prediction analysis {analysis_id}...")

    def _update() -> dict[str, Any]:
        project = get_dss_client().get_project(project_key)
        analysis = project.get_analysis(analysis_id)
        task_ref = _require_single_ml_task(analysis)
        mltask_id = task_ref["mlTaskId"]
        set_analysis_name(analysis, analysis_name)
        mltask = analysis.get_ml_task(mltask_id)

        settings = mltask.get_settings()
        raw_settings = settings.get_raw()
        if raw_settings.get("taskType") != "PREDICTION":
            raise ValueError(
                f"ML task '{mltask_id}' is '{raw_settings.get('taskType')}', not a prediction task."
            )

        guessed = False
        if target_column is not None and target_column != raw_settings.get(
            "targetVariable"
        ):
            mltask.guess(target_variable=target_column, full_reguess=full_reguess)
            mltask.wait_guess_complete()
            guessed = True
        if prediction_type is not None and prediction_type != raw_settings.get(
            "predictionType"
        ):
            mltask.guess(prediction_type=prediction_type, full_reguess=full_reguess)
            mltask.wait_guess_complete()
            guessed = True
        if full_reguess and not guessed:
            mltask.guess(full_reguess=True)
            mltask.wait_guess_complete()

        settings = mltask.get_settings()
        apply_prediction_settings(
            settings=settings,
            algorithms=algo_list,
            split_method=split_method,
            metric=metric,
            custom_metric_code=custom_metric_code,
            custom_metric_name=custom_metric_name,
            custom_metric_greater_is_better=custom_metric_greater_is_better,
            custom_metric_use_probabilities=custom_metric_use_probabilities,
            train_ratio=train_ratio,
            n_folds=n_folds,
            stratified=stratified,
            time_ordering_feature=time_ordering_feature,
            time_ordering_ascending=time_ordering_ascending,
            disable_time_ordering=disable_time_ordering,
            split_seed=split_seed,
            included_features=included_feature_list,
            rejected_features=rejected_feature_list,
            weighting_method=weighting_method,
            weighting_feature=weighting_feature,
            search_strategy=search_strategy,
            search_randomize_grid=search_randomize_grid,
            search_seed=search_seed,
            search_n_iter=search_n_iter,
            search_timeout=search_timeout,
            search_parallelism=search_parallelism,
            search_distributed=search_distributed,
            search_n_containers=search_n_containers,
            search_validation_mode=search_validation_mode,
            search_validation_ratio=search_validation_ratio,
            search_n_folds=search_n_folds,
            search_stratified=search_stratified,
            search_cv_seed=search_cv_seed,
            custom_search_validation_code=custom_search_validation_code,
            diagnostics_enabled=diagnostics_enabled,
            diagnostic_type_overrides=diagnostic_type_overrides_obj,
            algorithm_settings_patch=algorithm_settings_patch_obj,
            feature_preprocessing_patch=feature_preprocessing_patch_obj,
            feature_reduction_method=feature_reduction_method,
            feature_reduction_n_features=feature_reduction_n_features,
            feature_reduction_variance_proportion=feature_reduction_variance_proportion,
            env_mode=env_mode,
            env_name=env_name,
        )

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
    # Drop pure input echoes (caller already has these args in context).
    summary.pop("project_key", None)
    summary.pop("analysis_id", None)
    return compact_json(omit_empty(summary))
