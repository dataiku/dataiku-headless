"""Tests for new govern-signoff commands: delegate-feedback, delegate-approval, list-feedbacks, get-feedback, get-approval."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from dku_cli.main import app

runner = CliRunner()


def test_signoff_delegate_feedback(patch_client):
    result = runner.invoke(
        app,
        [
            "govern",
            "signoff",
            "delegate-feedback",
            "ar.5",
            "exploration",
            "--group-id",
            "business_reviewers",
            "--users-container",
            '{"type": "SINGLE_USER", "login": "charlie"}',
        ],
    )
    assert result.exit_code == 0
    gov = patch_client.get_govern_client()
    signoff = gov.get_artifact.return_value.get_signoff.return_value
    signoff.delegate_feedback.assert_called_once_with(
        "business_reviewers",
        {"type": "SINGLE_USER", "login": "charlie"},
    )


def test_signoff_delegate_approval(patch_client):
    result = runner.invoke(
        app,
        [
            "govern",
            "signoff",
            "delegate-approval",
            "ar.5",
            "exploration",
            "--users-container",
            '{"type": "SINGLE_USER", "login": "charlie"}',
        ],
    )
    assert result.exit_code == 0
    gov = patch_client.get_govern_client()
    signoff = gov.get_artifact.return_value.get_signoff.return_value
    signoff.delegate_approval.assert_called_once_with(
        {"type": "SINGLE_USER", "login": "charlie"},
    )


def test_signoff_delegate_approval_help_mentions_global_api_key_shape(patch_client):
    result = runner.invoke(app, ["govern", "signoff", "delegate-approval", "--help"])

    assert result.exit_code == 0
    assert "globalAPIKeyId" in result.output
    assert '\\"type\\":\\"user\\"' in result.output


def test_signoff_list_feedbacks(patch_client):
    result = runner.invoke(
        app, ["govern", "signoff", "list-feedbacks", "ar.5", "exploration"]
    )
    assert result.exit_code == 0
    assert "fb.1" in result.output


def test_signoff_list_feedbacks_json(patch_client):
    result = runner.invoke(
        app,
        [
            "--format",
            "json",
            "govern",
            "signoff",
            "list-feedbacks",
            "ar.5",
            "exploration",
        ],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 1
    assert data[0]["id"] == "fb.1"


def test_signoff_get_feedback(patch_client):
    result = runner.invoke(
        app, ["govern", "signoff", "get-feedback", "ar.5", "exploration", "fb.1"]
    )
    assert result.exit_code == 0


def test_signoff_get_feedback_json(patch_client):
    result = runner.invoke(
        app,
        [
            "--format",
            "json",
            "govern",
            "signoff",
            "get-feedback",
            "ar.5",
            "exploration",
            "fb.1",
        ],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["id"] == "fb.1"
    assert data["status"] == "APPROVED"


def test_signoff_get_approval(patch_client):
    result = runner.invoke(
        app, ["govern", "signoff", "get-approval", "ar.5", "exploration"]
    )
    assert result.exit_code == 0


def test_signoff_get_approval_json(patch_client):
    result = runner.invoke(
        app,
        [
            "--format",
            "json",
            "govern",
            "signoff",
            "get-approval",
            "ar.5",
            "exploration",
        ],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["status"] == "APPROVED"
    assert data["user"] == "bob"
