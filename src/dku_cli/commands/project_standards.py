"""dku project-standards — DSS 14.1+ Project Standards checks, scopes, runs.

Compliance semantics: a check run's ``status`` is execution health only.
A compliance failure is expressed as ``result.severity >= 1`` while
``status`` stays ``RUN_SUCCESS`` — never filter on a RUN_FAILURE status
to find violations.
"""

from __future__ import annotations

import typer

from dku_cli.enums import ScopeSelectionMethod
from dku_cli.errors import exit_with_error, handle_api_error
from dku_cli.helpers import get_client_from_ctx, resolve_project
from dku_cli.output import (
    hint,
    info,
    render,
    resolve_output_format,
    success,
    warn,
)

app = typer.Typer(
    help="Manage Project Standards checks, scopes, and compliance runs (DSS 14.1+)."
)


_REPORT_COLUMNS = [
    "check_id",
    "name",
    "status",
    "severity",
    "severity_category",
    "message",
]

_SEVERITY_NAMES = ["SUCCESS", "LOWEST", "LOW", "MEDIUM", "HIGH", "CRITICAL"]


def _severity_category(severity: int | None) -> str:
    if severity is None or severity <= 0 or severity > 5:
        return ""
    return _SEVERITY_NAMES[severity]


def _report_rows(raw_report: dict) -> list[dict]:
    rows = []
    for check_id, run_info in (raw_report.get("bundleChecksRunInfo") or {}).items():
        check = run_info.get("check") or {}
        result = run_info.get("result") or {}
        severity = result.get("severity")
        rows.append(
            {
                "check_id": check_id,
                "name": check.get("name", ""),
                "status": result.get("status", ""),
                "severity": severity if severity is not None else "",
                "severity_category": _severity_category(severity),
                "message": result.get("message", ""),
            }
        )
    return sorted(rows, key=lambda r: r["check_id"])


def _render_report(raw_report: dict, title: str) -> None:
    rows = _report_rows(raw_report)
    render(rows, _REPORT_COLUMNS, output_format=resolve_output_format(), title=title)
    non_compliant = [
        r for r in rows if isinstance(r["severity"], int) and r["severity"] >= 1
    ]
    errored = [r for r in rows if r["status"] == "RUN_ERROR"]
    if non_compliant:
        warn(
            f"{len(non_compliant)} of {len(rows)} checks non-compliant "
            "(severity >= 1; status stays RUN_SUCCESS — status is execution "
            "health, not compliance)."
        )
    elif rows and not errored:
        info(f"All {len(rows)} checks compliant (severity 0).")
    if errored:
        warn(f"{len(errored)} checks failed to execute (status RUN_ERROR).")


@app.command("list-check-specs")
def list_check_specs(ctx: typer.Context) -> None:
    """List check specs available on the instance (plugin components)."""
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        specs = client.get_project_standards().list_check_specs()
        data = [
            {
                "element_type": s.get("elementType", ""),
                "label": s.get("label", ""),
                "owner_plugin_id": s.get("ownerPluginId", ""),
                "description": s.get("description", ""),
            }
            for s in specs
        ]
        render(
            data,
            ["element_type", "label", "owner_plugin_id"],
            output_format=output,
            title="Project Standards check specs",
        )
        hint("dku project-standards create-checks --spec <ELEMENT_TYPE>")
    except Exception as e:
        handle_api_error(e)


@app.command("list-checks")
def list_checks(ctx: typer.Context) -> None:
    """List checks configured on the instance."""
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        checks = client.get_project_standards().list_checks()
        data = [
            {
                "id": c.id,
                "name": c.name,
                "check_element_type": c.check_element_type,
                "description": c.description,
            }
            for c in checks
        ]
        render(
            data,
            ["id", "name", "check_element_type"],
            output_format=output,
            title="Project Standards checks",
        )
        if not data:
            hint("dku project-standards list-check-specs")
    except Exception as e:
        handle_api_error(e)


@app.command("create-checks")
def create_checks(
    ctx: typer.Context,
    spec: list[str] = typer.Option(
        ...,
        "--spec",
        help="Check spec element type to import (repeatable). "
        "Get values from `dku project-standards list-check-specs`.",
    ),
) -> None:
    """Create checks from check specs."""
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        checks = client.get_project_standards().create_checks(spec)
        data = [
            {"id": c.id, "name": c.name, "check_element_type": c.check_element_type}
            for c in checks
        ]
        render(
            data,
            ["id", "name", "check_element_type"],
            output_format=output,
            title="Created checks",
        )
        hint("dku project-standards create-scope --name NAME --check ID --item PROJ")
    except Exception as e:
        handle_api_error(e)


@app.command("list-scopes")
def list_scopes(ctx: typer.Context) -> None:
    """List scopes (which checks run on which projects)."""
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        scopes = client.get_project_standards().list_scopes()
        data = [
            {
                "name": s.get("name", ""),
                "selection_method": s.get("selectionMethod", ""),
                "checks": ",".join(s.get("checks") or []),
                "description": s.get("description", ""),
            }
            for s in scopes
        ]
        render(
            data,
            ["name", "selection_method", "checks"],
            output_format=output,
            title="Project Standards scopes",
        )
    except Exception as e:
        handle_api_error(e)


@app.command("create-scope")
def create_scope(
    ctx: typer.Context,
    name: str = typer.Option(
        ..., "--name", help="Scope name (immutable after creation)"
    ),
    description: str = typer.Option("", "--description", help="Scope description"),
    check: list[str] = typer.Option(
        [],
        "--check",
        help="Check id to include in the scope (repeatable). "
        "Get ids from `dku project-standards list-checks`.",
    ),
    selection_method: ScopeSelectionMethod = typer.Option(
        ScopeSelectionMethod.BY_PROJECT,
        "--selection-method",
        case_sensitive=False,
        help="How the scope selects projects",
    ),
    item: list[str] = typer.Option(
        [],
        "--item",
        help="Selected object id (repeatable). BY_PROJECT: project keys; "
        "BY_FOLDER: folder ids; BY_TAG: tags.",
    ),
) -> None:
    """Create a scope binding checks to projects (by key, folder, or tag)."""
    try:
        client = get_client_from_ctx(ctx)
        scope = client.get_project_standards().create_scope(
            name,
            description=description,
            checks=check,
            selection_method=selection_method.value,
            items=item,
        )
        success(f"Created scope '{scope.name}'")
        hint(f"dku project-standards run -P {item[0] if item else '<PROJECT>'}")
    except Exception as e:
        handle_api_error(e)


@app.command()
def run(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    check_id: list[str] = typer.Option(
        [],
        "--check-id",
        help="Explicit check id to run (repeatable). Default: all checks from "
        "the project's scope. Note: the saved last-report is only updated "
        "when running the full scope (no --check-id).",
    ),
    wait: bool = typer.Option(
        True, "--wait/--no-wait", help="Wait for the run and print the report"
    ),
) -> None:
    """Run Project Standards checks on a project.

    A non-compliant check reports severity >= 1 while its status stays
    RUN_SUCCESS (status is execution health, not compliance).
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        future = proj.start_run_project_standards_checks(check_ids=check_id or None)
        if not wait:
            success(
                f"Started Project Standards run on {project_key} (job {future.job_id})"
            )
            hint(f"dku project-standards last-report -P {project_key}")
            return
        report = future.wait_for_result()
        _render_report(report.data, f"Project Standards report ({project_key})")
    except Exception as e:
        handle_api_error(e, project_key=project_key)


@app.command("last-report")
def last_report(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Show the latest saved Project Standards report for a project."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        report = client.get_project(project_key).get_project_standards_last_report()
        if report is None:
            exit_with_error(
                f"No Project Standards report exists for {project_key}.",
                details=[
                    "Checks have never been run on this project with its scope.",
                    f"Run them: dku project-standards run -P {project_key}",
                ],
            )
        _render_report(report.data, f"Last Project Standards report ({project_key})")
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e, project_key=project_key)
