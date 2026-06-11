"""Pure payload builders and validators for scenario commands.

Keep DSS JSON shape logic here so ``scenario.py`` can stay focused on Typer
command wiring and API calls.
"""

from __future__ import annotations

import difflib

from dku_cli.enums import EnvMode
from dku_cli.errors import exit_with_error


VALID_FREQUENCIES = frozenset({"Minutely", "Hourly", "Daily", "Weekly", "Monthly"})
VALID_DAYS_OF_WEEK = frozenset(
    {
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    }
)
VALID_MONTHLY_RUN_ON = frozenset(
    {
        "ON_THE_DAY",
        "LAST_DAY_OF_THE_MONTH",
        "FIRST_DAY_OF_THE_MONTH",
        "FIRST_WEEK",
        "LAST_WEEK",
    }
)


KNOWN_STEP_TYPES = frozenset(
    {
        "build_flowitem",
        "custom_python",
        "exec_sql",
        "check_dataset",
        "compute_metrics",
        "reload_schema",
        "run_scenario",
        "restart_webapp",
        "refresh_chart_cache",
        "set_project_variables",
        "clear_dataset",
        "invalidate_cache",
        "kill_scenario",
        "package_api_service",
        "update_from_bundle",
        "merge_branch",
        "git_push",
        "start_apinode_service",
        "stop_apinode_service",
        "notify",
        "email_report",
        "dataset_data_check",
    }
)


# Server enum Step.RunConditionType. Omitting the field defaults server-side to
# RUN_IF_STATUS_MATCH on SUCCESS,WARNING, so prior failures skip following steps.
VALID_RUN_CONDITION_TYPES = frozenset(
    {"RUN_ALWAYS", "RUN_IF_STATUS_MATCH", "RUN_CONDITIONALLY"}
)
RUN_CONDITION_TYPE_ALIASES = {
    "ALWAYS": "RUN_ALWAYS",
    "RUN_IF_EXPR_TRUE": "RUN_CONDITIONALLY",
    "RUN_IF_NOT_EXPR_TRUE": "RUN_CONDITIONALLY",
}

# Server enum ReportItem.Outcome, also used by params.handleWarningsAs.
VALID_STEP_STATUSES = frozenset({"SUCCESS", "WARNING", "FAILED", "ABORTED"})
HANDLE_WARNINGS_ALIASES = {
    "AS_FAILURE": "FAILED",
    "FAIL": "FAILED",
    "NORMAL_WARNING": "WARNING",
    "IMPORTANT_WARNING": "WARNING",
    "FAIL_SILENTLY": "SUCCESS",
}


# dataikuapi project.py new_job values. DSS saves bad values as null jobType,
# then the build step fails later with a NullPointerException.
VALID_BUILD_JOB_TYPES = frozenset(
    {
        "RECURSIVE_BUILD",
        "NON_RECURSIVE_FORCED_BUILD",
        "RECURSIVE_FORCED_BUILD",
        "RECURSIVE_MISSING_ONLY_BUILD",
    }
)
BUILD_JOB_TYPE_ALIASES = {
    "FORCED_RECURSIVE_BUILD": "RECURSIVE_FORCED_BUILD",
    "RECURSIVE": "RECURSIVE_BUILD",
    "FORCED": "NON_RECURSIVE_FORCED_BUILD",
    "NON_RECURSIVE_BUILD": "NON_RECURSIVE_FORCED_BUILD",
}


def build_temporal_trigger(
    *,
    frequency: str,
    hour: int,
    minute: int,
    days: str | None,
    monthly_run_on: str,
    repeat_every: int,
    timezone: str,
    active: bool,
) -> dict:
    """Build and validate a DSS temporal trigger payload."""
    _validate_temporal_inputs(frequency, hour, minute, repeat_every)

    params: dict = {
        "frequency": frequency,
        "repeatFrequency": repeat_every,
        "timezone": timezone,
    }

    if frequency in {"Hourly", "Daily"}:
        params.update(_time_params(hour, minute))
    elif frequency == "Weekly":
        params.update(_weekly_params(days, hour, minute))
    elif frequency == "Monthly":
        params.update(_monthly_params(monthly_run_on, hour, minute))

    return {"active": active, "type": "temporal", "params": params}


def _validate_temporal_inputs(
    frequency: str,
    hour: int,
    minute: int,
    repeat_every: int,
) -> None:
    if frequency not in VALID_FREQUENCIES:
        exit_with_error(
            f"Invalid --frequency '{frequency}'.",
            details=[f"Valid: {', '.join(sorted(VALID_FREQUENCIES))}"],
        )
    if not 0 <= hour <= 23:
        exit_with_error(f"--hour {hour} out of range (0-23).")
    if not 0 <= minute <= 59:
        exit_with_error(
            f"--minute {minute} out of range (0-59).",
        )
    if repeat_every < 1:
        exit_with_error(f"--repeat-every {repeat_every} must be >= 1.")


def _time_params(hour: int, minute: int) -> dict:
    return {"hour": hour, "minute": minute}


def _weekly_params(days: str | None, hour: int, minute: int) -> dict:
    if not days:
        exit_with_error(
            "--days is required for Weekly frequency.",
            details=["Example: --days Monday,Wednesday,Friday"],
        )
    days_list = [d.strip() for d in days.split(",") if d.strip()]
    invalid = [d for d in days_list if d not in VALID_DAYS_OF_WEEK]
    if invalid:
        exit_with_error(
            f"Invalid day(s): {', '.join(invalid)}.",
            details=[f"Valid: {', '.join(sorted(VALID_DAYS_OF_WEEK))}"],
        )
    return {**_time_params(hour, minute), "daysOfWeek": days_list}


def _monthly_params(monthly_run_on: str, hour: int, minute: int) -> dict:
    if monthly_run_on not in VALID_MONTHLY_RUN_ON:
        exit_with_error(
            f"Invalid --monthly-run-on '{monthly_run_on}'.",
            details=[f"Valid: {', '.join(sorted(VALID_MONTHLY_RUN_ON))}"],
        )
    return {**_time_params(hour, minute), "monthlyRunOn": monthly_run_on}


def env_selection(env_mode: EnvMode, env_name: str | None) -> dict:
    """Build envSelection and reject EXPLICIT_ENV without a concrete env."""
    if env_mode == EnvMode.EXPLICIT_ENV and not env_name:
        exit_with_error(
            "--env-mode EXPLICIT_ENV requires --env-name.",
        )
    selection = {"envMode": env_mode.value}
    if env_name:
        selection["envName"] = env_name
    return selection


def build_python_trigger(
    *,
    code: str,
    env_mode: EnvMode,
    env_name: str | None,
    delay: int,
    grace_delay: int,
    check_again: bool,
    active: bool,
    name: str | None = None,
) -> dict:
    """Build a custom_python trigger payload."""
    trigger = {
        "active": active,
        "type": "custom_python",
        "delay": delay,
        "graceDelaySettings": {
            "delay": grace_delay,
            "checkAgainAfterGraceDelay": check_again,
        },
        "params": {
            "code": code,
            "envSelection": env_selection(env_mode, env_name),
        },
    }
    if name:
        trigger["name"] = name
    return trigger


def validate_handle_warnings_as(value: str | None) -> str | None:
    """Validate --handle-warnings-as against ReportItem.Outcome."""
    if value is None:
        return None
    candidate = value.strip().upper()
    if candidate in VALID_STEP_STATUSES:
        return candidate
    details = [f"Use {', '.join(sorted(VALID_STEP_STATUSES))}."]
    alias = HANDLE_WARNINGS_ALIASES.get(candidate)
    if alias:
        details.insert(0, f"Did you mean '{alias}'?")
    details.append("DSS silently replaces an unknown value with the default WARNING.")
    exit_with_error(
        f"Invalid --handle-warnings-as '{value}'.",
        details=details,
    )
    return None


def _reject_run_condition_type(value: str) -> None:
    details = [f"Use {', '.join(sorted(VALID_RUN_CONDITION_TYPES))}."]
    alias = RUN_CONDITION_TYPE_ALIASES.get(value.upper())
    if alias:
        details.insert(0, f"Did you mean '{alias}'?")
    details.append(
        "An unknown value saves as a null runConditionType and the "
        "scenario save fails with a server NullPointerException."
    )
    exit_with_error(
        f"Invalid --run-condition-type '{value}'.",
        details=details,
    )


def validate_run_options(
    run_condition_type: str | None,
    run_condition_expression: str | None,
    run_condition_statuses: list[str] | None,
    max_retries: int | None,
    delay_between_retries: int | None,
) -> tuple[str | None, list[str] | None]:
    """Cross-validate run-condition / retry flags."""
    if delay_between_retries is not None and max_retries is None:
        exit_with_error(
            "--delay-between-retries requires --max-retries.",
        )
    if run_condition_type and run_condition_type not in VALID_RUN_CONDITION_TYPES:
        _reject_run_condition_type(run_condition_type)
    if run_condition_expression and not run_condition_type:
        run_condition_type = "RUN_CONDITIONALLY"
    parsed_statuses: list[str] | None = None
    if run_condition_statuses:
        parsed_statuses = []
        for entry in run_condition_statuses:
            for v in entry.replace(",", " ").split():
                v = v.strip().upper()
                if not v:
                    continue
                if v not in VALID_STEP_STATUSES:
                    exit_with_error(
                        f"Invalid status '{v}' in --run-condition-statuses.",
                        details=[
                            f"Valid: {', '.join(sorted(VALID_STEP_STATUSES))}",
                            "DSS UI default for 'run if previous succeeded' "
                            "is SUCCESS,WARNING.",
                        ],
                    )
                parsed_statuses.append(v)
        if parsed_statuses and not run_condition_type:
            run_condition_type = "RUN_IF_STATUS_MATCH"
    return run_condition_type, parsed_statuses


def build_step(
    step_type: str,
    name: str,
    params: dict,
    *,
    proceed_on_failure: bool = False,
    delay_between_retries: int | None = None,
    max_retries: int | None = None,
    run_condition_type: str | None = None,
    run_condition_expression: str | None = None,
    run_condition_statuses: list[str] | None = None,
    reset_scenario_status: bool = False,
) -> dict:
    """Assemble the common DSS step envelope."""
    step = {
        "type": step_type,
        "name": name,
        "params": params,
    }
    if proceed_on_failure:
        step.setdefault("params", {})["proceedOnFailure"] = True
    if delay_between_retries is not None:
        step["delayBetweenRetries"] = delay_between_retries
    if max_retries is not None:
        step["maxRetriesOnFail"] = max_retries
    if run_condition_type:
        step["runConditionType"] = run_condition_type
    if run_condition_expression:
        step["runConditionExpression"] = run_condition_expression
    if run_condition_statuses:
        step["runConditionStatuses"] = run_condition_statuses
    if reset_scenario_status:
        step["resetScenarioStatus"] = True
    return step


def validate_build_job_type(job_type: str) -> str:
    """Return a valid build job type or exit with a prescriptive error."""
    if job_type in VALID_BUILD_JOB_TYPES:
        return job_type

    details = [f"Valid values: {', '.join(sorted(VALID_BUILD_JOB_TYPES))}."]
    suggestion = BUILD_JOB_TYPE_ALIASES.get(job_type)
    if suggestion is None:
        close = difflib.get_close_matches(
            job_type, VALID_BUILD_JOB_TYPES, n=1, cutoff=0.5
        )
        suggestion = close[0] if close else None
    if suggestion:
        details.append(f"Did you mean '{suggestion}'?")
    details.append(
        "An invalid jobType saves as null and the build step fails at run "
        "time with a server NullPointerException."
    )
    exit_with_error(
        f"Invalid --job-type '{job_type}'.",
        details=details,
    )
    return job_type


def build_targets(refs: list[str]) -> list[dict]:
    """Build FlowItem refs for build_flowitem steps."""
    targets = []
    for ref in refs:
        if "." in ref:
            pk, item_id = ref.split(".", 1)
            targets.append({"type": "DATASET", "projectKey": pk, "itemId": item_id})
        else:
            targets.append({"type": "DATASET", "itemId": ref})
    return targets


def dataset_items(refs: list[str]) -> list[dict]:
    """Build DATASET items for scenario step params."""
    return typed_items(refs, item_type="DATASET")


def typed_items(refs: list[str], item_type: str) -> list[dict]:
    """Build step item refs; supports PROJECT.NAME cross-project form."""
    items = []
    for ref in refs:
        if "." in ref:
            pk, name = ref.split(".", 1)
            items.append(
                {
                    "type": item_type,
                    "projectKey": pk,
                    "itemId": name,
                    "partitionsSpec": "",
                }
            )
        else:
            items.append({"type": item_type, "itemId": ref, "partitionsSpec": ""})
    return items


def mixed_typed_items(
    datasets: list[str] | None = None,
    folders: list[str] | None = None,
    saved_models: list[str] | None = None,
) -> list[dict]:
    """Combine dataset, folder, and saved-model refs into one item array."""
    items: list[dict] = []
    if datasets:
        items.extend(typed_items(datasets, "DATASET"))
    if folders:
        items.extend(typed_items(folders, "MANAGED_FOLDER"))
    if saved_models:
        items.extend(typed_items(saved_models, "SAVED_MODEL"))
    return items
