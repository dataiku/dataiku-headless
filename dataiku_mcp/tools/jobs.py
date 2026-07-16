"""Inspection tools for DSS jobs and futures."""

import asyncio
import time

from dataikuapi.dss.future import DSSFuture
from fastmcp import Context

from .. import mcp
from .utils.async_executor import run_blocking
from .utils.auth import get_dss_client
from .utils.job_summaries import (
    get_job_status_brief as _get_job_status_brief,
    get_job_status_full as _get_job_status_full,
    summarize_listed_job as _summarize_listed_job,
)
from .utils.serialization import columnar, compact_json
from .utils.validation import (
    require_non_empty_string as _require_non_empty_string,
    require_positive_int as _require_positive_int,
)

JOB_POLL_INTERVAL_SECONDS = 2
TERMINAL_JOB_STATES = {"DONE", "FAILED", "ABORTED"}


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
async def get_future_status(
    future_id: str,
    ctx: Context,
    fetch_result: bool = False,
) -> str:
    """Get the status of a DSSFuture returned by a long-running DSS operation."""
    future_id = _require_non_empty_string(future_id, "future_id")
    await ctx.info(
        f"Retrieving DSS future status for {future_id} "
        f"(fetch_result={fetch_result})..."
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
    """Get the current status of a DSS job."""
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
    """Get DSS job logs."""
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
        **({"activity": activity} if activity is not None else {}),
        **({"tail_lines": tail_lines} if tail_lines is not None else {}),
        "line_count": line_count,
        "truncated": truncated,
        "log": log_excerpt,
    }
    return compact_json(result)


@mcp.tool()
async def list_jobs(project_key: str, limit: int = 10) -> str:
    """List recent DSS jobs in the project."""
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
    """Wait for a DSS job to finish, with a timeout."""
    project_key = _require_non_empty_string(project_key, "project_key")
    job_id = _require_non_empty_string(job_id, "job_id")
    timeout_seconds = _require_positive_int(timeout_seconds, "timeout_seconds")
    await ctx.info(f"Waiting for DSS job {job_id} in {project_key}...")

    job = await run_blocking(
        lambda: get_dss_client().get_project(project_key).get_job(job_id)
    )
    timed_out, status_summary = await _wait_for_job_result(
        project_key, job, timeout_seconds
    )
    if timed_out:
        return compact_json(
            {
                "status": "job_still_running",
                "job": status_summary,
                "hint": (
                    "The DSS job is still running. Do not assume it failed or start a "
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
