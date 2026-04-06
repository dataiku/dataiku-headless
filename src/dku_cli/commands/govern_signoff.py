"""dku govern-signoff — list, get, create, update-status, add-feedback, add-approval."""

from __future__ import annotations

from typing import Optional

import typer

from dku_cli.errors import handle_api_error
from dku_cli.helpers import get_govern_client_from_ctx
from dku_cli.output import render, render_raw, resolve_output_format, success

app = typer.Typer(help="Manage Govern artifact sign-offs.")


@app.command()
def create(
    ctx: typer.Context,
    artifact_id: str = typer.Argument(help="Artifact ID (e.g. ar.5)"),
    step_id: str = typer.Argument(help="Workflow step ID (e.g. ideation, exploration)"),
) -> None:
    """Create a sign-off for a workflow step. Required before updating status."""
    try:
        govern = get_govern_client_from_ctx(ctx)
        art = govern.get_artifact(artifact_id)
        art.create_signoff(step_id)
        success(f"Created sign-off for step '{step_id}' on artifact '{artifact_id}'")
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("list")
def list_signoffs(
    ctx: typer.Context,
    artifact_id: str = typer.Argument(help="Artifact ID (e.g. ar.5)"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List sign-offs for an artifact."""
    output = resolve_output_format(output)
    try:
        govern = get_govern_client_from_ctx(ctx)
        art = govern.get_artifact(artifact_id)
        signoffs = art.list_signoffs()
        data = []
        for item in signoffs:
            raw = item.get_raw()
            data.append(
                {
                    "step_id": raw.get("stepId", ""),
                    "status": raw.get("status", ""),
                }
            )
        render(
            data,
            ["step_id", "status"],
            output_format=output,
            title=f"Sign-offs for {artifact_id}",
        )
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def get(
    ctx: typer.Context,
    artifact_id: str = typer.Argument(help="Artifact ID"),
    step_id: str = typer.Argument(help="Workflow step ID (e.g. exploration)"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Get sign-off details for an artifact workflow step."""
    output = resolve_output_format(output)
    try:
        govern = get_govern_client_from_ctx(ctx)
        art = govern.get_artifact(artifact_id)
        signoff = art.get_signoff(step_id)
        details = signoff.get_details()
        render_raw(details.get_raw(), output_format=output)
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("update-status")
def update_status(
    ctx: typer.Context,
    artifact_id: str = typer.Argument(help="Artifact ID"),
    step_id: str = typer.Argument(help="Workflow step ID"),
    status: str = typer.Argument(
        help="New status: NOT_STARTED, WAITING_FOR_FEEDBACK, WAITING_FOR_APPROVAL, APPROVED, REJECTED, ABANDONED"
    ),
) -> None:
    """Update the status of a sign-off."""
    valid = {
        "NOT_STARTED",
        "WAITING_FOR_FEEDBACK",
        "WAITING_FOR_APPROVAL",
        "APPROVED",
        "REJECTED",
        "ABANDONED",
    }
    if status not in valid:
        from dku_cli.errors import exit_with_error

        exit_with_error(
            f"Invalid sign-off status: '{status}'",
            code="invalid_argument",
            details=[f"Valid statuses: {', '.join(sorted(valid))}"],
        )
    try:
        govern = get_govern_client_from_ctx(ctx)
        art = govern.get_artifact(artifact_id)
        signoff = art.get_signoff(step_id)
        signoff.update_status(status)
        success(
            f"Updated sign-off status to '{status}' for step '{step_id}' on artifact '{artifact_id}'"
        )
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("add-feedback")
def add_feedback(
    ctx: typer.Context,
    artifact_id: str = typer.Argument(help="Artifact ID"),
    step_id: str = typer.Argument(help="Workflow step ID"),
    group_id: str = typer.Option(..., "--group-id", "-g", help="Feedback group ID"),
    status: str = typer.Option(
        ...,
        "--status",
        "-s",
        help="Feedback status: APPROVED, MINOR_ISSUE, MAJOR_ISSUE",
    ),
    comment: Optional[str] = typer.Option(
        None, "--comment", "-c", help="Feedback comment"
    ),
) -> None:
    """Add feedback to a sign-off."""
    valid = {"APPROVED", "MINOR_ISSUE", "MAJOR_ISSUE"}
    if status not in valid:
        from dku_cli.errors import exit_with_error

        exit_with_error(
            f"Invalid feedback status: '{status}'",
            code="invalid_argument",
            details=[f"Valid statuses: {', '.join(sorted(valid))}"],
        )
    try:
        govern = get_govern_client_from_ctx(ctx)
        art = govern.get_artifact(artifact_id)
        signoff = art.get_signoff(step_id)
        signoff.add_feedback(group_id, status, comment=comment)
        success(
            f"Added feedback '{status}' for step '{step_id}' on artifact '{artifact_id}'"
        )
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("add-approval")
def add_approval(
    ctx: typer.Context,
    artifact_id: str = typer.Argument(help="Artifact ID"),
    step_id: str = typer.Argument(help="Workflow step ID"),
    status: str = typer.Option(
        ..., "--status", "-s", help="Approval status: APPROVED, REJECTED, ABANDONED"
    ),
    comment: Optional[str] = typer.Option(
        None, "--comment", "-c", help="Approval comment"
    ),
) -> None:
    """Add approval to a sign-off."""
    valid = {"APPROVED", "REJECTED", "ABANDONED"}
    if status not in valid:
        from dku_cli.errors import exit_with_error

        exit_with_error(
            f"Invalid approval status: '{status}'",
            code="invalid_argument",
            details=[f"Valid statuses: {', '.join(sorted(valid))}"],
        )
    try:
        govern = get_govern_client_from_ctx(ctx)
        art = govern.get_artifact(artifact_id)
        signoff = art.get_signoff(step_id)
        signoff.add_approval(status, comment=comment)
        success(
            f"Added approval '{status}' for step '{step_id}' on artifact '{artifact_id}'"
        )
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)
