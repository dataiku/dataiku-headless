"""Tests for job commands."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from dku_cli.commands.job import _emit_long_running_hint
from dku_cli.main import app
from dku_cli.output import set_quiet
from tests.helpers import strip_ansi

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
    result = runner.invoke(
        app, ["--format", "json", "job", "list", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 1
    assert parsed[0]["id"] == "job1"


def test_job_last_prints_id(patch_client):
    """Default output is the plain job id on stdout — composable with $()."""
    result = runner.invoke(app, ["job", "last", "--project", "PROJ1"])
    assert result.exit_code == 0
    # Output is just the id, possibly with a trailing newline
    assert result.output.strip() == "job1"


def test_job_last_json(patch_client):
    """--format json returns the full record."""
    result = runner.invoke(
        app, ["--format", "json", "job", "last", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["id"] == "job1"
    assert parsed["state"] == "DONE"
    assert parsed["initiator"] == "testuser"


def test_job_last_old_output_flag_value_rejected(patch_client):
    """`-o` is the global --format alias now; the legacy `table` value gets the
    prescriptive valid-set error instead of a bare 'No such option'."""
    result = runner.invoke(app, ["job", "last", "--project", "PROJ1", "-o", "table"])
    assert result.exit_code == 2
    assert "json, csv, ids, quiet" in result.output


def test_job_last_no_jobs(patch_client):
    """When there are no jobs, exit 1 with a prescriptive error."""
    proj = patch_client.get_project("PROJ1")
    proj.list_jobs.return_value = []
    result = runner.invoke(app, ["job", "last", "--project", "PROJ1"])
    assert result.exit_code == 1
    assert "No jobs found" in result.output
    assert "dku recipe run" in result.output  # prescriptive fix


def test_job_last_invalid_global_format(patch_client):
    """Invalid output format should raise BadParameter."""
    result = runner.invoke(
        app, ["--format", "yaml", "job", "last", "--project", "PROJ1"]
    )
    assert result.exit_code != 0
    assert "Output format must be one of" in result.output


def test_job_status(patch_client):
    result = runner.invoke(app, ["job", "status", "job1", "--project", "PROJ1"])
    assert result.exit_code == 0


def test_job_status_json(patch_client):
    """-o json emits a structured dict — not a UI field-table list.

    Agents that debug recipe failures need the state, error, and per-activity
    breakdown as a navigable dict (PENDING.md 2026-05-11). The prior shape
    `[{field, value}, ...]` made every field accessor a `.[].select(...)`
    incantation.
    """
    result = runner.invoke(
        app, ["--format", "json", "job", "status", "job1", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert isinstance(parsed, dict)
    assert parsed["state"] == "DONE"
    assert parsed["job_id"] == "job1"
    assert "activities" in parsed
    # Initiator surfaced as a normal key (not wrapped in a field-row)
    assert parsed["initiator"] == "testuser"


def test_job_status_json_with_failed_activity(patch_client):
    """A failed activity surfaces with its name + error in the JSON payload.

    Real DSS shape (SerializedJobStatus): ``baseStatus.activities`` is a dict
    keyed by activity id, with ``startTime``/``endTime``/``firstFailure``.
    """
    job = patch_client.get_project("PROJ1").get_job("job1")
    job.get_status.return_value = {
        "baseStatus": {
            "def": {"id": "job1", "initiator": "testuser"},
            "state": "FAILED",
            "activities": {
                "build_my_recipe_NP": {
                    "state": "FAILED",
                    "startTime": 1700000000000,
                    "endTime": 1700000060000,
                    "firstFailure": {"message": "boom"},
                },
                "compute_other_NP": {
                    "state": "DONE",
                    "startTime": 1700000000000,
                    "endTime": 1700000030000,
                    "message": "built 42 rows",
                },
            },
        },
        "errorMessage": "Recipe failed",
    }
    result = runner.invoke(
        app, ["--format", "json", "job", "status", "job1", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["state"] == "FAILED"
    assert parsed["error"] == "Recipe failed"
    activities = {a["name"]: a for a in parsed["activities"]}
    assert len(activities) == 2
    failed = activities["build_my_recipe_NP"]
    assert failed["state"] == "FAILED"
    assert failed["error"] == "boom"
    assert failed["duration_ms"] == 60000
    # A benign per-activity `message` must NOT surface as an error.
    assert activities["compute_other_NP"]["error"] is None


def test_job_status_default_format_failed_job_stdout_is_json(patch_client):
    """A FAILED job's default output must stay pipe-safe: one JSON object on
    stdout, no trailing failed-activities table (the data is already in
    `activities`). The failure case is exactly where agents parse status."""
    job = patch_client.get_project("PROJ1").get_job("job1")
    job.get_status.return_value = {
        "baseStatus": {
            "def": {"id": "job1", "initiator": "testuser"},
            "state": "FAILED",
            "activities": {
                "build_my_recipe_NP": {
                    "state": "FAILED",
                    "startTime": 1700000000000,
                    "endTime": 1700000060000,
                    "firstFailure": {"message": "boom"},
                },
            },
        },
        "errorMessage": "Recipe failed",
    }
    result = runner.invoke(app, ["job", "status", "job1", "--project", "PROJ1"])
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert parsed["state"] == "FAILED"
    assert parsed["activities"][0]["error"] == "boom"
    # Debug hint stays on stderr.
    assert "dku job log job1" in result.stderr


def test_job_log_docker_socket_hint(patch_client):
    """A Docker-daemon-unreachable signature in the job log surfaces the
    recipe-level containerMode=NONE recovery recipe."""
    job = patch_client.get_project("PROJ1").get_job("job1")
    job.get_log.return_value = (
        "INFO Executing recipe on Docker with config=local-docker\n"
        "ERROR Cannot connect to the Docker daemon at unix:///var/run/docker.sock\n"
    )
    result = runner.invoke(app, ["job", "log", "job1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "containerMode" in result.output
    # Rich line-wraps the long examples; just check the load-bearing phrases.
    assert "Recipe-level containerMode=NONE" in result.output
    # Code recipes must be steered to set-env, NOT the destructive
    # set-definition --payload form (which would overwrite their source).
    assert "set-env" in result.output
    assert "USE_BUILTIN_MODE" in result.output
    assert "USE_BUILTIN_ENV" not in result.output


def test_job_log(patch_client):
    result = runner.invoke(app, ["job", "log", "job1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "Log line" in result.output


def test_job_log_bracketed_content_is_not_parsed_as_markup(patch_client):
    """Raw log lines with brackets (file lists, [ERROR] tags) crashed Rich with
    MarkupError and hid the real error. Logs must print verbatim."""
    job = patch_client.get_project("PROJ1").get_job("job1")
    job.get_log.return_value = (
        "[2026-06-03 10:00] [/SUP001_contract.pdf, /SUP002.pdf] [ERROR] embed failed"
    )
    result = runner.invoke(app, ["job", "log", "job1", "--project", "PROJ1"])
    assert result.exit_code == 0
    assert "SUP001_contract.pdf" in result.output
    assert "embed failed" in result.output


def test_job_log_tail(patch_client):
    job = patch_client.get_project("PROJ1").get_job("job1")
    job.get_log.return_value = "line1\nline2\nline3\nline4"
    result = runner.invoke(
        app, ["job", "log", "job1", "--project", "PROJ1", "--tail", "2"]
    )
    assert result.exit_code == 0
    assert "line1" not in result.output
    assert "line2" not in result.output
    assert "line3" in result.output
    assert "line4" in result.output


def test_job_log_grep_no_match(patch_client):
    job = patch_client.get_project("PROJ1").get_job("job1")
    job.get_log.return_value = "INFO build started\nINFO build finished"
    result = runner.invoke(
        app, ["job", "log", "job1", "--project", "PROJ1", "--grep", "nonexistent"]
    )
    assert result.exit_code == 0
    assert "No lines matching 'nonexistent' found" in result.output
    assert "INFO build started" not in result.output


def test_job_log_errors_only(patch_client):
    job = patch_client.get_project("PROJ1").get_job("job1")
    job.get_log.return_value = "\n".join(
        [
            "INFO start",
            "INFO preparing recipe",
            "ERROR recipe failed",
            'ValueError: bad column "MONTH_DATE"',
            "Traceback (most recent call last):",
            'KeyError: "MONTH_DATE"',
            "INFO cleanup",
        ]
    )
    result = runner.invoke(
        app, ["job", "log", "job1", "--project", "PROJ1", "--errors-only"]
    )
    assert result.exit_code == 0
    assert "ERROR recipe failed" in result.output
    assert 'KeyError: "MONTH_DATE"' in result.output
    assert "INFO preparing recipe" in result.output
    assert "INFO start" not in result.output


def test_job_log_errors_only_falls_back_when_no_matches(patch_client):
    job = patch_client.get_project("PROJ1").get_job("job1")
    job.get_log.return_value = "INFO build started\nINFO build finished"
    result = runner.invoke(
        app, ["job", "log", "job1", "--project", "PROJ1", "--errors-only"]
    )
    assert result.exit_code == 0
    assert "No error-like lines found" in result.output
    assert "INFO build started" in result.output
    assert "INFO build finished" in result.output


def test_job_abort(patch_client):
    result = runner.invoke(app, ["job", "abort", "job1", "--project", "PROJ1"])
    assert result.exit_code == 0


def test_job_long_running_hint_uses_valid_abort_command(capsys):
    _emit_long_running_hint("job1", "PROJ1", 180)

    captured = capsys.readouterr()
    assert "dku job abort job1" in captured.err
    assert "-P PROJ1" in captured.err
    assert " -y" not in captured.err


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
        result = runner.invoke(
            app, ["job", "wait", "job1", "--project", "PROJ1", "--timeout", "2"]
        )
    assert result.exit_code == 1
    assert "Timed out" in result.output


def test_job_wait_failed_exits_nonzero(patch_client):
    """`job wait` on a FAILED job must exit non-zero so agents chaining
    `job wait && next-step` stop instead of marching past a failed build."""
    proj = patch_client.get_project("PROJ1")
    job_mock = proj.get_job("job1")
    job_mock.get_status.return_value = {"baseStatus": {"state": "FAILED"}}
    result = runner.invoke(app, ["job", "wait", "job1", "--project", "PROJ1"])
    assert result.exit_code != 0
    assert "FAILED" in result.output
    assert "job log" in result.output  # prescriptive 'Inspect why' hint


# ── Phase: job run command ───────────────────────────────────────────


def test_job_run_basic(patch_client):
    """Basic job run with single target."""
    result = runner.invoke(
        app,
        [
            "job",
            "run",
            "--target",
            "my_dataset",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    proj.new_job.assert_called_once_with("NON_RECURSIVE_FORCED_BUILD")
    builder = proj.new_job.return_value
    # Object type is auto-detected and passed explicitly (defaults to DATASET) so
    # managed-folder / saved-model targets don't error with "dataset not found".
    builder.with_output.assert_called_once_with("my_dataset", object_type="DATASET")
    builder.start.assert_called_once()


def test_job_run_recursive_with_auto_schema(patch_client):
    """Recursive build with auto schema update."""
    result = runner.invoke(
        app,
        [
            "job",
            "run",
            "--target",
            "final_ds",
            "--type",
            "RECURSIVE_BUILD",
            "--auto-update-schema",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    proj.new_job.assert_called_once_with("RECURSIVE_BUILD")
    builder = proj.new_job.return_value
    builder.with_auto_update_schema_before_each_recipe_run.assert_called_once_with(True)


def test_job_run_auto_update_schema_on_by_default(patch_client):
    """No flag → auto-update is ON by default (imported from DADK)."""
    result = runner.invoke(
        app, ["job", "run", "--target", "final_ds", "--project", "PROJ1"]
    )
    assert result.exit_code == 0
    builder = patch_client.get_project("PROJ1").new_job.return_value
    builder.with_auto_update_schema_before_each_recipe_run.assert_called_once_with(True)


def test_job_run_no_auto_update_schema_opt_out(patch_client):
    """--no-auto-update-schema preserves the stored schema (partitioned /
    hand-curated case) — the builder schema-update call is not made."""
    result = runner.invoke(
        app,
        [
            "job",
            "run",
            "--target",
            "final_ds",
            "--no-auto-update-schema",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    builder = patch_client.get_project("PROJ1").new_job.return_value
    builder.with_auto_update_schema_before_each_recipe_run.assert_not_called()


def test_job_run_folder_target_resolves_type(patch_client):
    """A managed-folder target (by name) builds as MANAGED_FOLDER with its ID,
    not the default DATASET (which would error with 'dataset not found')."""
    result = runner.invoke(
        app,
        [
            "job",
            "run",
            "--target",
            "Data Folder",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0, result.output
    proj = patch_client.get_project("PROJ1")
    builder = proj.new_job.return_value
    # "Data Folder" resolves to id "folder1" (conftest).
    builder.with_output.assert_called_once_with("folder1", object_type="MANAGED_FOLDER")


def test_job_run_multiple_targets(patch_client):
    """Multiple targets in a single job."""
    result = runner.invoke(
        app,
        [
            "job",
            "run",
            "--target",
            "ds1",
            "--target",
            "ds2",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    proj = patch_client.get_project("PROJ1")
    builder = proj.new_job.return_value
    assert builder.with_output.call_count == 2


def test_job_run_wait(patch_client):
    """Job run with --wait."""
    result = runner.invoke(
        app,
        [
            "job",
            "run",
            "--target",
            "my_dataset",
            "--wait",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 0
    assert "completed" in result.output.lower() or "DONE" in result.output


def test_job_run_wait_failed_exits_nonzero(patch_client):
    """`job run --wait` on a FAILED build must exit non-zero (DONE still exits 0).

    Agents chain `job run --wait && next-step`; exit 0 on FAILED would let the
    chain continue past a broken build."""
    proj = patch_client.get_project("PROJ1")
    started_job = proj.new_job.return_value.start.return_value
    started_job.get_status.return_value = {"baseStatus": {"state": "FAILED"}}
    result = runner.invoke(
        app,
        [
            "job",
            "run",
            "--target",
            "my_dataset",
            "--wait",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code != 0
    assert "FAILED" in result.output
    assert "job log" in result.output  # prescriptive 'Inspect why' hint


def test_job_run_invalid_type(patch_client):
    """Invalid job type is rejected at parse time by click.Choice (exit 2)."""
    result = runner.invoke(
        app,
        [
            "job",
            "run",
            "--target",
            "my_dataset",
            "--type",
            "INVALID_TYPE",
            "--project",
            "PROJ1",
        ],
    )
    assert result.exit_code == 2
    stripped = strip_ansi(result.output)
    assert "Invalid value" in stripped


def test_job_run_wait_done_emits_build_summary(patch_client):
    """A successful --wait build prints a rows/cols proof line per dataset."""
    result = runner.invoke(
        app,
        ["job", "run", "--target", "my_dataset", "--wait", "--project", "PROJ1"],
    )
    assert result.exit_code == 0, result.output
    assert "Built my_dataset:" in result.output
    assert "cols" in result.output
