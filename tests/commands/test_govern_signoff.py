"""Tests for dku govern-signoff commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_signoff_list(patch_client):
    result = runner.invoke(app, ["govern", "signoff", "list", "ar.5"])
    assert result.exit_code == 0
    assert "exploration" in result.output


def test_signoff_list_json(patch_client):
    result = runner.invoke(
        app, ["--format", "json", "govern", "signoff", "list", "ar.5"]
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 1
    assert data[0]["step_id"] == "exploration"


def test_signoff_get(patch_client):
    result = runner.invoke(app, ["govern", "signoff", "get", "ar.5", "exploration"])
    assert result.exit_code == 0


def test_signoff_get_json(patch_client):
    result = runner.invoke(
        app, ["--format", "json", "govern", "signoff", "get", "ar.5", "exploration"]
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "feedbackGroups" in data or "approvers" in data


def test_signoff_update_status(patch_client):
    result = runner.invoke(
        app,
        [
            "govern",
            "signoff",
            "update-status",
            "ar.5",
            "exploration",
            "WAITING_FOR_FEEDBACK",
        ],
    )
    assert result.exit_code == 0
    gov = patch_client.get_govern_client()
    signoff = gov.get_artifact.return_value.get_signoff.return_value
    signoff.update_status.assert_called_once_with(
        "WAITING_FOR_FEEDBACK", reload_conf_for_reset=False
    )


def test_signoff_update_status_with_reload(patch_client):
    result = runner.invoke(
        app,
        [
            "govern",
            "signoff",
            "update-status",
            "ar.5",
            "exploration",
            "NOT_STARTED",
            "--reload",
        ],
    )
    assert result.exit_code == 0
    gov = patch_client.get_govern_client()
    signoff = gov.get_artifact.return_value.get_signoff.return_value
    signoff.update_status.assert_called_once_with(
        "NOT_STARTED", reload_conf_for_reset=True
    )


def test_signoff_update_status_invalid(patch_client):
    result = runner.invoke(
        app,
        ["govern", "signoff", "update-status", "ar.5", "exploration", "INVALID"],
    )
    assert result.exit_code != 0
    assert "Invalid" in result.output or "Invalid" in (result.stderr or "")


def test_signoff_add_feedback(patch_client):
    result = runner.invoke(
        app,
        [
            "govern",
            "signoff",
            "add-feedback",
            "ar.5",
            "exploration",
            "--group-id",
            "business_reviewers",
            "--status",
            "APPROVED",
            "--comment",
            "Looks good",
        ],
    )
    assert result.exit_code == 0
    gov = patch_client.get_govern_client()
    signoff = gov.get_artifact.return_value.get_signoff.return_value
    signoff.add_feedback.assert_called_once_with(
        "business_reviewers", "APPROVED", comment="Looks good"
    )


def test_signoff_add_feedback_invalid_status(patch_client):
    result = runner.invoke(
        app,
        [
            "govern",
            "signoff",
            "add-feedback",
            "ar.5",
            "exploration",
            "--group-id",
            "g1",
            "--status",
            "INVALID",
        ],
    )
    assert result.exit_code != 0


def test_signoff_add_approval(patch_client):
    result = runner.invoke(
        app,
        [
            "govern",
            "signoff",
            "add-approval",
            "ar.5",
            "exploration",
            "--status",
            "APPROVED",
            "--comment",
            "Ship it",
        ],
    )
    assert result.exit_code == 0
    gov = patch_client.get_govern_client()
    signoff = gov.get_artifact.return_value.get_signoff.return_value
    signoff.add_approval.assert_called_once_with("APPROVED", comment="Ship it")


def test_signoff_add_approval_rejected(patch_client):
    result = runner.invoke(
        app,
        [
            "govern",
            "signoff",
            "add-approval",
            "ar.5",
            "exploration",
            "--status",
            "REJECTED",
        ],
    )
    assert result.exit_code == 0
    gov = patch_client.get_govern_client()
    signoff = gov.get_artifact.return_value.get_signoff.return_value
    signoff.add_approval.assert_called_once_with("REJECTED", comment=None)


def test_signoff_add_approval_invalid_status(patch_client):
    result = runner.invoke(
        app,
        [
            "govern",
            "signoff",
            "add-approval",
            "ar.5",
            "exploration",
            "--status",
            "INVALID",
        ],
    )
    assert result.exit_code != 0


def test_signoff_create(patch_client):
    """Test creating a signoff for a workflow step."""
    result = runner.invoke(app, ["govern", "signoff", "create", "ar.5", "exploration"])
    assert result.exit_code == 0
    gov = patch_client.get_govern_client()
    gov.get_artifact.return_value.create_signoff.assert_called_once_with("exploration")


def test_signoff_create_blocks_when_workflow_step_mismatches(patch_client):
    """Pre-flight: refuse and emit advance-payload if current step != requested."""
    gov = patch_client.get_govern_client()
    art = gov.get_artifact.return_value
    # Artifact is currently at step "review" but caller requests sign-off
    # creation for "exploration" — DSS would raise "workflow step is not active".
    art.get_definition.return_value.get_raw.return_value = {
        "id": "ar.5",
        "name": "Test Project",
        "status": {"stepId": "review"},
    }
    result = runner.invoke(app, ["govern", "signoff", "create", "ar.5", "exploration"])
    assert result.exit_code != 0
    output = result.output + (result.stderr or "")
    assert "current" in output.lower()
    assert "review" in output
    assert "exploration" in output
    # The remediation must be the read-modify-write snippet — NOT a
    # `set-definition --definition '{"status": ...}'` suggestion, which strips
    # status server-side and would wipe the artifact's other fields.
    assert "get_definition" in output
    assert "stepId" in output
    assert "--definition" not in output
    # Must NOT have called create_signoff before exiting
    art.create_signoff.assert_not_called()


def test_signoff_create_proceeds_when_step_matches(patch_client):
    """When current step == requested, no pre-flight block — proceed to create."""
    gov = patch_client.get_govern_client()
    art = gov.get_artifact.return_value
    art.get_definition.return_value.get_raw.return_value = {
        "id": "ar.5",
        "status": {"stepId": "exploration"},
    }
    result = runner.invoke(app, ["govern", "signoff", "create", "ar.5", "exploration"])
    assert result.exit_code == 0
    art.create_signoff.assert_called_once_with("exploration")
