"""Shared job summary helpers for tool modules."""


# DSS job state is not always present at the top level.
# Prefer job-level fields, then activities, then jobEndTime as a last resort.
def _derive_job_state(raw_job: dict, job_end_time: int | None) -> str | None:
    explicit_state = raw_job.get("state")
    if explicit_state:
        return explicit_state

    base_status = raw_job.get("baseStatus", {})
    for key in ("state", "status"):
        fallback_state = base_status.get(key)
        if fallback_state:
            return fallback_state

    runtime_summary = raw_job.get("runtimeSummary", {})
    for key in ("state", "status"):
        fallback_state = runtime_summary.get(key)
        if fallback_state:
            return fallback_state

    activities = runtime_summary.get("activities") or []
    activity_states = [activity.get("state") for activity in activities if activity.get("state")]
    if "FAILED" in activity_states:
        return "FAILED"
    if "ABORTED" in activity_states:
        return "ABORTED"
    if activity_states and all(state == "DONE" for state in activity_states):
        return "DONE"

    if isinstance(job_end_time, int):
        if job_end_time > 0:
            return "DONE"
        if job_end_time == 0:
            return "RUNNING"

    return None


def _summarize_job_outputs(outputs: list[dict] | None) -> list[dict]:
    if not outputs:
        return []

    summarized_outputs = []
    for output in outputs:
        summarized_output = {"type": output.get("type")}
        for key in (
            "targetDatasetProjectKey",
            "targetDataset",
            "targetPartition",
            "targetManagedFolderProjectKey",
            "targetManagedFolder",
            "savedModelId",
        ):
            if key in output:
                summarized_output[key] = output.get(key)
        summarized_outputs.append(summarized_output)
    return summarized_outputs


def _summarize_runtime_activities(
    activities: list[dict] | None,
    base_activities: dict | None = None,
) -> list[dict]:
    if not activities:
        return []

    base_activities = base_activities or {}
    summarized_activities = []
    for activity in activities:
        activity_id = activity.get("activityId")
        base = base_activities.get(activity_id) or {}
        summarized_activities.append(
            {
                "activity_id": activity_id,
                "recipe_name": base.get("recipeName"),
                "state": activity.get("state"),
                "activity_type": activity.get("activityType"),
                "engine_type": activity.get("engineType"),
                "total_time_ms": activity.get("totalTime"),
                "preparing_time_ms": activity.get("preparingTime"),
                "waiting_time_ms": activity.get("waitingTime"),
                "running_time_ms": activity.get("runningTime"),
                "outputs": [
                    {"type": target.get("type"), "ref": target.get("id")}
                    for target in (base.get("targets") or [])
                ],
            }
        )
    return summarized_activities


def _summarize_activity_warnings(base_activities: dict | None) -> list[dict]:
    if not base_activities:
        return []

    summarized_warnings = []
    for activity_id, activity in base_activities.items():
        warnings_payload = (activity or {}).get("warnings") or {}
        warnings_by_type = warnings_payload.get("warnings") or {}

        for warning_type, warning_details in warnings_by_type.items():
            stored = warning_details.get("stored") or []
            summarized_warnings.append(
                {
                    "activity_id": activity_id,
                    "warning_type": warning_details.get("type", warning_type),
                    "count": warning_details.get("count", len(stored)),
                    "messages": [
                        entry.get("message") for entry in stored if entry.get("message")
                    ],
                }
            )

    return summarized_warnings


def get_job_status_brief(
    project_key: str,
    job_id: str,
    raw_status: dict,
) -> dict:
    definition = raw_status.get("def", {}) or {}
    base_status = raw_status.get("baseStatus", {}) or {}
    job_start_time = base_status.get("jobStartTime")
    job_end_time = base_status.get("jobEndTime")

    summary = {
        "project_key": project_key,
        "job_id": definition.get("id", job_id),
        "status": _derive_job_state(raw_status, job_end_time),
        "type": definition.get("type"),
        "start_time": job_start_time,
        "end_time": job_end_time,
    }

    if (
        isinstance(job_start_time, int)
        and isinstance(job_end_time, int)
        and job_end_time > 0
    ):
        summary["total_duration_ms"] = job_end_time - job_start_time

    return summary


def get_job_status_full(project_key: str, job_id: str, raw_status: dict) -> dict:
    definition = raw_status.get("def", {}) or {}
    base_status = raw_status.get("baseStatus", {}) or {}
    runtime_summary = raw_status.get("runtimeSummary", {})
    initiator = raw_status.get("initiator", {})
    job_start_time = base_status.get("jobStartTime")
    job_end_time = base_status.get("jobEndTime")

    summary = {
        "project_key": project_key,
        "job_id": definition.get("id", job_id),
        "name": definition.get("name"),
        "state": _derive_job_state(raw_status, job_end_time),
        "job_type": runtime_summary.get("jobType", definition.get("type")),
        "trigger_type": runtime_summary.get(
            "triggerType", definition.get("triggeredFrom")
        ),
        "initiator": {
            "login": initiator.get("login"),
            "display_name": initiator.get("displayName"),
        },
        "outputs": _summarize_job_outputs(definition.get("outputs")),
        "start_time": job_start_time,
        "end_time": job_end_time,
        "resolve_duration_ms": base_status.get("resolveDuration"),
        "exec_duration_ms": base_status.get("execDuration"),
        "activities": _summarize_runtime_activities(
            runtime_summary.get("activities"),
            base_status.get("activities"),
        ),
        "warnings": _summarize_activity_warnings(base_status.get("activities")),
    }

    if (
        isinstance(job_start_time, int)
        and isinstance(job_end_time, int)
        and job_end_time > 0
    ):
        summary["total_duration_ms"] = job_end_time - job_start_time

    return summary


def summarize_listed_job(project_key: str, raw_job: dict) -> dict:
    definition = raw_job.get("def", {}) or {}
    initiator = raw_job.get("initiator", {})

    return {
        "project_key": project_key,
        "name": raw_job.get("name", definition.get("name")),
        "job_id": raw_job.get("id", definition.get("id")),
        "status": raw_job.get("state"),
        "initiator": {
            "login": initiator.get("login"),
            "display_name": initiator.get("displayName"),
        },
        "type": raw_job.get("type", definition.get("type")),
        "initiation_timestamp": raw_job.get(
            "initiationTimestamp", definition.get("initiationTimestamp")
        ),
        "initiation_type": raw_job.get("triggeredFrom", definition.get("triggeredFrom")),
    }
