"""Shared Project Standards rendering, validation, and safety helpers."""

from __future__ import annotations

import json

import typer

from dku_cli.errors import exit_with_error
from dku_cli.helpers import object_write_lock
from dku_cli.output import info, render, render_raw, warn
from dku_cli.safety import Tier, guard

app = typer.Typer(
    help="Manage Project Standards checks, scopes, and compliance runs (DSS 14.1+)."
)

REPORT_COLUMNS = [
    "check_id",
    "name",
    "status",
    "severity",
    "severity_category",
    "message",
]
SEVERITY_NAMES = ["SUCCESS", "LOWEST", "LOW", "MEDIUM", "HIGH", "CRITICAL"]


def policy_write_lock(client):
    return object_write_lock(
        client,
        "instance",
        "project-standards-policy",
        "instance",
    )


def guard_admin(
    ctx: typer.Context,
    *,
    action: str,
    subject: str,
    target_id: str,
    yes: bool,
    confirm_name: str | None,
    i_know: bool,
) -> None:
    guard(
        ctx,
        tier=Tier.ADMIN,
        action=action,
        subject=subject,
        yes=yes,
        target_id=target_id,
        confirm_name=confirm_name,
        i_know=i_know,
    )


def render_check_specs(specs: list[dict], output: str) -> None:
    rows = [
        {
            "element_type": spec.get("elementType", ""),
            "label": spec.get("label", ""),
            "owner_plugin_id": spec.get("ownerPluginId", ""),
            "description": spec.get("description", ""),
            "parameters": spec.get("parameters", []) or [],
        }
        for spec in specs
    ]
    render(
        rows,
        ["element_type", "label", "owner_plugin_id", "description", "parameters"],
        output_format=output,
        title="Project Standards check specs",
    )


def render_checks(checks: list, output: str, *, title: str) -> None:
    rows = []
    for check in checks:
        raw = check.get_raw()
        rows.append(
            {
                "id": raw.get("id", ""),
                "name": raw.get("name", ""),
                "check_element_type": raw.get("checkElementType", ""),
                "description": raw.get("description", ""),
                "check_params": raw.get("checkParams", {}) or {},
                "tags": raw.get("tags", []) or [],
            }
        )
    render(
        rows,
        [
            "id",
            "name",
            "check_element_type",
            "description",
            "check_params",
            "tags",
        ],
        output_format=output,
        title=title,
    )


def scope_targets(scope: dict) -> list[str]:
    key = {
        "BY_PROJECT": "selectedProjects",
        "BY_FOLDER": "selectedFolders",
        "BY_TAG": "selectedTags",
    }.get(scope.get("selectionMethod"))
    return scope.get(key, []) or [] if key else []


def render_scopes(scopes: list[dict], output: str) -> None:
    rows = [
        {
            "name": scope.get("name", ""),
            "selection_method": scope.get("selectionMethod", ""),
            "items": scope_targets(scope),
            "checks": scope.get("checks", []) or [],
            "description": scope.get("description", ""),
        }
        for scope in scopes
    ]
    render(
        rows,
        ["name", "selection_method", "items", "checks", "description"],
        output_format=output,
        title="Project Standards scopes (highest priority first)",
    )


def validate_check_ids(standards, check_ids: list[str]) -> None:
    if not check_ids:
        return
    available = {check.id for check in standards.list_checks()}
    missing = sorted(set(check_ids) - available)
    if missing:
        exit_with_error(
            f"Unknown Project Standards check ID(s): {', '.join(missing)}",
            details=["List valid IDs: dku project-standards list-checks"],
        )


def severity_category(severity: int | None) -> str:
    if severity is None or severity <= 0 or severity >= len(SEVERITY_NAMES):
        return ""
    return SEVERITY_NAMES[severity]


def report_rows(raw_report: dict) -> list[dict]:
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
                "severity_category": severity_category(severity),
                "message": result.get("message", ""),
            }
        )
    return sorted(rows, key=lambda row: row["check_id"])


def render_report(raw_report: dict, output: str, title: str) -> list[dict]:
    rows = report_rows(raw_report)
    render(rows, REPORT_COLUMNS, output_format=output, title=title)
    findings = [
        row for row in rows if isinstance(row["severity"], int) and row["severity"]
    ]
    errors = [row for row in rows if row["status"] == "RUN_ERROR"]
    if findings:
        warn(
            f"{len(findings)} of {len(rows)} checks non-compliant "
            "(severity >= 1; status is execution health)."
        )
    elif rows and not errors:
        info(f"All {len(rows)} checks compliant (severity 0).")
    if errors:
        warn(f"{len(errors)} checks failed to execute.")
    return rows


def render_resource(resource, output: str) -> None:
    render_raw(resource.get_raw(), output_format=output)


def compact_json(value: object) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)
