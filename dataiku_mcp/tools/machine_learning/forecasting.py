"""Time series forecasting analysis creation and update."""

from __future__ import annotations

from typing import Optional

from fastmcp import Context

from ... import mcp
from ..utils.async_executor import run_blocking
from ..utils.serialization import compact_json
from ..utils.auth import get_dss_client
from ..utils.parsing import (
    parse_json_array as _parse_json_array,
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


@mcp.tool()
async def create_timeseries_forecasting_analysis(
    project_key: str,
    input_dataset: str,
    target_variable: str,
    time_variable: str,
    ctx: Context,
    analysis_name: Optional[str] = None,
    timeseries_identifiers: Optional[str] = None,
    guess_policy: str = "TIMESERIES_DEFAULT",
) -> str:
    """Create a time series forecasting analysis, wait for DSS guessing, and return created ids/metadata.

    Args:
        input_dataset: Training dataset name
        target_variable: Column to forecast
        time_variable: Column holding the timestamp
        analysis_name: Visual analysis name (auto-generated if omitted)
        timeseries_identifiers: JSON array of column names that identify distinct series (for multi-series datasets)
        guess_policy: DSS guess policy
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    input_dataset = _require_non_empty_string(input_dataset, "input_dataset")
    target_variable = _require_non_empty_string(target_variable, "target_variable")
    time_variable = _require_non_empty_string(time_variable, "time_variable")
    guess_policy = _require_non_empty_string(guess_policy, "guess_policy")
    if analysis_name is not None:
        analysis_name = _require_non_empty_string(analysis_name, "analysis_name")

    identifier_list = (
        _parse_non_empty_string_list(timeseries_identifiers, "timeseries_identifiers")
        if timeseries_identifiers is not None
        else None
    )

    await ctx.info(
        f"Creating time series forecasting analysis on dataset '{input_dataset}' and waiting for DSS guessing..."
    )

    def _configure():
        project = get_dss_client().get_project(project_key)
        mltask = project.create_timeseries_forecasting_ml_task(
            input_dataset=input_dataset,
            target_variable=target_variable,
            time_variable=time_variable,
            timeseries_identifiers=identifier_list,
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
            include_target_column=True,
        )

    result = await run_blocking(_configure)
    await ctx.report_progress(1, 1)
    # Drop pure echoes of input params (caller already has these in context).
    result.pop("project_key", None)
    result.pop("input_dataset", None)
    response = {
        **result,
        "time_variable": time_variable,
        "timeseries_identifiers": identifier_list,
        "hint": (
            "Inspect raw guessed settings with get_ml_analysis_settings(); "
            "use get_ml_analysis_summary() for a normalized overview, then customize with "
            "update_timeseries_forecasting_analysis() and train with train_ml_analysis()."
        ),
    }
    # Lever 4: omit timeseries_identifiers when empty (single-series datasets pass
    # no identifiers -> None/[]); absent is read as "no identifiers" by convention.
    if response.get("timeseries_identifiers") in (None, []):
        response.pop("timeseries_identifiers", None)
    return compact_json(response)


@mcp.tool()
async def update_timeseries_forecasting_analysis(
    project_key: str,
    analysis_id: str,
    ctx: Context,
    analysis_name: Optional[str] = None,
    target_variable: Optional[str] = None,
    time_variable: Optional[str] = None,
    timeseries_identifiers: Optional[str] = None,
    metric: Optional[str] = None,
    algorithms: Optional[str] = None,
    forecast_horizon: Optional[int] = None,
    validation_horizons: Optional[str] = None,
    time_unit: Optional[str] = None,
    n_time_units: Optional[int] = None,
    end_of_week_day: Optional[int] = None,
    unit_alignment: Optional[str] = None,
    monthly_alignment: Optional[str] = None,
    duplicate_timestamp_handling: Optional[str] = None,
    included_features: Optional[str] = None,
    rejected_features: Optional[str] = None,
    algorithm_settings_patch: Optional[str] = None,
    feature_preprocessing_patch: Optional[str] = None,
    env_mode: Optional[str] = None,
    env_name: Optional[str] = None,
    full_reguess: bool = False,
) -> str:
    """Update an existing time series forecasting analysis in place.

    Args:
        analysis_id: Analysis ID from list_ml_analyses
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    analysis_id = _require_non_empty_string(analysis_id, "analysis_id")
    if analysis_name is not None:
        analysis_name = _require_non_empty_string(analysis_name, "analysis_name")
    if target_variable is not None:
        target_variable = _require_non_empty_string(target_variable, "target_variable")
    if time_variable is not None:
        time_variable = _require_non_empty_string(time_variable, "time_variable")
    if time_unit is not None:
        time_unit = _require_non_empty_string(time_unit, "time_unit")
    if unit_alignment is not None:
        unit_alignment = _require_non_empty_string(unit_alignment, "unit_alignment")
    if monthly_alignment is not None:
        monthly_alignment = _require_non_empty_string(
            monthly_alignment, "monthly_alignment"
        )
    if duplicate_timestamp_handling is not None:
        duplicate_timestamp_handling = _require_non_empty_string(
            duplicate_timestamp_handling, "duplicate_timestamp_handling"
        )

    algo_list = (
        _parse_non_empty_string_list(algorithms, "algorithms")
        if algorithms is not None
        else None
    )
    identifier_list = (
        _parse_non_empty_string_list(timeseries_identifiers, "timeseries_identifiers")
        if timeseries_identifiers is not None
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
    validation_horizons_list = (
        _parse_json_array(validation_horizons, "validation_horizons")
        if validation_horizons is not None
        else None
    )
    if forecast_horizon is not None:
        forecast_horizon = _require_positive_int(forecast_horizon, "forecast_horizon")
    if n_time_units is not None:
        n_time_units = _require_positive_int(n_time_units, "n_time_units")

    if (
        analysis_name is None
        and target_variable is None
        and time_variable is None
        and identifier_list is None
        and metric is None
        and algo_list is None
        and forecast_horizon is None
        and validation_horizons_list is None
        and time_unit is None
        and n_time_units is None
        and end_of_week_day is None
        and unit_alignment is None
        and monthly_alignment is None
        and duplicate_timestamp_handling is None
        and included_feature_list is None
        and rejected_feature_list is None
        and algorithm_settings_patch_obj is None
        and feature_preprocessing_patch_obj is None
        and env_mode is None
    ):
        raise ValueError("Provide at least one setting to update.")

    await ctx.info(f"Updating time series forecasting analysis {analysis_id}...")

    def _update():
        project = get_dss_client().get_project(project_key)
        analysis = project.get_analysis(analysis_id)
        task_ref = _require_single_ml_task(analysis)
        mltask_id = task_ref["mlTaskId"]
        set_analysis_name(analysis, analysis_name)
        mltask = analysis.get_ml_task(mltask_id)
        settings = mltask.get_settings()
        raw_settings = settings.get_raw()

        if raw_settings.get("predictionType") != "TIMESERIES_FORECAST":
            raise ValueError(
                f"ML task '{mltask_id}' is '{raw_settings.get('predictionType')}', not a time series forecasting task."
            )

        def _guess_if_changed(**kwargs):
            mltask.guess(full_reguess=full_reguess, **kwargs)
            mltask.wait_guess_complete()

        guessed = False
        if target_variable is not None and target_variable != raw_settings.get(
            "targetVariable"
        ):
            _guess_if_changed(target_variable=target_variable)
            guessed = True
        if time_variable is not None and time_variable != raw_settings.get(
            "timeVariable"
        ):
            _guess_if_changed(time_variable=time_variable)
            guessed = True
        if identifier_list is not None and list(identifier_list) != list(
            raw_settings.get("timeseriesIdentifiers") or []
        ):
            _guess_if_changed(timeseries_identifiers=identifier_list)
            guessed = True
        if full_reguess and not guessed:
            mltask.guess(full_reguess=True)
            mltask.wait_guess_complete()
            guessed = True
        if guessed:
            settings = mltask.get_settings()
            raw_settings = settings.get_raw()

        apply_algorithm_selection(settings, algo_list)
        if metric is not None:
            settings.set_metric(metric=metric)
        if forecast_horizon is not None:
            settings.set_forecast_horizon(
                forecast_horizon,
                validation_horizons=validation_horizons_list,
            )
        if any(
            value is not None
            for value in [
                time_unit,
                n_time_units,
                end_of_week_day,
                unit_alignment,
                monthly_alignment,
            ]
        ):
            settings.set_time_step(
                time_unit=time_unit,
                n_time_units=n_time_units,
                end_of_week_day=end_of_week_day,
                unit_alignment=unit_alignment,
                monthly_alignment=monthly_alignment,
            )
        if duplicate_timestamp_handling is not None:
            settings.set_duplicate_timestamp_handling(duplicate_timestamp_handling)

        protected_feature_names = set(
            value
            for value in [
                raw_settings.get("targetVariable"),
                raw_settings.get("timeVariable"),
            ]
            if value is not None
        )
        protected_feature_names.update(raw_settings.get("timeseriesIdentifiers") or [])
        apply_feature_selection(
            settings=settings,
            raw_settings=raw_settings,
            included_features=included_feature_list,
            rejected_features=rejected_feature_list,
            protected_roles={"TARGET", "TIME"},
            protected_feature_names=protected_feature_names,
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
        summary = build_ml_task_summary(
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
        # Drop pure echoes of input params (caller already has these in context).
        summary.pop("project_key", None)
        summary.pop("analysis_id", None)
        return summary

    return compact_json(await run_blocking(_update))
