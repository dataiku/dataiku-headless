"""Tests for the three direct-execution tools.

These are the only sanctioned direct actions on existing assets (everything else
goes through Cobuild): ``build_datasets`` / ``run_recipe`` (jobs) and
``run_scenario`` (scenarios). They never touch the network — ``get_dss_client``
is patched with a ``MagicMock`` chain, and the monotonic clock is patched where a
bounded wait path must be exercised without real sleeping.
"""

import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest

from dataiku_mcp.tools import jobs, scenarios


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


class FakeCtx:
    """Minimal async Context capturing ctx.info progress messages."""

    def __init__(self):
        self.infos = []

    async def info(self, message, **kwargs):
        self.infos.append(message)


def _load(coro):
    """Run a tool coroutine and parse its compact-JSON string result."""
    return json.loads(asyncio.run(coro))


def _incrementing_monotonic(step=1000.0):
    """A monotonic() stand-in that jumps ``step`` seconds on every call.

    Every "remaining" check therefore lands well past the deadline computed on the
    preceding call, so any bounded wait loop times out on its first iteration —
    deterministic and with no real sleeping, regardless of call count.
    """
    state = {"t": 0.0}

    def _next():
        value = state["t"]
        state["t"] += step
        return value

    return _next


def _job(job_id, raw_status=None):
    job = MagicMock()
    job.id = job_id
    if raw_status is not None:
        job.get_status.return_value = raw_status
    return job


def _raw_status(job_id, *, end_time, runtime_state=None):
    return {
        "def": {"id": job_id},
        "baseStatus": {"jobStartTime": 100, "jobEndTime": end_time},
        "runtimeSummary": {"state": runtime_state} if runtime_state else {},
        "initiator": {},
    }


# --------------------------------------------------------------------------- #
# build_datasets
# --------------------------------------------------------------------------- #


def test_build_datasets_no_wait_returns_job_ids():
    job1, job2 = _job("J1"), _job("J2")
    builder = MagicMock()
    builder.start.side_effect = [job1, job2]
    project = MagicMock()
    project.new_job.return_value = builder
    client = MagicMock()
    client.get_project.return_value = project

    with patch("dataiku_mcp.tools.jobs.get_dss_client", return_value=client):
        res = _load(
            jobs.build_datasets("PK", FakeCtx(), ["a", "b"], wait_for_completion=False)
        )

    assert res["status"] == "builds_started"
    assert [j["job_id"] for j in res["jobs"]] == ["J1", "J2"]
    assert all(j["status"] == "STARTED" for j in res["jobs"])
    # No wait means no status was fetched.
    assert job1.get_status.call_count == 0


def test_build_datasets_wait_aggregates_completed_errors_and_running():
    job_done = _job("JD", _raw_status("JD", end_time=200))
    job_failed = _job("JF", _raw_status("JF", end_time=300, runtime_state="FAILED"))
    job_running = _job("JR", _raw_status("JR", end_time=0, runtime_state="RUNNING"))
    builder = MagicMock()
    builder.start.side_effect = [job_done, job_failed, job_running]
    project = MagicMock()
    project.new_job.return_value = builder
    client = MagicMock()
    client.get_project.return_value = project

    with patch("dataiku_mcp.tools.jobs.get_dss_client", return_value=client), patch(
        "dataiku_mcp.tools.jobs.time"
    ) as mock_time:
        mock_time.monotonic.side_effect = _incrementing_monotonic()
        res = _load(
            jobs.build_datasets(
                "PK", FakeCtx(), ["d", "f", "r"], wait_for_completion=True
            )
        )

    by_ds = {j["dataset"]: j for j in res["jobs"]}
    assert by_ds["d"]["status"] == "DONE"
    assert by_ds["f"]["status"] == "FAILED"
    assert by_ds["r"]["status"] == "RUNNING"
    assert by_ds["r"]["wait_timed_out"] is True
    assert by_ds["d"]["wait_timed_out"] is False
    # Top-level summary surfaces the error (highest-priority signal).
    assert res["status"] == "builds_completed_with_errors"


def test_build_datasets_invalid_job_type_rejected():
    with pytest.raises(ValueError, match="job_type"):
        _load(jobs.build_datasets("PK", FakeCtx(), ["a"], job_type="BOGUS"))


# --------------------------------------------------------------------------- #
# run_recipe
# --------------------------------------------------------------------------- #


def _recipe_project(outputs):
    graph = MagicMock()
    graph.get_successor_computables.return_value = outputs
    flow = MagicMock()
    flow.get_graph.return_value = graph
    project = MagicMock()
    project.get_recipe.return_value = MagicMock()
    project.get_flow.return_value = flow
    return project


def test_run_recipe_resolves_output_and_returns_job_id():
    project = _recipe_project([{"type": "COMPUTABLE_DATASET", "ref": "out_ds"}])
    builder = MagicMock()
    builder.start.return_value = _job("JR1")
    project.new_job.return_value = builder
    client = MagicMock()
    client.get_project.return_value = project

    with patch("dataiku_mcp.tools.jobs.get_dss_client", return_value=client):
        res = _load(
            jobs.run_recipe("PK", "my_recipe", FakeCtx(), wait_for_completion=False)
        )

    assert res["status"] == "recipe_run_started"
    assert res["job_id"] == "JR1"
    # The first computable output was resolved to its job output type and built.
    builder.with_output.assert_called_once_with("out_ds", object_type="DATASET")


def test_run_recipe_unsupported_output_raises():
    project = _recipe_project([{"type": "COMPUTABLE_WEIRD", "ref": "x"}])
    client = MagicMock()
    client.get_project.return_value = project

    with patch("dataiku_mcp.tools.jobs.get_dss_client", return_value=client):
        with pytest.raises(Exception, match="unsupported output type"):
            _load(jobs.run_recipe("PK", "weird", FakeCtx()))


def test_run_recipe_no_output_raises():
    project = _recipe_project([])
    client = MagicMock()
    client.get_project.return_value = project

    with patch("dataiku_mcp.tools.jobs.get_dss_client", return_value=client):
        with pytest.raises(Exception, match="no outputs"):
            _load(jobs.run_recipe("PK", "empty", FakeCtx()))


# --------------------------------------------------------------------------- #
# run_scenario
# --------------------------------------------------------------------------- #


def _scenario_client(trigger_fire):
    scenario = MagicMock()
    scenario.run.return_value = trigger_fire
    project = MagicMock()
    project.get_scenario.return_value = scenario
    client = MagicMock()
    client.get_project.return_value = project
    return client


def test_run_scenario_no_wait_returns_run_id():
    scenario_run = MagicMock()
    scenario_run.id = "RUN-1"
    trigger_fire = MagicMock()
    trigger_fire.run_id = "TRIG-9"
    trigger_fire.get_scenario_run.return_value = scenario_run
    client = _scenario_client(trigger_fire)

    with patch("dataiku_mcp.tools.scenarios.get_dss_client", return_value=client):
        res = _load(
            scenarios.run_scenario("PK", "sc1", FakeCtx(), wait_for_completion=False)
        )

    assert res["status"] == "scenario_run_triggered"
    # The real scenario run id (not the trigger fire id) is returned.
    assert res["run_id"] == "RUN-1"
    assert "trigger_run_id" not in res


def test_run_scenario_no_wait_falls_back_to_trigger_id_when_run_absent():
    trigger_fire = MagicMock()
    trigger_fire.run_id = "TRIG-9"
    trigger_fire.get_scenario_run.return_value = None
    trigger_fire.is_cancelled.return_value = False
    client = _scenario_client(trigger_fire)

    # Collapse the resolve budget so the poll ends immediately.
    with patch("dataiku_mcp.tools.scenarios.get_dss_client", return_value=client), patch(
        "dataiku_mcp.tools.scenarios.time"
    ) as mock_time:
        mock_time.monotonic.side_effect = _incrementing_monotonic()
        res = _load(
            scenarios.run_scenario("PK", "sc1", FakeCtx(), wait_for_completion=False)
        )

    assert res["status"] == "scenario_run_triggered"
    assert res["trigger_run_id"] == "TRIG-9"
    assert "run_id" not in res


def test_run_scenario_wait_bounded_timeout_returns_still_running():
    scenario_run = MagicMock()
    scenario_run.id = "RUN-2"
    scenario_run.running = True  # never finishes
    trigger_fire = MagicMock()
    trigger_fire.get_scenario_run.return_value = scenario_run
    client = _scenario_client(trigger_fire)

    with patch("dataiku_mcp.tools.scenarios.get_dss_client", return_value=client), patch(
        "dataiku_mcp.tools.scenarios.time"
    ) as mock_time:
        mock_time.monotonic.side_effect = _incrementing_monotonic()
        res = _load(
            scenarios.run_scenario(
                "PK", "sc1", FakeCtx(), wait_for_completion=True, timeout_seconds=600
            )
        )

    assert res["status"] == "scenario_still_running"
    assert res["run_id"] == "RUN-2"
    assert "get_scenario_run_history" in res["hint"]
