"""Project-scoped Project Standards reports and execution."""

from __future__ import annotations

import typer

from dku_cli.enums import ProjectStandardsSeverity
from dku_cli.errors import exit_with_error, handle_errors
from dku_cli.helpers import get_client_from_ctx, resolve_project
from dku_cli.output import hint, render_raw, resolve_output_format, success, warn

from ._common import app, render_report, validate_check_ids

SEVERITY_VALUES = {
    ProjectStandardsSeverity.LOWEST: 1,
    ProjectStandardsSeverity.LOW: 2,
    ProjectStandardsSeverity.MEDIUM: 3,
    ProjectStandardsSeverity.HIGH: 4,
    ProjectStandardsSeverity.CRITICAL: 5,
}


@app.command("project-scope")
@handle_errors
def project_scope(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Show which scope currently applies to a project."""
    project_key = resolve_project(project)
    client = get_client_from_ctx(ctx)
    scope = client.get_project(project_key).get_project_standards_scope()
    render_raw(
        {"project": project_key, "scope": scope},
        output_format=resolve_output_format(),
    )


@app.command()
@handle_errors
def run(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    check_id: list[str] = typer.Option(
        [],
        "--check-id",
        "--check",
        help="Explicit check id (repeatable); explicit runs do not save last-report",
    ),
    wait: bool = typer.Option(
        True, "--wait/--no-wait", help="Wait for completion and print the report"
    ),
    fail_at: ProjectStandardsSeverity | None = typer.Option(
        None,
        "--fail-at",
        case_sensitive=False,
        help="Exit 1 when a finding reaches this severity (inclusive)",
    ),
) -> None:
    """Run checks; optionally turn findings into a CI exit code."""
    if fail_at is not None and not wait:
        exit_with_error(
            "--fail-at requires --wait.",
            details=["Remove --no-wait so the result can be evaluated."],
        )
    project_key = resolve_project(project)
    client = get_client_from_ctx(ctx)
    standards = client.get_project_standards()
    validate_check_ids(standards, check_id)
    future = client.get_project(project_key).start_run_project_standards_checks(
        check_ids=check_id or None
    )
    if not wait:
        success(f"Started Project Standards run on {project_key} (job {future.job_id})")
        if not check_id:
            hint(f"dku project-standards last-report -P {project_key}")
        return
    report = future.wait_for_result()
    rows = render_report(
        report.data,
        resolve_output_format(),
        f"Project Standards report ({project_key})",
    )
    if check_id:
        warn("Explicit-check runs are diagnostic and do not update last-report.")
    _enforce_report(rows, fail_at)
    success(f"Completed Project Standards for project '{project_key}'")


@app.command("last-report")
@handle_errors
def last_report(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Show the latest saved scoped report for a project."""
    project_key = resolve_project(project)
    client = get_client_from_ctx(ctx)
    report = client.get_project(project_key).get_project_standards_last_report()
    if report is None:
        exit_with_error(
            f"No Project Standards report exists for {project_key}.",
            details=[
                "Explicit-check runs are not saved.",
                f"Create one: dku project-standards run -P {project_key}",
            ],
        )
    render_report(
        report.data,
        resolve_output_format(),
        f"Last Project Standards report ({project_key})",
    )


def _enforce_report(rows: list[dict], fail_at: ProjectStandardsSeverity | None) -> None:
    run_errors = [row for row in rows if row["status"] == "RUN_ERROR"]
    if run_errors:
        exit_with_error(
            f"{len(run_errors)} Project Standards check(s) failed to execute.",
            details=["Inspect the report rows above, fix the check, and re-run."],
        )
    if fail_at is None:
        return
    threshold = SEVERITY_VALUES[fail_at]
    findings = [
        row
        for row in rows
        if isinstance(row["severity"], int) and row["severity"] >= threshold
    ]
    if findings:
        exit_with_error(
            f"{len(findings)} finding(s) reached --fail-at {fail_at.value}.",
            details=["Inspect the report rows above, remediate, and re-run."],
        )
