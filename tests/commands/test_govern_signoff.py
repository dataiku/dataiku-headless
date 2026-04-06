"""Tests for dku govern-signoff commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_signoff_list(patch_client):
    result = runner.invoke(app, ["govern-signoff", "list", "ar.5"])
    assert result.exit_code == 0
    assert "exploration" in result.output


def test_signoff_list_json(patch_client):
    result = runner.invoke(app, ["govern-signoff", "list", "ar.5", "-o", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 1
    assert data[0]["step_id"] == "exploration"


def test_signoff_get(patch_client):
    result = runner.invoke(app, ["govern-signoff", "get", "ar.5", "exploration"])
    assert result.exit_code == 0


def test_signoff_get_json(patch_client):
    result = runner.invoke(
        app, ["govern-signoff", "get", "ar.5", "exploration", "-o", "json"]
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "feedbackGroups" in data or "approvers" in data


def test_signoff_update_status(patch_client):
    result = runner.invoke(
        app,
        [
            "govern-signoff",
            "update-status",
            "ar.5",
            "exploration",
            "WAITING_FOR_FEEDBACK",
        ],
    )
    assert result.exit_code == 0
    gov = patch_client.get_govern_client()
    signoff = gov.get_artifact.return_value.get_signoff.return_value
    signoff.update_status.assert_called_once_with("WAITING_FOR_FEEDBACK")


def test_signoff_update_status_invalid(patch_client):
    result = runner.invoke(
        app,
        ["govern-signoff", "update-status", "ar.5", "exploration", "INVALID"],
    )
    assert result.exit_code != 0
    assert "Invalid" in result.output or "Invalid" in (result.stderr or "")


def test_signoff_add_feedback(patch_client):
    result = runner.invoke(
        app,
        [
            "govern-signoff",
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
            "govern-signoff",
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
            "govern-signoff",
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
            "govern-signoff",
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
            "govern-signoff",
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
    result = runner.invoke(app, ["govern-signoff", "create", "ar.5", "exploration"])
    assert result.exit_code == 0
    gov = patch_client.get_govern_client()
    gov.get_artifact.return_value.create_signoff.assert_called_once_with("exploration")
