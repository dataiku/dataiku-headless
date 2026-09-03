# Copyright 2026 Dataiku
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Inspection tools for Dataiku jobs and futures."""

import asyncio
import time

from dataikuapi.dss.future import DSSFuture
from fastmcp import Context

from .. import mcp
from .utils.async_executor import run_blocking
from .utils.auth import get_dss_client
from .utils.errors import safe_error_text as _safe_error_text
from .utils.job_summaries import (
    get_job_status_brief as _get_job_status_brief,
    get_job_status_full as _get_job_status_full,
    summarize_listed_job as _summarize_listed_job,
)
from .utils.serialization import columnar, compact_json
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
MAX_INLINE_WAIT_SECONDS = 3600
MAX_DATASETS_PER_BUILD = 100
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


class _RecipeExecutionPrecondition(ValueError):
    """The recipe cannot be mapped to a supported Dataiku job output."""


def _validate_inline_timeout(timeout_seconds: int) -> int:
    timeout_seconds = _require_positive_int(timeout_seconds, "timeout_seconds")
    if timeout_seconds > MAX_INLINE_WAIT_SECONDS:
        raise ValueError(f"'timeout_seconds' must be <= {MAX_INLINE_WAIT_SECONDS}")
    return timeout_seconds


async def _wait_for_job_result(
    project_key: str,
    job,
    timeout_seconds: int,
    job_id: str | None = None,
) -> tuple[bool, dict]:
    # Use the caller-captured id so polling never depends on reading job.id again.
    deadline = time.monotonic() + timeout_seconds
    while True:
        raw_status = await run_blocking(job.get_status)
        summary = _get_job_status_full(project_key, job_id, raw_status)
        if summary["state"] in TERMINAL_JOB_STATES or (
            isinstance(summary.get("end_time"), int) and summary["end_time"] > 0
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


def _per_dataset_outcomes(dataset_names: list[str], status_summary: dict) -> list[dict]:
    """Map requested datasets to the state of the activity that produces them. Datasets with no matching activity yet report ``state: null``."""
    state_by_ref: dict[str, str | None] = {}
    for activity in status_summary.get("activities", []) or []:
        for output in activity.get("outputs", []) or []:
            ref = output.get("ref")
            if ref:
                state_by_ref[ref] = activity.get("state")
    return [
        {"dataset": name, "state": state_by_ref.get(name)} for name in dataset_names
    ]


@mcp.tool()
async def build_datasets(
    project_key: str,
    ctx: Context,
    dataset_names: list[str],
    wait_for_completion: bool = False,
    job_type: str = "NON_RECURSIVE_FORCED_BUILD",
    auto_update_schema: bool = True,
    timeout_seconds: int = DEFAULT_WAIT_TIMEOUT_SECONDS,
) -> str:
    """Build one or more existing datasets as a single Dataiku job.

    Args:
        dataset_names: Existing dataset names to build (at least one). All requested datasets are started in one job.
        wait_for_completion: If true, wait up to timeout_seconds for the job to finish; if false, start it and return the job_id.
        job_type: One of NON_RECURSIVE_FORCED_BUILD, RECURSIVE_BUILD, RECURSIVE_FORCED_BUILD.
        auto_update_schema: Whether to auto-update output schemas before each recipe run.
        timeout_seconds: Max time for the inline wait when wait_for_completion=true. This is a soft timeout checked between status polls.
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    names = _require_non_empty_list(dataset_names, "dataset_names")
    names = [
        _require_non_empty_string(name, f"dataset_names[{i}]")
        for i, name in enumerate(names)
    ]
    job_type = _require_allowed_value(job_type, "job_type", VALID_JOB_TYPES)
    if len(names) > MAX_DATASETS_PER_BUILD:
        raise ValueError(
            f"'dataset_names' must contain at most {MAX_DATASETS_PER_BUILD} items"
        )
    if len(set(names)) != len(names):
        raise ValueError("'dataset_names' must not contain duplicates")
    timeout_seconds = _validate_inline_timeout(timeout_seconds)
    client = get_dss_client()

    await ctx.info(
        f"Starting build of {len(names)} dataset(s) in {project_key} as one job "
        f"({job_type}, wait_for_completion={wait_for_completion}, "
        f"auto_update_schema={auto_update_schema})..."
    )

    def _start_job():
        project = client.get_project(project_key)
        builder = project.new_job(job_type)
        for target_dataset_name in names:
            builder.with_output(target_dataset_name)
        if auto_update_schema:
            builder.with_auto_update_schema_before_each_recipe_run(True)
        return builder.start()

    try:
        job = await run_blocking(_start_job)
    except Exception as exc:
        raise RuntimeError(
            "Dataiku did not return a job handle for this build. Inspect recent jobs "
            "before retrying because the start request may have reached Dataiku."
        ) from exc

    try:
        job_id = job.id
    except Exception:
        job_id = None

    if not wait_for_completion:
        return compact_json(
            {
                "status": "build_started",
                "project_key": project_key,
                "job_id": job_id,
                "datasets": names,
                "hint": (
                    "Build started. Wait explicitly with "
                    "wait_for_job(project_key, job_id, timeout_seconds=...) or poll "
                    "get_job_status(project_key, job_id); use get_job_log for logs."
                ),
            }
        )

    try:
        timed_out, status_summary = await _wait_for_job_result(
            project_key,
            job,
            timeout_seconds,
            job_id,
        )
    except Exception as exc:
        return compact_json(
            {
                "status": "build_poll_failed",
                "project_key": project_key,
                **({"job_id": job_id} if job_id is not None else {}),
                "datasets": names,
                "error_type": type(exc).__name__,
                "error": _safe_error_text(exc),
                "hint": (
                    "The build job started but status polling failed. Keep this "
                    "job_id and inspect it with get_job_status or wait_for_job; "
                    "do not start a replacement build."
                ),
            }
        )
    per_dataset = _per_dataset_outcomes(names, status_summary)

    if timed_out:
        return compact_json(
            {
                "status": "build_still_running",
                "project_key": project_key,
                "job_id": job_id,
                "datasets": names,
                "per_dataset": per_dataset,
                "status_summary": status_summary,
                "hint": (
                    "The build job is still running. Do not start another build for "
                    "these flow objects. Use wait_for_job(project_key, job_id, "
                    "timeout_seconds=...) or get_job_status(project_key, job_id). Add "
                    "full=true only when you need more detail, or use "
                    "get_job_log(project_key, job_id) for logs."
                ),
            }
        )

    top_level_status = "build_completed"
    if status_summary["state"] in {"FAILED", "ABORTED"}:
        top_level_status = "build_completed_with_errors"

    return compact_json(
        {
            "status": top_level_status,
            "project_key": project_key,
            "job_id": job_id,
            "datasets": names,
            "per_dataset": per_dataset,
            "status_summary": status_summary,
        }
    )


@mcp.tool()
async def run_recipe(
    project_key: str,
    recipe_name: str,
    ctx: Context,
    wait_for_completion: bool = False,
    job_type: str = "NON_RECURSIVE_FORCED_BUILD",
    auto_update_schema: bool = True,
    timeout_seconds: int = DEFAULT_WAIT_TIMEOUT_SECONDS,
) -> str:
    """Run an existing recipe by building its first output as the trigger target.

    Args:
        wait_for_completion: If true, wait up to timeout_seconds for the job to finish; if false, start it and return the job_id.
        job_type: One of NON_RECURSIVE_FORCED_BUILD, RECURSIVE_BUILD, RECURSIVE_FORCED_BUILD.
        auto_update_schema: Whether to auto-update output schemas before each recipe run.
        timeout_seconds: Max time for the inline wait when wait_for_completion=true. This is a soft timeout checked between status polls.
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    recipe_name = _require_non_empty_string(recipe_name, "recipe_name")
    job_type = _require_allowed_value(job_type, "job_type", VALID_JOB_TYPES)
    timeout_seconds = _validate_inline_timeout(timeout_seconds)
    client = get_dss_client()

    await ctx.info(
        f"Running recipe {recipe_name} in {project_key} "
        f"({job_type}, wait_for_completion={wait_for_completion}, "
        f"auto_update_schema={auto_update_schema})..."
    )

    def _run():
        project = client.get_project(project_key)
        recipe = project.get_recipe(recipe_name)

        # We do not use DSSRecipe.run() directly. Instead we trigger the recipe by
        # building its first output object, so that auto_update_schema can attach to
        # the job builder (this prevents e.g. scoring recipes from building datasets
        # with an empty schema).
        outputs = project.get_flow().get_graph().get_successor_computables(recipe)
        if not outputs:
            raise _RecipeExecutionPrecondition(
                f"recipe '{recipe_name}' has no outputs, so Dataiku cannot run it"
            )

        first_output = outputs[0]
        object_type = COMPUTABLE_TO_JOB_OUTPUT_TYPE.get(first_output.get("type"))
        if object_type is None:
            raise _RecipeExecutionPrecondition(
                f"recipe '{recipe_name}' has unsupported output type "
                f"{first_output.get('type')}, can't run it"
            )

        builder = project.new_job(job_type)
        builder.with_output(first_output["ref"], object_type=object_type)
        if auto_update_schema:
            builder.with_auto_update_schema_before_each_recipe_run(True)
        return builder.start()

    try:
        job = await run_blocking(_run)
    except _RecipeExecutionPrecondition:
        raise
    except Exception as exc:
        raise RuntimeError(
            f"Dataiku did not return a job handle for recipe '{recipe_name}'. Inspect "
            "recent jobs before retrying because the start request may have "
            "reached Dataiku."
        ) from exc

    try:
        job_id = job.id
    except Exception:
        job_id = None

    if not wait_for_completion:
        return compact_json(
            {
                "status": "recipe_run_started",
                "project_key": project_key,
                "recipe": recipe_name,
                "job_id": job_id,
                "hint": (
                    "Recipe run started. Wait explicitly with "
                    "wait_for_job(project_key, job_id, timeout_seconds=...) or poll "
                    "get_job_status(project_key, job_id); use get_job_log for logs."
                ),
            }
        )

    try:
        timed_out, status_summary = await _wait_for_job_result(
            project_key,
            job,
            timeout_seconds,
            job_id,
        )
    except Exception as exc:
        return compact_json(
            {
                "status": "recipe_poll_failed",
                "project_key": project_key,
                "recipe": recipe_name,
                **({"job_id": job_id} if job_id is not None else {}),
                "error_type": type(exc).__name__,
                "error": _safe_error_text(exc),
                "hint": (
                    "The recipe job started but status polling failed. Keep this "
                    "job_id and inspect it with get_job_status or wait_for_job; "
                    "do not run the recipe again."
                ),
            }
        )
    if timed_out:
        return compact_json(
            {
                "status": "recipe_run_still_running",
                "project_key": project_key,
                "recipe": recipe_name,
                "job_id": job_id,
                "status_summary": status_summary,
                "hint": (
                    "Do not start another build for this recipe or its outputs while "
                    "this job is still running. Use wait_for_job(project_key, job_id, "
                    "timeout_seconds=...) or get_job_status(project_key, job_id). Add "
                    "full=true only when you need more detail, or use "
                    "get_job_log(project_key, job_id) for logs."
                ),
            }
        )

    top_level_status = "recipe_run_completed"
    if status_summary["state"] in {"FAILED", "ABORTED"}:
        top_level_status = "recipe_run_completed_with_errors"

    return compact_json(
        {
            "status": top_level_status,
            "status_summary": status_summary,
            "project_key": project_key,
            "recipe": recipe_name,
            "job_id": job_id,
        }
    )


@mcp.tool()
async def get_future_status(
    future_id: str,
    ctx: Context,
    fetch_result: bool = False,
) -> str:
    """Get the status of a DSSFuture returned by a long-running Dataiku operation."""
    future_id = _require_non_empty_string(future_id, "future_id")
    await ctx.info(
        f"Retrieving Dataiku future status for {future_id} (fetch_result={fetch_result})..."
    )

    def _run():
        future = DSSFuture(get_dss_client(), future_id)
        state = future.get_state() if fetch_result else future.peek_state()
        return {"future_id": future_id, "state": state}

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def get_job_status(
    project_key: str,
    job_id: str,
    ctx: Context,
    full: bool = False,
) -> str:
    """Get the current status of a Dataiku job."""
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
    """Get Dataiku job logs."""
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
        lambda: (
            get_dss_client()
            .get_project(project_key)
            .get_job(job_id)
            .get_log(activity=activity)
        )
    )
    log_excerpt, line_count, truncated = _tail_log_text(log_text, tail_lines)
    result = {
        "project_key": project_key,
        "job_id": job_id,
        **({"activity": activity} if activity is not None else {}),
        **({"tail_lines": tail_lines} if tail_lines is not None else {}),
        "line_count": line_count,
        "truncated": truncated,
        "log": log_excerpt,
    }
    return compact_json(result)


@mcp.tool()
async def list_jobs(project_key: str, limit: int = 10) -> str:
    """List recent Dataiku jobs in the project."""
    project_key = _require_non_empty_string(project_key, "project_key")
    limit = min(_require_positive_int(limit, "limit"), 100)

    raw_jobs = await run_blocking(
        lambda: get_dss_client().get_project(project_key).list_jobs()
    )
    jobs = [_summarize_listed_job(project_key, raw_job) for raw_job in raw_jobs[:limit]]
    return compact_json(
        {
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
        }
    )


@mcp.tool()
async def wait_for_job(
    project_key: str,
    job_id: str,
    ctx: Context,
    timeout_seconds: int = 600,
) -> str:
    """Wait for a Dataiku job to finish, with a timeout."""
    project_key = _require_non_empty_string(project_key, "project_key")
    job_id = _require_non_empty_string(job_id, "job_id")
    timeout_seconds = _require_positive_int(timeout_seconds, "timeout_seconds")
    await ctx.info(f"Waiting for Dataiku job {job_id} in {project_key}...")

    job = await run_blocking(
        lambda: get_dss_client().get_project(project_key).get_job(job_id)
    )
    timed_out, status_summary = await _wait_for_job_result(
        project_key, job, timeout_seconds, job_id
    )
    if timed_out:
        return compact_json(
            {
                "status": "job_still_running",
                "job": status_summary,
                "hint": (
                    "The Dataiku job is still running. Do not assume it failed or start a "
                    "duplicate build; call wait_for_job again or inspect with "
                    "get_job_status. Add full=true only when you need more detail, "
                    "or use get_job_log for logs."
                ),
            }
        )

    top_level_status = "job_completed"
    if status_summary["state"] in {"FAILED", "ABORTED"}:
        top_level_status = "job_completed_with_errors"
    return compact_json({"status": top_level_status, "job": status_summary})
