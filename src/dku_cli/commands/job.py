"""dku job — list, run, status, log, abort, wait."""

from __future__ import annotations

import time
from datetime import datetime, timezone

import typer

from dku_cli.enums import JobType
from dku_cli.errors import handle_api_error
from dku_cli.helpers import (
    get_client_from_ctx,
    resolve_build_output_types,
    resolve_project,
)
from dku_cli.output import (
    console,
    error,
    info,
    print_text,
    render,
    resolve_output_format,
    success,
    warn,
)


def _format_epoch_ms(value) -> str:
    """Format an epoch-ms timestamp as UTC ISO string. Empty on missing/bad input."""
    try:
        ts = int(value)
    except (TypeError, ValueError):
        return ""
    if ts <= 0:
        return ""
    return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S UTC"
    )


def _format_duration_ms(start, end) -> str:
    """Return human-readable duration between two epoch-ms timestamps."""
    try:
        s, e = int(start), int(end)
    except (TypeError, ValueError):
        return ""
    if s <= 0 or e <= 0 or e < s:
        return ""
    seconds = (e - s) / 1000
    if seconds < 60:
        return f"{seconds:.1f}s"
    m, s = divmod(int(seconds), 60)
    if m < 60:
        return f"{m}m {s}s"
    h, m = divmod(m, 60)
    return f"{h}h {m}m"


app = typer.Typer(help="Manage DSS jobs.")

_ERROR_MARKERS = (
    "error",
    "exception",
    "traceback",
    "failed",
)


def _tail_lines(text: str, count: int) -> str:
    """Return the last *count* lines from *text*."""
    if count <= 0:
        return ""
    lines = text.splitlines()
    return "\n".join(lines[-count:])


def _grep_lines(text: str, pattern: str) -> str:
    """Return only lines matching *pattern* (case-insensitive substring match)."""
    if not pattern:
        return text
    lines = text.splitlines()
    lower = pattern.lower()
    matched = [line for line in lines if lower in line.lower()]
    return "\n".join(matched)


def _filter_error_lines(text: str, context: int = 1) -> str:
    """Return error-like lines with a small amount of surrounding context.

    DSS job logs are plain text and not strongly structured, so this is
    intentionally heuristic: keep lines containing common failure markers plus a
    few surrounding lines to preserve traceback readability.
    """
    lines = text.splitlines()
    if not lines:
        return ""

    selected: set[int] = set()
    for idx, line in enumerate(lines):
        lowered = line.lower()
        if any(marker in lowered for marker in _ERROR_MARKERS):
            start = max(0, idx - context)
            end = min(len(lines), idx + context + 1)
            selected.update(range(start, end))

    if not selected:
        return ""

    ordered = sorted(selected)
    chunks: list[str] = []
    previous: int | None = None
    for idx in ordered:
        if previous is not None and idx != previous + 1:
            chunks.append("...")
        chunks.append(lines[idx])
        previous = idx
    return "\n".join(chunks)


@app.command("list")
def list_jobs(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max jobs to show"),
) -> None:
    """List recent jobs."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        jobs = proj.list_jobs()

        data = []
        for j in jobs[:limit]:
            # list_jobs() returns top-level fields (state, def.id, startTime),
            # NOT nested under baseStatus (that's only from get_status()).
            job_def = j.get("def", {})
            data.append(
                {
                    "id": job_def.get("id", ""),
                    "state": j.get("state", ""),
                    "initiator": job_def.get("initiator", ""),
                    "start": j.get("startTime", ""),
                }
            )

        render(
            data,
            ["id", "state", "initiator", "start"],
            output_format=output,
            title=f"Jobs ({project_key})",
        )
    except Exception as e:
        handle_api_error(e)


@app.command()
def last(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(
        None,
        "-o",
        "--output",
        help="Output format: plain id (default), 'table', or 'json'",
    ),
) -> None:
    """Show the most recent job id (shortcut for 'dku job list | .[0]').

    Default output is the plain job id on stdout — designed for shell
    capture: ``dku job log $(dku job last -P PROJ) -P PROJ``.

    Pass ``-o json`` to get the full job record (id, state, initiator,
    start time) or ``-o table`` for a single-row table.
    """
    project_key = resolve_project(project)
    # Do NOT call resolve_output_format here — we want the unset default
    # to be "plain id on stdout", not the configured "table" fallback.
    fmt = output.lower() if output else "plain"
    if fmt not in ("plain", "table", "json"):
        raise typer.BadParameter("Output format must be one of: plain, table, json")
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        jobs = proj.list_jobs()
        if not jobs:
            error(
                f"No jobs found in project {project_key}. "
                f"Run a recipe first: dku recipe run RECIPE -P {project_key} --wait"
            )
            raise typer.Exit(1)
        j = jobs[0]
        job_def = j.get("def", {})
        record = {
            "id": job_def.get("id", ""),
            "state": j.get("state", ""),
            "initiator": job_def.get("initiator", ""),
            "start": j.get("startTime", ""),
        }
        if fmt == "json":
            from dku_cli.output import render_raw

            render_raw(record, output_format="json")
        elif fmt == "table":
            render(
                [record],
                ["id", "state", "initiator", "start"],
                output_format="table",
                title=f"Most recent job ({project_key})",
            )
        else:
            # Plain id on stdout — composable with $(dku job last -P PROJ)
            console.print(record["id"], highlight=False)
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def status(
    ctx: typer.Context,
    job_id: str = typer.Argument(
        help="Job ID (positional — pass it as the first argument, not via -j)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show job status details.

    Job ID is positional. Example: `dku job status 2026-04-27-123 -P PROJ`.
    """
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        job = proj.get_job(job_id)
        raw = job.get_status()

        base = raw.get("baseStatus", {})
        state = base.get("state", "")
        start_ms = base.get("jobStartTime")
        end_ms = base.get("jobEndTime")
        error_msg = raw.get("errorMessage") or (raw.get("error") or {}).get(
            "message", ""
        )

        data = [
            {"field": "Job ID", "value": job_id},
            {"field": "State", "value": state},
            {"field": "Initiator", "value": base.get("def", {}).get("initiator", "")},
            {"field": "Start", "value": _format_epoch_ms(start_ms)},
            {"field": "End", "value": _format_epoch_ms(end_ms)},
            {"field": "Duration", "value": _format_duration_ms(start_ms, end_ms)},
        ]
        if state == "FAILED" and error_msg:
            data.append({"field": "Error", "value": error_msg})

        render(data, ["field", "value"], output_format=output, title=f"Job: {job_id}")

        if state == "FAILED" and output != "json":
            info(f"Debug with: dku job log {job_id} -P {project_key}")
    except Exception as e:
        handle_api_error(e)


@app.command()
def log(
    ctx: typer.Context,
    job_id: str = typer.Argument(help="Job ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    grep: str | None = typer.Option(
        None, "--grep", help="Show only lines containing this text (case-insensitive)"
    ),
    tail: int | None = typer.Option(
        None, "--tail", help="Show only the last N log lines"
    ),
    errors_only: bool = typer.Option(
        False,
        "--errors-only",
        help="Show only error-like log lines plus nearby context",
    ),
) -> None:
    """Show job log output."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        job = proj.get_job(job_id)
        log_text = job.get_log()
        if errors_only:
            filtered = _filter_error_lines(log_text)
            if filtered:
                log_text = filtered
            else:
                warn(
                    "No error-like lines found in the job log. Showing the original log."
                )
        if grep:
            log_text = _grep_lines(log_text, grep)
            if not log_text:
                warn(f"No lines matching '{grep}' found in the job log.")
                return
        if tail is not None:
            log_text = _tail_lines(log_text, tail)
        print_text(log_text)
    except Exception as e:
        handle_api_error(e)


@app.command()
def abort(
    ctx: typer.Context,
    job_id: str = typer.Argument(help="Job ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Abort a running job."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        job = proj.get_job(job_id)
        job.abort()
        success(f"Abort requested for job '{job_id}'")
    except Exception as e:
        handle_api_error(e)


_TERMINAL_STATES = {"DONE", "FAILED", "ABORTED"}

# After this long in a non-terminal state, surface the containerized-recipe
# trap once: on a full K8s quota the pod never schedules, the job spins in
# RUNNING forever and locks its output dataset.
_LONG_RUNNING_HINT_SECS = 180


def _emit_long_running_hint(job_id: str, project_key: str, elapsed: float) -> None:
    warn(
        f"Job '{job_id}' still not finished after {int(elapsed)}s. If the recipe "
        "is containerized, it may be stuck unschedulable on a full K8s quota."
    )
    info(
        f"Inspect: dku job log {job_id} -P {project_key} --tail 50 · "
        f"abort: dku job abort {job_id} -P {project_key} · run locally: "
        "dku recipe set-definition RECIPE --definition "
        '\'{"params":{"containerSelection":{"containerMode":"NONE"}}}\''
    )


@app.command()
def run(
    ctx: typer.Context,
    target: list[str] = typer.Option(
        ...,
        "--target",
        help="Object to build — dataset name, managed folder (name or ID), or saved model (name or ID). Type is auto-detected. Repeatable.",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    job_type: JobType = typer.Option(
        JobType.NON_RECURSIVE_FORCED_BUILD,
        "--type",
        "-t",
        case_sensitive=False,
        help="Build type: NON_RECURSIVE_FORCED_BUILD, RECURSIVE_BUILD, RECURSIVE_FORCED_BUILD, RECURSIVE_MISSING_ONLY_BUILD",
    ),
    auto_update_schema: bool = typer.Option(
        False,
        "--auto-update-schema",
        help="Auto-update output schemas before each recipe run",
    ),
    refresh_metastore: bool = typer.Option(
        False,
        "--refresh-metastore",
        help="Refresh Hive metastore after building HDFS datasets",
    ),
    wait_for_completion: bool = typer.Option(
        False, "--wait", "-w", help="Wait for job completion"
    ),
    timeout: int = typer.Option(
        0, "--timeout", help="Timeout in seconds when waiting (0 = no limit)"
    ),
) -> None:
    """Run a build job with full control over build type and schema updates.

    Use --type RECURSIVE_BUILD --auto-update-schema to build an entire pipeline
    with automatic schema propagation — no manual schema fixing needed.
    """
    project_key = resolve_project(project)

    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        builder = proj.new_job(job_type)

        # JobDefinitionBuilder.with_output defaults object_type to DATASET, so a
        # managed-folder / saved-model target would error with "dataset does not
        # exist". Resolve each target's real type (and names to IDs) first.
        for resolved_ref, object_type in resolve_build_output_types(proj, target):
            builder.with_output(resolved_ref, object_type=object_type)
        if auto_update_schema:
            builder.with_auto_update_schema_before_each_recipe_run(True)
        if refresh_metastore:
            builder.with_refresh_metastore(True)

        job = builder.start()
        success(f"Job started: {job.id}")
        info(f"Type: {job_type}, Targets: {', '.join(target)}")
        if auto_update_schema:
            info("Auto-update schema: enabled")

        if wait_for_completion:
            info("Waiting for completion...")
            elapsed = 0.0
            hinted = False
            while True:
                raw = job.get_status()
                state = raw.get("baseStatus", {}).get("state", "")
                if state in _TERMINAL_STATES:
                    if state == "DONE":
                        success(f"Job '{job.id}' completed successfully")
                        return
                    # FAILED/ABORTED must exit non-zero — agents chain
                    # `job run --wait && next-step`; exit 0 here would let the
                    # chain march on past a failed build.
                    warn(f"Job '{job.id}' finished with state: {state}")
                    info(f"Inspect why: dku job log {job.id} -P {project_key}")
                    raise SystemExit(1)
                if timeout > 0 and elapsed >= timeout:
                    warn(
                        f"Timed out after {timeout}s — job '{job.id}' still in state: {state}"
                    )
                    raise SystemExit(1)
                if not hinted and elapsed >= _LONG_RUNNING_HINT_SECS:
                    hinted = True
                    _emit_long_running_hint(job.id, project_key, elapsed)
                time.sleep(2)
                elapsed += 2
    except SystemExit:
        raise
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def wait(
    ctx: typer.Context,
    job_id: str = typer.Argument(help="Job ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    timeout: int = typer.Option(
        0, "--timeout", "-t", help="Timeout in seconds (0 = no limit)"
    ),
) -> None:
    """Wait for a job to reach a terminal state."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        job = proj.get_job(job_id)

        info(f"Waiting for job '{job_id}' to complete...")
        elapsed = 0.0
        hinted = False
        while True:
            raw = job.get_status()
            state = raw.get("baseStatus", {}).get("state", "")
            if state in _TERMINAL_STATES:
                if state == "DONE":
                    success(f"Job '{job_id}' finished with state: {state}")
                    return
                warn(f"Job '{job_id}' finished with state: {state}")
                info(f"Inspect why: dku job log {job_id} -P {project_key}")
                raise SystemExit(1)
            if timeout > 0 and elapsed >= timeout:
                warn(
                    f"Timed out after {timeout}s — job '{job_id}' still in state: {state}"
                )
                raise SystemExit(1)
            if not hinted and elapsed >= _LONG_RUNNING_HINT_SECS:
                hinted = True
                _emit_long_running_hint(job_id, project_key, elapsed)
            time.sleep(2)
            elapsed += 2
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)
