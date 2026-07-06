"""dku govern signoff — list, get, create, update-status, add-feedback, add-approval, delegate-feedback, delegate-approval, list-feedbacks, get-feedback, get-approval."""

from __future__ import annotations

import typer

from dku_cli.enums import (
    SignoffApprovalStatus,
    SignoffFeedbackStatus,
    SignoffStatus,
)
from dku_cli.errors import exit_with_error, handle_api_error
from dku_cli.helpers import get_govern_client_from_ctx, read_json_input
from dku_cli.output import render, render_raw, resolve_output_format, success

app = typer.Typer(help="Manage Govern artifact sign-offs.")


def _current_step_id(artifact) -> str | None:
    """Read the artifact's current workflow step id, if any.

    Returns None if no current step is set or the shape is unfamiliar — the
    caller falls back to letting the server raise.
    """
    try:
        defn = artifact.get_definition().get_raw()
    except Exception:
        return None
    status = defn.get("status") if isinstance(defn, dict) else None
    if isinstance(status, dict):
        sid = status.get("stepId")
        if isinstance(sid, str) and sid:
            return sid
    return None


@app.command()
def create(
    ctx: typer.Context,
    artifact_id: str = typer.Argument(help="Artifact ID (e.g. ar.5)"),
    step_id: str = typer.Argument(help="Workflow step ID (e.g. ideation, exploration)"),
) -> None:
    """Create a sign-off for a workflow step. Required before updating status.

    The artifact's CURRENT workflow step must equal ``step_id``. If they
    differ, DSS rejects with ``workflow step is not active`` — this verb
    pre-flights the check and emits the exact ``set-definition`` payload
    needed to advance the workflow first.
    """
    try:
        govern = get_govern_client_from_ctx(ctx)
        art = govern.get_artifact(artifact_id)

        current = _current_step_id(art)
        if current is not None and current != step_id:
            exit_with_error(
                f"Sign-off step '{step_id}' is not the artifact's current "
                f"workflow step ('{current}'). DSS only allows sign-off "
                "creation on the active step.",
                details=[
                    "Advance the workflow first, then re-run sign-off create.",
                    "",
                    "Step 1 — advance to the target step via read-modify-write "
                    "(dku set-definition strips the status field, and a "
                    "status-only definition would wipe the artifact's fields):",
                    "",
                    "  python - <<'PY'",
                    "  import dataikuapi",
                    "  c = dataikuapi.GovernClient(URL, api_key=KEY)",
                    f"  defn = c.get_artifact('{artifact_id}').get_definition()",
                    "  raw = defn.get_raw()",
                    f"  raw.setdefault('status', {{}})['stepId'] = '{step_id}'",
                    "  raw.pop('workflow', None)  # server re-derives steps",
                    "  defn.save()",
                    "  PY",
                    "",
                    "Step 2 — create the sign-off (re-run this command):",
                    f"  dku govern signoff create {artifact_id} {step_id}",
                ],
                status=2,
            )

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
) -> None:
    """List sign-offs for an artifact."""
    output = resolve_output_format()
    try:
        govern = get_govern_client_from_ctx(ctx)
        art = govern.get_artifact(artifact_id)
        signoffs = art.list_signoffs()
        data = []
        for item in signoffs:
            raw = item.get_raw()
            signoff_id = (
                raw.get("signoffId") if isinstance(raw.get("signoffId"), dict) else {}
            )
            data.append(
                {
                    "step_id": signoff_id.get("stepId", ""),
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
) -> None:
    """Get sign-off details for an artifact workflow step."""
    output = resolve_output_format()
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
    status: SignoffStatus = typer.Argument(
        case_sensitive=False,
        help="New status: NOT_STARTED, WAITING_FOR_FEEDBACK, WAITING_FOR_APPROVAL, APPROVED, REJECTED, ABANDONED",
    ),
) -> None:
    """Update the status of a sign-off."""
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
    status: SignoffFeedbackStatus = typer.Option(
        ...,
        "--status",
        "-s",
        case_sensitive=False,
        help="Feedback status: APPROVED, MINOR_ISSUE, MAJOR_ISSUE",
    ),
    comment: str | None = typer.Option(
        None, "--comment", "-c", help="Feedback comment"
    ),
) -> None:
    """Add feedback to a sign-off."""
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
    status: SignoffApprovalStatus = typer.Option(
        ...,
        "--status",
        "-s",
        case_sensitive=False,
        help="Approval status: APPROVED, REJECTED, ABANDONED",
    ),
    comment: str | None = typer.Option(
        None, "--comment", "-c", help="Approval comment"
    ),
) -> None:
    """Add approval to a sign-off."""
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


@app.command("delegate-feedback")
def delegate_feedback(
    ctx: typer.Context,
    artifact_id: str = typer.Argument(help="Artifact ID"),
    step_id: str = typer.Argument(help="Workflow step ID"),
    group_id: str = typer.Option(
        ..., "--group-id", "-g", help="Feedback group ID to delegate from"
    ),
    users_container: str = typer.Option(
        ...,
        "--users-container",
        help="Users container JSON (string, @file.json, or - for stdin)",
    ),
) -> None:
    """Delegate feedback to specific users for a sign-off group."""
    try:
        govern = get_govern_client_from_ctx(ctx)
        art = govern.get_artifact(artifact_id)
        signoff = art.get_signoff(step_id)
        container = read_json_input(users_container)
        signoff.delegate_feedback(group_id, container)
        success(
            f"Delegated feedback for group '{group_id}' on step '{step_id}' of artifact '{artifact_id}'"
        )
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("delegate-approval")
def delegate_approval(
    ctx: typer.Context,
    artifact_id: str = typer.Argument(help="Artifact ID"),
    step_id: str = typer.Argument(help="Workflow step ID"),
    users_container: str = typer.Option(
        ...,
        "--users-container",
        help="Users container JSON (string, @file.json, or - for stdin)",
    ),
) -> None:
    """Delegate approval to specific users for a sign-off."""
    try:
        govern = get_govern_client_from_ctx(ctx)
        art = govern.get_artifact(artifact_id)
        signoff = art.get_signoff(step_id)
        container = read_json_input(users_container)
        signoff.delegate_approval(container)
        success(f"Delegated approval for step '{step_id}' on artifact '{artifact_id}'")
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("list-feedbacks")
def list_feedbacks(
    ctx: typer.Context,
    artifact_id: str = typer.Argument(help="Artifact ID"),
    step_id: str = typer.Argument(help="Workflow step ID"),
) -> None:
    """List all feedbacks for a sign-off step."""
    output = resolve_output_format()
    try:
        govern = get_govern_client_from_ctx(ctx)
        art = govern.get_artifact(artifact_id)
        signoff = art.get_signoff(step_id)
        feedbacks = signoff.list_feedbacks()
        data = []
        for item in feedbacks:
            raw = item.get_raw()
            data.append(
                {
                    "id": raw.get("id", ""),
                    "status": raw.get("status", ""),
                    "group_id": raw.get("groupId", ""),
                    "user": raw.get("user", ""),
                }
            )
        render(
            data,
            ["id", "status", "group_id", "user"],
            output_format=output,
            title=f"Feedbacks for {artifact_id} step {step_id}",
        )
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("get-feedback")
def get_feedback(
    ctx: typer.Context,
    artifact_id: str = typer.Argument(help="Artifact ID"),
    step_id: str = typer.Argument(help="Workflow step ID"),
    feedback_id: str = typer.Argument(help="Feedback ID"),
) -> None:
    """Get a specific feedback review from a sign-off."""
    output = resolve_output_format()
    try:
        govern = get_govern_client_from_ctx(ctx)
        art = govern.get_artifact(artifact_id)
        signoff = art.get_signoff(step_id)
        feedback = signoff.get_feedback(feedback_id)
        defn = feedback.get_definition()
        render_raw(defn.get_raw(), output_format=output)
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("get-approval")
def get_approval(
    ctx: typer.Context,
    artifact_id: str = typer.Argument(help="Artifact ID"),
    step_id: str = typer.Argument(help="Workflow step ID"),
) -> None:
    """Get the current approval for a sign-off step."""
    output = resolve_output_format()
    try:
        govern = get_govern_client_from_ctx(ctx)
        art = govern.get_artifact(artifact_id)
        signoff = art.get_signoff(step_id)
        approval = signoff.get_approval()
        defn = approval.get_definition()
        render_raw(defn.get_raw(), output_format=output)
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)
