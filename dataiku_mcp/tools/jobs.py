"""Build operations for datasets and recipes."""

import asyncio
import time

from dataikuapi.dss.future import DSSFuture
from fastmcp import Context

from .. import mcp
from .utils.async_executor import run_blocking
from .utils.serialization import columnar, compact_json
from .utils.auth import get_dss_client
from .utils.job_summaries import (
    get_job_status_brief as _get_job_status_brief,
    get_job_status_full as _get_job_status_full,
    summarize_listed_job as _summarize_listed_job,
)
from .utils.validation import (
    require_allowed_value as _require_allowed_value,
    require_non_empty_list as _require_non_empty_list,
    require_non_empty_string as _require_non_empty_string,
    require_positive_int as _require_positive_int,
)

VALID_JOB_TYPES = {
    "NON_RECURSIVE_FORCED_BUILD",
    "RECURSIVE_BUILD",
    "RECURSIVE_FORCED_BUILD",
}

DEFAULT_WAIT_TIMEOUT_SECONDS = 50
JOB_POLL_INTERVAL_SECONDS = 2
TERMINAL_JOB_STATES = {"DONE", "FAILED", "ABORTED"}

COMPUTABLE_TO_JOB_OUTPUT_TYPE = {
    "COMPUTABLE_DATASET": "DATASET",
    "COMPUTABLE_FOLDER": "MANAGED_FOLDER",
    "COMPUTABLE_SAVED_MODEL": "SAVED_MODEL",
    "COMPUTABLE_STREAMING_ENDPOINT": "STREAMING_ENDPOINT",
    "COMPUTABLE_MODEL_EVALUATION_STORE": "MODEL_EVALUATION_STORE",
    "COMPUTABLE_RETRIEVABLE_KNOWLEDGE": "RETRIEVABLE_KNOWLEDGE",
}


async def _wait_for_job_result(
    project_key: str,
    job,
    timeout_seconds: int,
) -> tuple[bool, dict]:
    deadline = time.monotonic() + timeout_seconds

    while True:
        raw_status = await run_blocking(job.get_status)
        summary = _get_job_status_full(project_key, job.id, raw_status)

        if (
            summary["state"] in TERMINAL_JOB_STATES
            or (
                isinstance(summary.get("end_time"), int)
                and summary["end_time"] > 0
            )
        ):
            return False, summary

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return True, summary

        await asyncio.sleep(min(JOB_POLL_INTERVAL_SECONDS, remaining))


def _tail_log_text(log_text: str, tail_lines: int | None) -> tuple[str, int, bool]:
    lines = log_text.splitlines()
    line_count = len(lines)

    if tail_lines is None or line_count <= tail_lines:
        return log_text, line_count, False

    return "\n".join(lines[-tail_lines:]), line_count, True


@mcp.tool()
async def build_datasets(
    project_key: str,
    ctx: Context,
    dataset_names: list[str],
    wait_for_completion: bool = True,
    job_type: str = "NON_RECURSIVE_FORCED_BUILD",
    auto_update_schema: bool = True,
    timeout_seconds: int = DEFAULT_WAIT_TIMEOUT_SECONDS,
) -> str:
    """Build one or more datasets as DSS jobs.

    Args:
        dataset_names: Dataset names to build (at least one)
        wait_for_completion: If true, wait for the jobs to finish; if false, start the jobs and return their IDs
        job_type: One of NON_RECURSIVE_FORCED_BUILD, RECURSIVE_BUILD, RECURSIVE_FORCED_BUILD
        auto_update_schema: Whether to auto-update output schemas before each recipe run
        timeout_seconds: Max time to wait before returning in-progress job state
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    names = _require_non_empty_list(dataset_names, "dataset_names")
    names = [
        _require_non_empty_string(name, f"dataset_names[{i}]")
        for i, name in enumerate(names)
    ]
    job_type = _require_allowed_value(job_type, "job_type", VALID_JOB_TYPES)
    timeout_seconds = _require_positive_int(timeout_seconds, "timeout_seconds")

    await ctx.info(
        f"Starting build of {len(names)} dataset(s) in {project_key} ({job_type}, wait_for_completion={wait_for_completion}, auto_update_schema={auto_update_schema})..."
    )

    def _start_job(target_dataset_name: str):
        project = get_dss_client().get_project(project_key)
        builder = project.new_job(job_type)
        builder.with_output(target_dataset_name)
        if auto_update_schema:
            builder.with_auto_update_schema_before_each_recipe_run(True)
        return builder.start()

    # Start jobs
    jobs = []
    for ds_name in names:
        try:
            job = await run_blocking(_start_job, ds_name)
            jobs.append(
                {"dataset": ds_name, "status": "STARTED", "job_id": job.id, "obj": job}
            )
        except Exception as e:
            jobs.append(
                {"dataset": ds_name, "status": "FAILED_TO_START", "error": str(e)}
            )

    # Return if not `wait_for_completion`
    top_level_status = "builds_started"
    for job in jobs:
        if job["status"] == "FAILED_TO_START":
            top_level_status = "builds_started_with_errors"
            break

    if not wait_for_completion:
        return compact_json({
                "status": top_level_status,
                "project_key": project_key,
                "jobs": [{k: v for k, v in j.items() if k != "obj"} for j in jobs],
            })

    # Wait for jobs to complete
    for job in jobs:
        if job["status"] != "STARTED":
            continue

        timed_out, status_summary = await _wait_for_job_result(
            project_key,
            job["obj"],
            timeout_seconds,
        )
        job["status_summary"] = status_summary
        job["wait_timed_out"] = timed_out
        job["status"] = job["status_summary"]["state"]

    # Return completed job information
    top_level_status = "builds_completed"
    for job in jobs:
        if job["status"] in {"FAILED_TO_START", "FAILED", "ABORTED"}:
            top_level_status = "builds_completed_with_errors"
            break
        if job.get("wait_timed_out"):
            top_level_status = "builds_still_running"

    return compact_json({
            "status": top_level_status,
            "project_key": project_key,
            "jobs": [{k: v for k, v in j.items() if k != "obj"} for j in jobs],
                "hint": (
                    "If any job is still running, do not start another build for the same "
                    "flow object. Use wait_for_job(project_key, job_id, timeout_seconds=...) "
                    "or get_job_status(project_key, job_id). Add full=true only when you "
                    "need more detail, or use get_job_log(project_key, job_id) for logs."
                ),
            })


@mcp.tool()
async def run_recipe(
    project_key: str,
    recipe_name: str,
    ctx: Context,
    wait_for_completion: bool = True,
    job_type: str = "NON_RECURSIVE_FORCED_BUILD",
    auto_update_schema: bool = True,
    timeout_seconds: int = DEFAULT_WAIT_TIMEOUT_SECONDS,
) -> str:
    """Start a DSS job to run a recipe by building its first output as the trigger target.

    Args:
        wait_for_completion: If true, wait for the job to finish; if false, start it and return the job ID
        job_type: One of NON_RECURSIVE_FORCED_BUILD, RECURSIVE_BUILD, RECURSIVE_FORCED_BUILD
        auto_update_schema: Whether to auto-update output schemas before each recipe run
        timeout_seconds: Max time to wait before returning in-progress job state
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    recipe_name = _require_non_empty_string(recipe_name, "recipe_name")
    job_type = _require_allowed_value(job_type, "job_type", VALID_JOB_TYPES)
    timeout_seconds = _require_positive_int(timeout_seconds, "timeout_seconds")

    await ctx.info(
        f"Running recipe {recipe_name} in {project_key} ({job_type}, wait_for_completion={wait_for_completion}, auto_update_schema={auto_update_schema})..."
    )

    def _run():
        project = get_dss_client().get_project(project_key)
        recipe = project.get_recipe(recipe_name)

        # We aren't using DSSRecipe.run() directly. Instead we trigger the recipe
        # by building its first output object so that we can attach
        # auto_update_schema to the job builder, which prevents scoring recipes
        # e.g. from building datasets with empty schema.
        outputs = project.get_flow().get_graph().get_successor_computables(recipe)
        if not outputs:
            raise Exception(f"recipe '{recipe_name}' has no outputs, can't run it")

        first_output = outputs[0]
        object_type = COMPUTABLE_TO_JOB_OUTPUT_TYPE.get(first_output.get("type"))
        if object_type is None:
            raise Exception(
                f"recipe '{recipe_name}' has unsupported output type "
                f"{first_output.get('type')}, can't run it"
            )

        builder = project.new_job(job_type)
        builder.with_output(first_output["ref"], object_type=object_type)
        if auto_update_schema:
            builder.with_auto_update_schema_before_each_recipe_run(True)

        return builder.start()

    job = await run_blocking(_run)

    if not wait_for_completion:
        return compact_json({
                "status": "recipe_run_started",
                "project_key": project_key,
                "recipe": recipe_name,
                "job_id": job.id,
            })

    timed_out, status_summary = await _wait_for_job_result(
        project_key,
        job,
        timeout_seconds,
    )
    if timed_out:
        return compact_json({
                "status": "recipe_run_still_running",
                "project_key": project_key,
                "recipe": recipe_name,
                "job_id": job.id,
                "status_summary": status_summary,
                "hint": (
                    "Do not start another build for this recipe or its outputs while this "
                    "job is still running. Use wait_for_job(project_key, job_id, "
                    "timeout_seconds=...) or get_job_status(project_key, job_id). Add "
                    "full=true only when you need more detail, or use "
                    "get_job_log(project_key, job_id) for logs."
                ),
            })

    top_level_status = "recipe_run_completed"
    if status_summary["state"] in {"FAILED", "ABORTED"}:
        top_level_status = "recipe_run_completed_with_errors"

    return compact_json({
            "status": top_level_status,
            "status_summary": status_summary,
            "project_key": project_key,
            "recipe": recipe_name,
            "job_id": job.id,
        })


@mcp.tool()
async def get_future_status(
    future_id: str,
    ctx: Context,
    fetch_result: bool = False,
) -> str:
    """Get the status of a DSSFuture returned by a long-running DSS operation.

    Args:
        future_id: Future ID returned by a DSS operation
        fetch_result: If true, fetch the result when it is ready; if false, only peek
    """
    future_id = _require_non_empty_string(future_id, "future_id")
    await ctx.info(
        f"Retrieving DSS future status for {future_id} "
        f"(fetch_result={fetch_result})..."
    )

    def _run():
        future = DSSFuture(get_dss_client(), future_id)
        state = future.get_state() if fetch_result else future.peek_state()
        return {
            "future_id": future_id,
            "state": state,
        }

    return compact_json(await run_blocking(_run))

@mcp.tool()
async def get_job_status(
    project_key: str,
    job_id: str,
    ctx: Context,
    full: bool = False,
) -> str:
    """Get the current status of a DSS job.

    Args:
        full: If true, return the richer summarized job payload; if false, return a lightweight polling shape
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    job_id = _require_non_empty_string(job_id, "job_id")
    await ctx.info(f"Retrieving status for job {job_id} (full={full})...")

    raw_status = await run_blocking(
        lambda: get_dss_client().get_project(project_key).get_job(job_id).get_status()
    )

    payload = (
        _get_job_status_full(project_key, job_id, raw_status)
        if full
        else _get_job_status_brief(project_key, job_id, raw_status)
    )
    return compact_json(payload)


@mcp.tool()
async def get_job_log(
    project_key: str,
    job_id: str,
    ctx: Context,
    activity: str | None = None,
    tail_lines: int | None = 200,
) -> str:
    """Get DSS job logs.

    Args:
        activity: Optional activity ID/name to scope the log to one activity
        tail_lines: If provided, return only the last N log lines
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    job_id = _require_non_empty_string(job_id, "job_id")
    if activity is not None:
        activity = _require_non_empty_string(activity, "activity")
    if tail_lines is not None:
        tail_lines = _require_positive_int(tail_lines, "tail_lines")

    await ctx.info(
        f"Retrieving log for job {job_id}"
        + (f" (activity={activity})" if activity is not None else "")
        + (f", tail_lines={tail_lines}" if tail_lines is not None else ", full log")
        + "..."
    )

    log_text = await run_blocking(
        lambda: get_dss_client()
        .get_project(project_key)
        .get_job(job_id)
        .get_log(activity=activity)
    )
    log_excerpt, line_count, truncated = _tail_log_text(log_text, tail_lines)

    result = {
        "project_key": project_key,
        "job_id": job_id,
        # LEVER 4: omit optional-input echoes when None (no-information);
        # absent is read as "no activity scope" / "full log" by convention.
        **({"activity": activity} if activity is not None else {}),
        **({"tail_lines": tail_lines} if tail_lines is not None else {}),
        "line_count": line_count,
        "truncated": truncated,
        "log": log_excerpt,
    }
    return compact_json(result)


@mcp.tool()
async def list_jobs(project_key: str, limit: int = 10) -> str:
    """List recent DSS jobs in the project.

    Args:
        limit: Maximum number of jobs to return (max 100)
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    limit = _require_positive_int(limit, "limit")
    limit = min(limit, 100)

    raw_jobs = await run_blocking(
        lambda: get_dss_client().get_project(project_key).list_jobs()
    )
    jobs = [_summarize_listed_job(project_key, raw_job) for raw_job in raw_jobs[:limit]]

    return compact_json({
            "project_key": project_key,
            "limit": limit,
            "jobs": columnar(
                jobs,
                [
                    "name",
                    "job_id",
                    "status",
                    "initiator",
                    "type",
                    "initiation_timestamp",
                    "initiation_type",
                ],
            ),
        })


@mcp.tool()
async def wait_for_job(
    project_key: str,
    job_id: str,
    ctx: Context,
    timeout_seconds: int = 600,
) -> str:
    """Wait for a DSS job to finish, with a timeout.

    Args:
        timeout_seconds: Max wait in seconds
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    job_id = _require_non_empty_string(job_id, "job_id")
    timeout_seconds = _require_positive_int(timeout_seconds, "timeout_seconds")

    await ctx.info(f"Waiting for DSS job {job_id} in {project_key}...")

    job = await run_blocking(
        lambda: get_dss_client().get_project(project_key).get_job(job_id)
    )

    timed_out, status_summary = await _wait_for_job_result(project_key, job, timeout_seconds)
    if timed_out:
        return compact_json({
                "status": "job_still_running",
                "job": status_summary,
                "hint": (
                    "The DSS job is still running. Do not assume it failed or start a "
                    "duplicate build; call wait_for_job again or inspect with "
                    "get_job_status. Add full=true only when you need more detail, "
                    "or use get_job_log for logs."
                ),
            })

    top_level_status = "job_completed"
    if status_summary["state"] in {"FAILED", "ABORTED"}:
        top_level_status = "job_completed_with_errors"

    return compact_json({
            "status": top_level_status,
            "job": status_summary,
        })
