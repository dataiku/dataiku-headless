"""dku job — list, run, status, log, abort, wait."""

from __future__ import annotations

import time

import typer

from dku_cli.errors import handle_api_error
from dku_cli.helpers import get_client_from_ctx, resolve_project
from dku_cli.output import console, error, info, render, resolve_output_format, success, warn

app = typer.Typer(help="Manage DSS jobs.")


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
            base = j.get("baseStatus", {})
            data.append({
                "id": base.get("def", {}).get("id", ""),
                "state": base.get("state", ""),
                "initiator": base.get("def", {}).get("initiator", ""),
                "start": base.get("timing", {}).get("startTime", ""),
            })

        render(
            data,
            ["id", "state", "initiator", "start"],
            output_format=output,
            title=f"Jobs ({project_key})",
        )
    except Exception as e:
        handle_api_error(e)


@app.command()
def status(
    ctx: typer.Context,
    job_id: str = typer.Argument(help="Job ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show job status details."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        job = proj.get_job(job_id)
        raw = job.get_status()

        base = raw.get("baseStatus", {})
        data = [
            {"field": "Job ID", "value": job_id},
            {"field": "State", "value": base.get("state", "")},
            {"field": "Initiator", "value": base.get("def", {}).get("initiator", "")},
            {"field": "Start", "value": base.get("timing", {}).get("startTime", "")},
            {"field": "End", "value": base.get("timing", {}).get("endTime", "")},
        ]

        render(data, ["field", "value"], output_format=output, title=f"Job: {job_id}")
    except Exception as e:
        handle_api_error(e)


@app.command()
def log(
    ctx: typer.Context,
    job_id: str = typer.Argument(help="Job ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Show job log output."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        job = proj.get_job(job_id)
        log_text = job.get_log()
        console.print(log_text)
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
_JOB_TYPES = [
    "NON_RECURSIVE_FORCED_BUILD",
    "RECURSIVE_BUILD",
    "RECURSIVE_FORCED_BUILD",
    "RECURSIVE_MISSING_ONLY_BUILD",
]


@app.command()
def run(
    ctx: typer.Context,
    target: list[str] = typer.Option(..., "--target", help="Dataset/object to build (repeatable)"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    job_type: str = typer.Option(
        "NON_RECURSIVE_FORCED_BUILD",
        "--type",
        "-t",
        help="Build type: NON_RECURSIVE_FORCED_BUILD, RECURSIVE_BUILD, RECURSIVE_FORCED_BUILD, RECURSIVE_MISSING_ONLY_BUILD",
    ),
    auto_update_schema: bool = typer.Option(False, "--auto-update-schema", help="Auto-update output schemas before each recipe run"),
    refresh_metastore: bool = typer.Option(False, "--refresh-metastore", help="Refresh Hive metastore after building HDFS datasets"),
    wait_for_completion: bool = typer.Option(False, "--wait", "-w", help="Wait for job completion"),
    timeout: int = typer.Option(0, "--timeout", help="Timeout in seconds when waiting (0 = no limit)"),
) -> None:
    """Run a build job with full control over build type and schema updates.

    Use --type RECURSIVE_BUILD --auto-update-schema to build an entire pipeline
    with automatic schema propagation — no manual schema fixing needed.
    """
    project_key = resolve_project(project)

    if job_type not in _JOB_TYPES:
        error(f"Invalid job type '{job_type}'. Must be one of: {', '.join(_JOB_TYPES)}")
        raise typer.Exit(1)

    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        builder = proj.new_job(job_type)

        for name in target:
            builder.with_output(name)
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
            while True:
                raw = job.get_status()
                state = raw.get("baseStatus", {}).get("state", "")
                if state in _TERMINAL_STATES:
                    if state == "DONE":
                        success(f"Job '{job.id}' completed successfully")
                    else:
                        warn(f"Job '{job.id}' finished with state: {state}")
                    return
                if timeout > 0 and elapsed >= timeout:
                    warn(f"Timed out after {timeout}s — job '{job.id}' still in state: {state}")
                    raise SystemExit(1)
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
    timeout: int = typer.Option(0, "--timeout", "-t", help="Timeout in seconds (0 = no limit)"),
) -> None:
    """Wait for a job to reach a terminal state."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        job = proj.get_job(job_id)

        info(f"Waiting for job '{job_id}' to complete...")
        elapsed = 0.0
        while True:
            raw = job.get_status()
            state = raw.get("baseStatus", {}).get("state", "")
            if state in _TERMINAL_STATES:
                success(f"Job '{job_id}' finished with state: {state}")
                return
            if timeout > 0 and elapsed >= timeout:
                warn(f"Timed out after {timeout}s — job '{job_id}' still in state: {state}")
                raise SystemExit(1)
            time.sleep(2)
            elapsed += 2
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)
