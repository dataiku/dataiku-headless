"""Causal prediction analysis creation and update."""

from __future__ import annotations

from typing import Optional

from fastmcp import Context

from ... import mcp
from ..utils.async_executor import run_blocking
from ..utils.serialization import compact_json, omit_empty
from ..utils.auth import get_dss_client
from ..utils.parsing import (
    parse_json_array as _parse_json_array,
    parse_json_object as _parse_json_object,
    parse_non_empty_string_list as _parse_non_empty_string_list,
)
from ..utils.validation import (
    require_allowed_value as _require_allowed_value,
    require_fraction as _require_fraction,
    require_int_at_least as _require_int_at_least,
    require_non_empty_string as _require_non_empty_string,
    require_positive_int as _require_positive_int,
)
from .shared.common import (
    build_created_ml_task_response,
    find_analysis_input_dataset,
    require_single_ml_task as _require_single_ml_task,
    set_analysis_name,
)
from .shared.constants import PREDICTION_SPLIT_METHODS as _PREDICTION_SPLIT_METHODS
from .shared.settings import (
    apply_algorithm_selection,
    apply_algorithm_settings_patch,
    apply_env_selection,
    apply_feature_preprocessing_patch,
    apply_feature_selection,
    apply_split_settings,
    validate_feature_names,
)
from .shared.summaries import build_ml_task_summary


def apply_causal_treatment_settings(
    raw_settings: dict,
    treatment_variable: str | None,
    control_value: str | None,
    treatment_values: list | None,
    positive_class: str | None,
) -> None:
    per_feature = raw_settings.get("preprocessing", {}).get("per_feature", {})

    if treatment_variable is not None:
        validate_feature_names(raw_settings, [treatment_variable], "treatment_variable")
        current_treatment = raw_settings.get("treatmentVariable")
        if current_treatment and current_treatment != treatment_variable:
            previous = per_feature.get(current_treatment)
            if previous is not None:
                previous["role"] = "INPUT"
        raw_settings["treatmentVariable"] = treatment_variable
        if treatment_variable in per_feature:
            per_feature[treatment_variable]["role"] = "TREATMENT"

    if control_value is not None:
        raw_settings["controlValue"] = control_value
    if treatment_values is not None:
        raw_settings["treatmentValues"] = treatment_values
    if positive_class is not None:
        raw_settings["positiveClass"] = positive_class


@mcp.tool()
async def create_causal_prediction_analysis(
    project_key: str,
    input_dataset: str,
    outcome_variable: str,
    treatment_variable: str,
    ctx: Context,
    analysis_name: Optional[str] = None,
) -> str:
    """Create a causal prediction analysis, wait for DSS guessing, and return created ids/metadata.

    Args:
        input_dataset: Training dataset name
        outcome_variable: Column whose causal effect is being estimated
        treatment_variable: Column indicating treatment assignment
        analysis_name: Visual analysis name (auto-generated if omitted)
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    input_dataset = _require_non_empty_string(input_dataset, "input_dataset")
    outcome_variable = _require_non_empty_string(outcome_variable, "outcome_variable")
    treatment_variable = _require_non_empty_string(
        treatment_variable, "treatment_variable"
    )
    if analysis_name is not None:
        analysis_name = _require_non_empty_string(analysis_name, "analysis_name")

    await ctx.info(
        f"Creating causal prediction analysis on dataset '{input_dataset}' and waiting for DSS guessing..."
    )

    def _configure():
        project = get_dss_client().get_project(project_key)
        mltask = project.create_causal_prediction_ml_task(
            input_dataset=input_dataset,
            outcome_variable=outcome_variable,
            treatment_variable=treatment_variable,
            wait_guess_complete=True,
        )
        analysis = project.get_analysis(mltask.analysis_id)
        return build_created_ml_task_response(
            project_key=project_key,
            input_dataset=input_dataset,
            mltask=mltask,
            analysis=analysis,
            analysis_name=analysis_name,
            # target_column omitted: for a causal task the target IS the outcome
            # variable (create_causal_prediction_ml_task sets targetVariable=outcome_variable
            # and the guesser never changes it), so it always equals the
            # outcome_variable field returned below.
            include_target_column=False,
            include_prediction_type=True,
        )

    result = await run_blocking(_configure)
    await ctx.report_progress(1, 1)
    response = {
            **result,
            "outcome_variable": outcome_variable,
            "treatment_variable": treatment_variable,
            "hint": (
                "Inspect raw guessed settings with get_ml_analysis_settings(); "
                "use get_ml_analysis_summary() for a normalized overview, then train with "
                "train_ml_analysis()."
            ),
        }
    # Lever 4: omit top-level fields that carry no information (None / "" / [] / {}).
    # Keeps False and 0 (they are not equal to any of the empty sentinels).
    response = omit_empty(response)
    return compact_json(response)


@mcp.tool()
async def update_causal_prediction_analysis(
    project_key: str,
    analysis_id: str,
    ctx: Context,
    analysis_name: Optional[str] = None,
    outcome_variable: Optional[str] = None,
    treatment_variable: Optional[str] = None,
    metric: Optional[str] = None,
    algorithms: Optional[str] = None,
    split_method: Optional[str] = None,
    train_ratio: Optional[float] = None,
    n_folds: Optional[int] = None,
    stratified: Optional[bool] = None,
    split_seed: Optional[int] = None,
    control_value: Optional[str] = None,
    treatment_values: Optional[str] = None,
    positive_class: Optional[str] = None,
    included_features: Optional[str] = None,
    rejected_features: Optional[str] = None,
    algorithm_settings_patch: Optional[str] = None,
    feature_preprocessing_patch: Optional[str] = None,
    env_mode: Optional[str] = None,
    env_name: Optional[str] = None,
    full_reguess: bool = False,
) -> str:
    """Update an existing causal prediction analysis in place.

    Args:
        analysis_id: Analysis ID from list_ml_analyses
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    analysis_id = _require_non_empty_string(analysis_id, "analysis_id")
    if analysis_name is not None:
        analysis_name = _require_non_empty_string(analysis_name, "analysis_name")
    if outcome_variable is not None:
        outcome_variable = _require_non_empty_string(
            outcome_variable, "outcome_variable"
        )
    if treatment_variable is not None:
        treatment_variable = _require_non_empty_string(
            treatment_variable, "treatment_variable"
        )
    if control_value is not None:
        control_value = _require_non_empty_string(control_value, "control_value")
    if positive_class is not None:
        positive_class = _require_non_empty_string(positive_class, "positive_class")

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
    treatment_values_list = (
        _parse_json_array(treatment_values, "treatment_values")
        if treatment_values is not None
        else None
    )
    if train_ratio is not None:
        train_ratio = _require_fraction(train_ratio, "train_ratio")
    if split_method is not None:
        split_method = _require_allowed_value(
            split_method,
            "split_method",
            _PREDICTION_SPLIT_METHODS,
        )
    if n_folds is not None:
        n_folds = _require_int_at_least(n_folds, "n_folds", 2)
    if split_seed is not None:
        split_seed = _require_positive_int(split_seed, "split_seed")

    if (
        analysis_name is None
        and outcome_variable is None
        and treatment_variable is None
        and metric is None
        and algo_list is None
        and split_method is None
        and train_ratio is None
        and n_folds is None
        and stratified is None
        and split_seed is None
        and control_value is None
        and treatment_values_list is None
        and positive_class is None
        and included_feature_list is None
        and rejected_feature_list is None
        and algorithm_settings_patch_obj is None
        and feature_preprocessing_patch_obj is None
        and env_mode is None
    ):
        raise ValueError("Provide at least one setting to update.")

    await ctx.info(f"Updating causal prediction analysis {analysis_id}...")

    def _update():
        project = get_dss_client().get_project(project_key)
        analysis = project.get_analysis(analysis_id)
        task_ref = _require_single_ml_task(analysis)
        mltask_id = task_ref["mlTaskId"]
        set_analysis_name(analysis, analysis_name)
        mltask = analysis.get_ml_task(mltask_id)
        settings = mltask.get_settings()
        raw_settings = settings.get_raw()

        if raw_settings.get("predictionType") not in {
            "CAUSAL_BINARY_CLASSIFICATION",
            "CAUSAL_REGRESSION",
        }:
            raise ValueError(
                f"ML task '{mltask_id}' is '{raw_settings.get('predictionType')}', not a causal prediction task."
            )

        if outcome_variable is not None and outcome_variable != raw_settings.get(
            "targetVariable"
        ):
            mltask.guess(target_variable=outcome_variable, full_reguess=full_reguess)
            mltask.wait_guess_complete()
            settings = mltask.get_settings()
            raw_settings = settings.get_raw()
        elif full_reguess:
            mltask.guess(full_reguess=True)
            mltask.wait_guess_complete()
            settings = mltask.get_settings()
            raw_settings = settings.get_raw()

        apply_causal_treatment_settings(
            raw_settings,
            treatment_variable=treatment_variable,
            control_value=control_value,
            treatment_values=treatment_values_list,
            positive_class=positive_class,
        )
        apply_algorithm_selection(settings, algo_list)
        if metric is not None:
            settings.set_metric(metric=metric)
        apply_split_settings(
            settings=settings,
            raw_settings=raw_settings,
            split_method=split_method,
            train_ratio=train_ratio,
            n_folds=n_folds,
            stratified=stratified,
            time_ordering_feature=None,
            time_ordering_ascending=True,
            disable_time_ordering=False,
            split_seed=split_seed,
        )
        apply_feature_selection(
            settings=settings,
            raw_settings=raw_settings,
            included_features=included_feature_list,
            rejected_features=rejected_feature_list,
            protected_roles={"TARGET", "TREATMENT"},
            protected_feature_names=set(
                value
                for value in [
                    raw_settings.get("targetVariable"),
                    raw_settings.get("treatmentVariable"),
                ]
                if value is not None
            ),
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
    # Lever 4: omit top-level fields that carry no information (None / "" / [] / {}).
    # Keeps False and 0; nested config dicts (split, metric_details, diagnostics,
    # hyperparameter_search) are left intact since their empty members are shaped
    # by the shared summary builders, not this file.
    summary = omit_empty(summary)
    return compact_json(summary)
