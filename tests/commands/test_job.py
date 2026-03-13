"""Tests for job commands."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from dku_cli.main import app
from dku_cli.output import set_quiet

runner = CliRunner()


@pytest.fixture(autouse=True)
def _reset_quiet():
    """Ensure quiet mode is off before each test (global state leak fix)."""
    set_quiet(False)
    yield
    set_quiet(False)


def test_job_list(patch_client):
    result = runner.invoke(app, ["job", "list", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "job1" in result.output


def test_job_list_json(patch_client):
    result = runner.invoke(app, ["job", "list", "--project", "PROJ1", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 1
    assert parsed[0]["id"] == "job1"


def test_job_status(patch_client):
    result = runner.invoke(app, ["job", "status", "job1", "--project", "PROJ1"])
    assert result.exit_code == 0


def test_job_status_json(patch_client):
    result = runner.invoke(app, ["job", "status", "job1", "--project", "PROJ1", "-o", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert any(d["field"] == "State" and d["value"] == "DONE" for d in parsed)


def test_job_log(patch_client):
    result = runner.invoke(app, ["job", "log", "job1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "Log line" in result.output


def test_job_abort(patch_client):
    result = runner.invoke(app, ["job", "abort", "job1", "--project", "PROJ1"])
    assert result.exit_code == 0


# ── Phase 4: wait command ──────────────────────────────────────────────


def test_job_wait_already_done(patch_client):
    """Job is already DONE — should return immediately."""
    result = runner.invoke(app, ["job", "wait", "job1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "finished" in result.output
    assert "DONE" in result.output


def test_job_wait_transitions_to_done(patch_client):
    """Job transitions from RUNNING to DONE after one poll."""
    proj = patch_client.get_project("PROJ1")
    job_mock = proj.get_job("job1")
    # First call returns RUNNING, second returns DONE
    job_mock.get_status.side_effect = [
        {"baseStatus": {"state": "RUNNING"}},
        {"baseStatus": {"state": "DONE"}},
    ]
    with patch("dku_cli.commands.job.time.sleep"):
        result = runner.invoke(app, ["job", "wait", "job1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "finished" in result.output
    assert "DONE" in result.output


def test_job_wait_timeout(patch_client):
    """Job never finishes — should time out."""
    proj = patch_client.get_project("PROJ1")
    job_mock = proj.get_job("job1")
    job_mock.get_status.return_value = {"baseStatus": {"state": "RUNNING"}}
    with patch("dku_cli.commands.job.time.sleep"):
        result = runner.invoke(app, ["job", "wait", "job1", "--project", "PROJ1", "--timeout", "2"])
    assert result.exit_code == 1
    assert "Timed out" in result.output


def test_job_wait_failed(patch_client):
    """Job finishes with FAILED state."""
    proj = patch_client.get_project("PROJ1")
    job_mock = proj.get_job("job1")
    job_mock.get_status.return_value = {"baseStatus": {"state": "FAILED"}}
    result = runner.invoke(app, ["job", "wait", "job1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "finished" in result.output
    assert "FAILED" in result.output
