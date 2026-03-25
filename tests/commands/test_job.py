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


# ── Phase: job run command ───────────────────────────────────────────


def test_job_run_basic(patch_client):
    """Basic job run with single target."""
    result = runner.invoke(app, [
        "job", "run", "--target", "my_dataset", "--project", "PROJ1",
    ])
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    proj.new_job.assert_called_once_with("NON_RECURSIVE_FORCED_BUILD")
    builder = proj.new_job.return_value
    builder.with_output.assert_called_once_with("my_dataset")
    builder.start.assert_called_once()


def test_job_run_recursive_with_auto_schema(patch_client):
    """Recursive build with auto schema update."""
    result = runner.invoke(app, [
        "job", "run",
        "--target", "final_ds",
        "--type", "RECURSIVE_BUILD",
        "--auto-update-schema",
        "--project", "PROJ1",
    ])
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    proj.new_job.assert_called_once_with("RECURSIVE_BUILD")
    builder = proj.new_job.return_value
    builder.with_auto_update_schema_before_each_recipe_run.assert_called_once_with(True)


def test_job_run_multiple_targets(patch_client):
    """Multiple targets in a single job."""
    result = runner.invoke(app, [
        "job", "run",
        "--target", "ds1", "--target", "ds2",
        "--project", "PROJ1",
    ])
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    builder = proj.new_job.return_value
    assert builder.with_output.call_count == 2


def test_job_run_wait(patch_client):
    """Job run with --wait."""
    result = runner.invoke(app, [
        "job", "run",
        "--target", "my_dataset",
        "--wait",
        "--project", "PROJ1",
    ])
    assert result.exit_code == 0
    assert "completed" in result.output.lower() or "DONE" in result.output


def test_job_run_invalid_type(patch_client):
    """Invalid job type should fail."""
    result = runner.invoke(app, [
        "job", "run",
        "--target", "my_dataset",
        "--type", "INVALID_TYPE",
        "--project", "PROJ1",
    ])
    assert result.exit_code == 1
