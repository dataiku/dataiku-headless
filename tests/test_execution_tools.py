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


def _raw_status_with_activities(job_id, *, end_time, runtime_state, activities):
    """A completed-job status carrying per-activity output refs + states.

    ``activities`` is a list of ``(activity_id, state, [dataset_refs])`` — enough
    for get_job_status_full to surface per-output activity states, which
    build_datasets maps back to per-dataset outcomes.

    The shape mirrors a payload captured from a live DSS 14.x DONE job:
    ``runtimeSummary.activities`` is a list carrying state and timings but NO
    output refs, ``baseStatus.activities`` is a dict keyed by activityId whose
    ``statusOutputs`` is empty even when DONE, and the dataset refs live at
    ``def.targets`` as ``{projectKey, datasetName, partitionId}`` entries.
    """
    return {
        "def": {"id": job_id},
        "baseStatus": {
            "jobStartTime": 100,
            "jobEndTime": end_time,
            "activities": {
                aid: {
                    "activityId": aid,
                    "statusOutputs": [],
                    "def": {
                        "targets": [
                            {
                                "projectKey": "PK",
                                "datasetName": ref,
                                "partitionId": "NP",
                            }
                            for ref in refs
                        ]
                    },
                }
                for aid, _state, refs in activities
            },
        },
        "runtimeSummary": {
            "state": runtime_state,
            "activities": [
                {"activityId": aid, "state": state} for aid, state, _refs in activities
            ],
        },
        "initiator": {},
    }


# --------------------------------------------------------------------------- #
# build_datasets — one job builds all requested outputs
# --------------------------------------------------------------------------- #


def test_build_datasets_no_wait_starts_one_job_with_all_outputs():
    job = _job("J1")
    builder = MagicMock()
    builder.start.return_value = job
    project = MagicMock()
    project.new_job.return_value = builder
    client = MagicMock()
    client.get_project.return_value = project

    with patch("dataiku_mcp.tools.jobs.get_dss_client", return_value=client):
        res = _load(
            jobs.build_datasets("PK", FakeCtx(), ["a", "b"], wait_for_completion=False)
        )

    assert res["status"] == "build_started"
    # ONE job, ONE job_id, for all requested outputs.
    assert res["job_id"] == "J1"
    assert res["datasets"] == ["a", "b"]
    project.new_job.assert_called_once()
    builder.start.assert_called_once()
    assert builder.with_output.call_count == 2
    builder.with_output.assert_any_call("a")
    builder.with_output.assert_any_call("b")
    # No wait means no status was fetched.
    assert job.get_status.call_count == 0


def test_build_datasets_wait_reports_per_dataset_outcomes():
    raw = _raw_status_with_activities(
        "J1",
        end_time=200,
        runtime_state="DONE",
        activities=[("act_a", "DONE", ["a"]), ("act_b", "DONE", ["b"])],
    )
    job = _job("J1", raw)
    builder = MagicMock()
    builder.start.return_value = job
    project = MagicMock()
    project.new_job.return_value = builder
    client = MagicMock()
    client.get_project.return_value = project

    with patch("dataiku_mcp.tools.jobs.get_dss_client", return_value=client):
        res = _load(
            jobs.build_datasets("PK", FakeCtx(), ["a", "b"], wait_for_completion=True)
        )

    assert res["status"] == "build_completed"
    assert res["job_id"] == "J1"
    per = {d["dataset"]: d["state"] for d in res["per_dataset"]}
    assert per == {"a": "DONE", "b": "DONE"}


def test_build_datasets_per_dataset_matches_live_dss_done_payload():
    """Regression for the live-DSS activity shape (was per_dataset state null).

    Verified against DSS 14.x project AAA_144D45, job
    Build_salary_stats_global__NP__2026-07-23T21-19-33.864: the DONE job's
    runtimeSummary activities carry no output refs, baseStatus.activities'
    statusOutputs is empty, and the only dataset refs sit at
    def.targets[].datasetName. The old summarizer read a top-level targets list
    keyed by id, so every per_dataset state came back null on a DONE build.
    """
    job_id = "Build_salary_stats_global__NP__2026-07-23T21-19-33.864"
    raw = {
        "def": {"id": job_id},
        "baseStatus": {
            "jobStartTime": 100,
            "jobEndTime": 200,
            "activities": {
                "salary_stats_by_dept_NP": {
                    "activityId": "salary_stats_by_dept_NP",
                    "activityType": "recipe",
                    "recipeName": "compute_salary_stats_by_department",
                    "state": "DONE",
                    "statusOutputs": [],
                    "def": {
                        "targets": [
                            {
                                "projectKey": "AAA_144D45",
                                "datasetName": "salary_stats_by_department",
                                "partitionId": "NP",
                            }
                        ]
                    },
                }
            },
        },
        "runtimeSummary": {
            "state": "DONE",
            "activities": [
                {
                    "activityId": "salary_stats_by_dept_NP",
                    "activityType": "recipe",
                    "engineType": "DSS",
                    "state": "DONE",
                    "preparingTime": 1,
                    "runningTime": 2,
                    "totalTime": 3,
                    "waitingTime": 0,
                }
            ],
        },
        "initiator": {},
    }
    job = _job(job_id, raw)
    builder = MagicMock()
    builder.start.return_value = job
    client = MagicMock()
    client.get_project.return_value.new_job.return_value = builder

    with patch("dataiku_mcp.tools.jobs.get_dss_client", return_value=client):
        res = _load(
            jobs.build_datasets(
                "AAA_144D45",
                FakeCtx(),
                ["salary_stats_by_department"],
                wait_for_completion=True,
            )
        )

    assert res["status"] == "build_completed"
    assert res["per_dataset"] == [
        {"dataset": "salary_stats_by_department", "state": "DONE"}
    ]


def test_build_datasets_wait_timeout_returns_still_running():
    raw = _raw_status("J1", end_time=0, runtime_state="RUNNING")
    job = _job("J1", raw)
    builder = MagicMock()
    builder.start.return_value = job
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
                "PK", FakeCtx(), ["a", "b"], wait_for_completion=True
            )
        )

    # A single shared timeout for the whole build; one job_id still running.
    assert res["status"] == "build_still_running"
    assert res["job_id"] == "J1"
    assert res["datasets"] == ["a", "b"]


def test_build_datasets_start_failure_raises_with_safe_retry_guidance():
    builder = MagicMock()
    builder.start.side_effect = RuntimeError("nope")
    project = MagicMock()
    project.new_job.return_value = builder
    client = MagicMock()
    client.get_project.return_value = project

    with patch("dataiku_mcp.tools.jobs.get_dss_client", return_value=client):
        with pytest.raises(RuntimeError, match="Inspect recent jobs") as raised:
            _load(
                jobs.build_datasets(
                    "PK", FakeCtx(), ["a", "b"], wait_for_completion=False
                )
            )

    assert isinstance(raised.value.__cause__, RuntimeError)
    assert "nope" in str(raised.value.__cause__)


def test_build_datasets_invalid_job_type_rejected():
    with pytest.raises(ValueError, match="job_type"):
        _load(jobs.build_datasets("PK", FakeCtx(), ["a"], job_type="BOGUS"))


def test_build_datasets_rejects_duplicates_and_unbounded_inputs():
    with pytest.raises(ValueError, match="duplicates"):
        _load(jobs.build_datasets("PK", FakeCtx(), ["a", "a"]))
    with pytest.raises(ValueError, match="at most"):
        _load(
            jobs.build_datasets(
                "PK",
                FakeCtx(),
                [f"dataset_{index}" for index in range(101)],
            )
        )
    with pytest.raises(ValueError, match="<= 3600"):
        _load(
            jobs.build_datasets(
                "PK", FakeCtx(), ["a"], wait_for_completion=True, timeout_seconds=3601
            )
        )


def test_build_datasets_captures_client_before_first_await():
    captured = MagicMock()
    captured_builder = MagicMock()
    captured_builder.start.return_value = _job("CAPTURED")
    captured.get_project.return_value.new_job.return_value = captured_builder
    later = MagicMock()
    current = [captured]

    class SwitchingCtx(FakeCtx):
        async def info(self, message, **kwargs):
            await super().info(message, **kwargs)
            current[0] = later

    with patch(
        "dataiku_mcp.tools.jobs.get_dss_client", side_effect=lambda: current[0]
    ):
        result = _load(jobs.build_datasets("PK", SwitchingCtx(), ["a"]))

    assert result["job_id"] == "CAPTURED"
    captured.get_project.assert_called_once_with("PK")
    later.get_project.assert_not_called()


def test_build_datasets_poll_failure_returns_structured_job_identity():
    job = _job("KEEP-ME")
    job.get_status.side_effect = ConnectionError("status link dropped")
    builder = MagicMock()
    builder.start.return_value = job
    client = MagicMock()
    client.get_project.return_value.new_job.return_value = builder

    with patch("dataiku_mcp.tools.jobs.get_dss_client", return_value=client):
        res = _load(
            jobs.build_datasets("PK", FakeCtx(), ["a"], wait_for_completion=True)
        )

    # Post-start failures are returned, not raised, so the job identity is
    # carried as structured fields that survive transport error masking.
    assert res["status"] == "build_poll_failed"
    assert res["job_id"] == "KEEP-ME"
    assert res["datasets"] == ["a"]
    assert res["error_type"] == "ConnectionError"
    assert "status link dropped" in res["error"]
    assert "do not start a replacement" in res["hint"]


def test_run_recipe_poll_failure_returns_structured_job_identity():
    project = _recipe_project([{"type": "COMPUTABLE_DATASET", "ref": "out_ds"}])
    job = _job("KEEP-RECIPE-JOB")
    job.get_status.side_effect = ConnectionError("status link dropped")
    project.new_job.return_value.start.return_value = job
    client = MagicMock()
    client.get_project.return_value = project

    with patch("dataiku_mcp.tools.jobs.get_dss_client", return_value=client):
        res = _load(
            jobs.run_recipe("PK", "my_recipe", FakeCtx(), wait_for_completion=True)
        )

    assert res["status"] == "recipe_poll_failed"
    assert res["job_id"] == "KEEP-RECIPE-JOB"
    assert res["recipe"] == "my_recipe"
    assert res["error_type"] == "ConnectionError"
    assert "do not run the recipe again" in res["hint"]


class _HostileJobHandle:
    """A job handle whose .id raises, as a partial DSS payload would.

    The SDK reads the id straight from the raw payload, so a truncated handle
    makes ``.id`` raise. Combined with a failing poll, the old code read
    ``job.id`` again inside the except block and escaped, losing the identity.
    """

    @property
    def id(self):
        raise KeyError("jobId")

    def get_status(self):
        raise ConnectionError("status link dropped")


def test_build_datasets_poll_failure_with_hostile_handle_stays_structured():
    job = _HostileJobHandle()
    builder = MagicMock()
    builder.start.return_value = job
    client = MagicMock()
    client.get_project.return_value.new_job.return_value = builder

    with patch("dataiku_mcp.tools.jobs.get_dss_client", return_value=client):
        res = _load(
            jobs.build_datasets("PK", FakeCtx(), ["a"], wait_for_completion=True)
        )

    # .id is unreadable and polling failed: the tool must still RETURN its
    # structured payload (never raise into transport masking). job_id is absent
    # because it was never readable, but the outcome is identified and the
    # datasets echoed so the caller does not blindly rebuild.
    assert res["status"] == "build_poll_failed"
    assert "job_id" not in res
    assert res["datasets"] == ["a"]
    assert res["error_type"] == "ConnectionError"


def test_run_recipe_poll_failure_with_hostile_handle_stays_structured():
    project = _recipe_project([{"type": "COMPUTABLE_DATASET", "ref": "out_ds"}])
    project.new_job.return_value.start.return_value = _HostileJobHandle()
    client = MagicMock()
    client.get_project.return_value = project

    with patch("dataiku_mcp.tools.jobs.get_dss_client", return_value=client):
        res = _load(
            jobs.run_recipe("PK", "my_recipe", FakeCtx(), wait_for_completion=True)
        )

    assert res["status"] == "recipe_poll_failed"
    assert "job_id" not in res
    assert res["recipe"] == "my_recipe"
    assert res["error_type"] == "ConnectionError"


class _HostileIdButDoneJobHandle:
    """get_status() SUCCEEDS with a terminal DONE payload while .id raises.

    This is the shape that exercises _wait_for_job_result's OWN job.id read:
    only passing the caller's captured job_id into the helper keeps a completed
    build from being misreported as a poll failure. The DONE payload still
    carries the real id under def.id, so the summary stays complete.
    """

    def __init__(self, job_id):
        self._job_id = job_id

    @property
    def id(self):
        raise KeyError("jobId")

    def get_status(self):
        return _raw_status_with_activities(
            self._job_id,
            end_time=200,
            runtime_state="DONE",
            activities=[("act_a", "DONE", ["a"])],
        )


def test_build_datasets_done_payload_with_hostile_id_completes():
    job = _HostileIdButDoneJobHandle("DONE-JOB")
    builder = MagicMock()
    builder.start.return_value = job
    client = MagicMock()
    client.get_project.return_value.new_job.return_value = builder

    with patch("dataiku_mcp.tools.jobs.get_dss_client", return_value=client):
        res = _load(
            jobs.build_datasets("PK", FakeCtx(), ["a"], wait_for_completion=True)
        )

    # The helper no longer reads job.id, so a DONE payload behind a hostile
    # handle completes instead of collapsing to build_poll_failed. The id is
    # recovered from the payload (def.id) and surfaced in the summary.
    assert res["status"] == "build_completed"
    assert res["status_summary"]["state"] == "DONE"
    assert res["status_summary"]["job_id"] == "DONE-JOB"
    assert res["per_dataset"] == [{"dataset": "a", "state": "DONE"}]


def test_run_recipe_done_payload_with_hostile_id_completes():
    project = _recipe_project([{"type": "COMPUTABLE_DATASET", "ref": "out_ds"}])
    project.new_job.return_value.start.return_value = _HostileIdButDoneJobHandle(
        "DONE-RECIPE-JOB"
    )
    client = MagicMock()
    client.get_project.return_value = project

    with patch("dataiku_mcp.tools.jobs.get_dss_client", return_value=client):
        res = _load(
            jobs.run_recipe("PK", "my_recipe", FakeCtx(), wait_for_completion=True)
        )

    assert res["status"] == "recipe_run_completed"
    assert res["status_summary"]["state"] == "DONE"
    assert res["status_summary"]["job_id"] == "DONE-RECIPE-JOB"


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
        with pytest.raises(ValueError, match="unsupported output type"):
            _load(jobs.run_recipe("PK", "weird", FakeCtx()))


def test_run_recipe_no_output_raises():
    project = _recipe_project([])
    client = MagicMock()
    client.get_project.return_value = project

    with patch("dataiku_mcp.tools.jobs.get_dss_client", return_value=client):
        with pytest.raises(ValueError, match="no outputs"):
            _load(jobs.run_recipe("PK", "empty", FakeCtx()))


def test_run_recipe_start_failure_is_raised_as_outcome_unknown():
    project = _recipe_project(
        [{"type": "COMPUTABLE_DATASET", "ref": "out_ds"}]
    )
    project.new_job.return_value.start.side_effect = ConnectionError("dropped")
    client = MagicMock()
    client.get_project.return_value = project

    with patch("dataiku_mcp.tools.jobs.get_dss_client", return_value=client):
        with pytest.raises(RuntimeError, match="Inspect recent jobs") as raised:
            _load(jobs.run_recipe("PK", "recipe", FakeCtx()))

    assert isinstance(raised.value.__cause__, ConnectionError)


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
    # The real scenario run id is returned, alongside the trigger identity.
    assert res["run_id"] == "RUN-1"
    assert res["trigger_fire_id"] == "TRIG-9"


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
    assert res["trigger_fire_id"] == "TRIG-9"
    assert "run_id" not in res


def test_run_scenario_wait_bounded_timeout_returns_still_running():
    scenario_run = MagicMock()
    scenario_run.id = "RUN-2"
    scenario_run.running = True  # never finishes
    trigger_fire = MagicMock()
    trigger_fire.run_id = "TRIG-2"
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

    assert res["status"] == "scenario_run_still_running"
    assert res["run_id"] == "RUN-2"
    assert res["trigger_fire_id"] == "TRIG-2"
    assert "get_scenario_run_history" in res["hint"]


def test_run_scenario_wait_completed_returns_both_identities():
    scenario_run = MagicMock()
    scenario_run.id = "RUN-DONE"
    scenario_run.running = False
    scenario_run.get_info.return_value = {"result": {"outcome": "SUCCESS"}}
    trigger_fire = MagicMock()
    trigger_fire.run_id = "TRIG-DONE"
    trigger_fire.get_scenario_run.return_value = scenario_run
    client = _scenario_client(trigger_fire)

    with patch("dataiku_mcp.tools.scenarios.get_dss_client", return_value=client):
        res = _load(
            scenarios.run_scenario(
                "PK", "sc1", FakeCtx(), wait_for_completion=True, timeout_seconds=600
            )
        )

    assert res["status"] == "scenario_run_completed"
    assert res["run_id"] == "RUN-DONE"
    assert res["trigger_fire_id"] == "TRIG-DONE"
    assert res["outcome"] == "SUCCESS"


def test_run_scenario_wait_timeout_before_run_exists_keeps_trigger_fire_id():
    trigger_fire = MagicMock()
    trigger_fire.run_id = "TRIG-NO-RUN"
    trigger_fire.get_scenario_run.return_value = None  # DSS never materializes it
    trigger_fire.is_cancelled.return_value = False
    client = _scenario_client(trigger_fire)

    with patch("dataiku_mcp.tools.scenarios.get_dss_client", return_value=client), patch(
        "dataiku_mcp.tools.scenarios.time"
    ) as mock_time:
        mock_time.monotonic.side_effect = _incrementing_monotonic()
        res = _load(
            scenarios.run_scenario(
                "PK", "sc1", FakeCtx(), wait_for_completion=True, timeout_seconds=1
            )
        )

    # The deadline expired before DSS materialized a run: no run_id exists yet,
    # so the trigger identity must be preserved to forbid a blind re-trigger.
    assert res["status"] == "scenario_run_still_running"
    assert "run_id" not in res
    assert res["trigger_fire_id"] == "TRIG-NO-RUN"


def test_run_scenario_cancelled_trigger_keeps_trigger_fire_id():
    trigger_fire = MagicMock()
    trigger_fire.run_id = "TRIG-CANCELLED"
    trigger_fire.get_scenario_run.return_value = None
    trigger_fire.is_cancelled.return_value = True
    client = _scenario_client(trigger_fire)

    with patch("dataiku_mcp.tools.scenarios.get_dss_client", return_value=client):
        res = _load(
            scenarios.run_scenario(
                "PK", "sc1", FakeCtx(), wait_for_completion=True, timeout_seconds=600
            )
        )

    assert res["status"] == "scenario_run_cancelled"
    assert res["trigger_fire_id"] == "TRIG-CANCELLED"


def test_run_scenario_poll_failure_returns_structured_trigger_identity():
    trigger_fire = MagicMock()
    trigger_fire.run_id = "TRIGGER-KEEP"
    trigger_fire.get_scenario_run.side_effect = ConnectionError("poll dropped")
    client = _scenario_client(trigger_fire)

    with patch("dataiku_mcp.tools.scenarios.get_dss_client", return_value=client):
        res = _load(scenarios.run_scenario("PK", "sc1", FakeCtx()))

    # Post-start failures are returned, not raised, so the trigger identity is
    # carried as structured fields that survive transport error masking.
    assert res["status"] == "scenario_poll_failed"
    assert res["trigger_fire_id"] == "TRIGGER-KEEP"
    assert "run_id" not in res
    assert res["error_type"] == "ConnectionError"
    assert "poll dropped" in res["error"]
    assert "Do not trigger the scenario again" in res["hint"]


def test_run_scenario_poll_failure_after_run_materializes_keeps_run_id():
    scenario_run = MagicMock()
    scenario_run.id = "RUN-POST"
    scenario_run.running = False
    scenario_run.get_info.side_effect = ConnectionError("info dropped")
    trigger_fire = MagicMock()
    trigger_fire.run_id = "TRIG-POST"
    trigger_fire.get_scenario_run.return_value = scenario_run
    client = _scenario_client(trigger_fire)

    with patch("dataiku_mcp.tools.scenarios.get_dss_client", return_value=client):
        res = _load(
            scenarios.run_scenario(
                "PK", "sc1", FakeCtx(), wait_for_completion=True, timeout_seconds=600
            )
        )

    # The run was observed before polling failed: BOTH identities must survive,
    # not just the trigger's.
    assert res["status"] == "scenario_poll_failed"
    assert res["run_id"] == "RUN-POST"
    assert res["trigger_fire_id"] == "TRIG-POST"
    assert res["error_type"] == "ConnectionError"


def test_run_scenario_poll_failure_is_structured_over_fastmcp_transport():
    """Call through the FastMCP server, not the raw function.

    A raised exception would reach the client as unstructured (maskable) error
    text; a structured tool RESULT is immune to error masking. Assert the tool
    returns a result carrying the identity fields rather than erroring.
    """
    from fastmcp import Client

    import dataiku_mcp

    trigger_fire = MagicMock()
    trigger_fire.run_id = "TRIG-TRANSPORT"
    trigger_fire.get_scenario_run.side_effect = ConnectionError("poll dropped")
    client = _scenario_client(trigger_fire)

    async def _call():
        async with Client(dataiku_mcp.mcp) as mcp_client:
            # raise_on_error=True (default): an error result would raise here.
            return await mcp_client.call_tool(
                "run_scenario", {"project_key": "PK", "scenario_id": "sc1"}
            )

    with patch("dataiku_mcp.tools.scenarios.get_dss_client", return_value=client):
        result = asyncio.run(_call())

    assert not result.is_error
    payload = json.loads(result.content[0].text)
    assert payload["status"] == "scenario_poll_failed"
    assert payload["trigger_fire_id"] == "TRIG-TRANSPORT"


def test_get_scenario_run_history_rows_carry_trigger_fire_id():
    run = MagicMock()
    run.running = False
    run.get_info.return_value = {
        "runId": "RUN-H",
        "start": 100,
        "result": {"outcome": "SUCCESS", "endTime": 200},
        "trigger": {"runId": "TRIG-H", "trigger": {"type": "manual"}},
    }
    scenario = MagicMock()
    scenario.get_last_runs.return_value = [run]
    client = MagicMock()
    client.get_project.return_value.get_scenario.return_value = scenario

    with patch("dataiku_mcp.tools.scenarios.get_dss_client", return_value=client):
        res = _load(scenarios.get_scenario_run_history("PK", "sc1", FakeCtx()))

    table = res["runs"]
    row = dict(zip(table["columns"], table["rows"][0]))
    # The trigger-fire id is exposed so a caller holding only a trigger_fire_id
    # (timeout before DSS materialized the run) can correlate it to its run.
    assert row["run_id"] == "RUN-H"
    assert row["trigger_fire_id"] == "TRIG-H"


def _history_row_for_trigger_shape(trigger_value):
    run = MagicMock()
    run.running = False
    run.get_info.return_value = {
        "runId": "RUN-SHAPE",
        "start": 100,
        "result": {"outcome": "SUCCESS", "endTime": 200},
        "trigger": trigger_value,
    }
    scenario = MagicMock()
    scenario.get_last_runs.return_value = [run]
    client = MagicMock()
    client.get_project.return_value.get_scenario.return_value = scenario

    with patch("dataiku_mcp.tools.scenarios.get_dss_client", return_value=client):
        res = _load(scenarios.get_scenario_run_history("PK", "sc1", FakeCtx()))

    table = res["runs"]
    return dict(zip(table["columns"], table["rows"][0]))


def test_get_scenario_run_history_tolerates_string_trigger_fire():
    # DSS put a bare string where the trigger-fire record was expected: the row
    # must still come back, with null trigger fields, never a fabricated id.
    row = _history_row_for_trigger_shape("manual")
    assert row["run_id"] == "RUN-SHAPE"
    assert row["trigger_fire_id"] is None
    assert row["trigger_type"] is None


def test_get_scenario_run_history_keeps_valid_fire_id_with_string_inner_trigger():
    # The fire record is a dict with a valid scalar runId, but its nested trigger
    # DEFINITION is a bare string. The contract keeps the usable fire id (it is
    # the identity needed for correlation) and only nulls the trigger type. A
    # valid fire id is never discarded because a sibling field is malformed.
    row = _history_row_for_trigger_shape({"runId": "TRIG-S", "trigger": "manual"})
    assert row["run_id"] == "RUN-SHAPE"
    assert row["trigger_fire_id"] == "TRIG-S"
    assert row["trigger_type"] is None


def test_get_scenario_run_history_nulls_non_scalar_fire_id():
    # runId itself is a non-scalar (a dict here, a list is equivalent): it is not
    # a usable fire id, so the contract nulls it rather than emitting a structure.
    row = _history_row_for_trigger_shape({"runId": {"nested": "x"}, "trigger": {}})
    assert row["run_id"] == "RUN-SHAPE"
    assert row["trigger_fire_id"] is None


def test_get_scenario_run_history_scalar_int_fire_id_is_kept():
    # An integer runId is still a valid scalar identity and is kept as-is.
    row = _history_row_for_trigger_shape({"runId": 4242, "trigger": {"type": "manual"}})
    assert row["trigger_fire_id"] == 4242
    assert row["trigger_type"] == "manual"


# The boolean, list, and absent-runId cases below pin already-correct behavior
# as coverage; they do NOT prove a regression. The isinstance scalar filter has
# been in place since the round-4 commit, so these pass against earlier commits
# too. Only the two hostile-handle tests (build/recipe DONE payload with a
# raising .id, and the raising .run_id trigger fire) genuinely fail pre-fix.
def test_get_scenario_run_history_nulls_boolean_fire_id():
    # A boolean is a scalar in JSON but is never a run id, so it is nulled even
    # though isinstance(True, int) is True; the type filter excludes booleans.
    row = _history_row_for_trigger_shape({"runId": True, "trigger": {"type": "manual"}})
    assert row["trigger_fire_id"] is None
    assert row["trigger_type"] == "manual"


def test_get_scenario_run_history_nulls_list_fire_id():
    # A list runId is a non-scalar and is nulled, never emitted as a structure.
    row = _history_row_for_trigger_shape({"runId": ["x"], "trigger": {}})
    assert row["run_id"] == "RUN-SHAPE"
    assert row["trigger_fire_id"] is None


def test_get_scenario_run_history_nulls_absent_fire_id():
    # A fire record with no runId key at all yields a null fire id.
    row = _history_row_for_trigger_shape({"trigger": {"type": "manual"}})
    assert row["run_id"] == "RUN-SHAPE"
    assert row["trigger_fire_id"] is None
    assert row["trigger_type"] == "manual"


class _UnformattableError(Exception):
    """An exception whose __str__ raises, as some SDK/HTTP errors do."""

    def __str__(self):
        raise RuntimeError("cannot format this error")


def test_run_scenario_poll_failure_with_unformattable_error_keeps_identity():
    trigger_fire = MagicMock()
    trigger_fire.run_id = "TRIG-UNFORMATTABLE"
    trigger_fire.get_scenario_run.side_effect = _UnformattableError("boom")
    client = _scenario_client(trigger_fire)

    with patch("dataiku_mcp.tools.scenarios.get_dss_client", return_value=client):
        res = _load(scenarios.run_scenario("PK", "sc1", FakeCtx()))

    # Building the failure payload must never raise, even when the exception's
    # own __str__ does; the identity survives and the error falls back to repr.
    assert res["status"] == "scenario_poll_failed"
    assert res["trigger_fire_id"] == "TRIG-UNFORMATTABLE"
    assert res["error_type"] == "_UnformattableError"
    assert "_UnformattableError" in res["error"]


class _PartialRun:
    """A run handle whose payload lacks runId, so .id raises like the SDK's."""

    running = False

    @property
    def id(self):
        raise KeyError("runId")

    def refresh(self):
        pass

    def get_info(self):
        raise ConnectionError("poll dropped")


def test_run_scenario_poll_failure_with_partial_run_payload_keeps_trigger_id():
    trigger_fire = MagicMock()
    trigger_fire.run_id = "TRIG-PARTIAL"
    trigger_fire.get_scenario_run.return_value = _PartialRun()
    client = _scenario_client(trigger_fire)

    with patch("dataiku_mcp.tools.scenarios.get_dss_client", return_value=client):
        res = _load(
            scenarios.run_scenario(
                "PK", "sc1", FakeCtx(), wait_for_completion=True, timeout_seconds=600
            )
        )

    # The run payload had no runId (its .id raises KeyError) and polling then
    # failed: the failure handler must not raise while recovering the run id,
    # and the trigger identity must survive.
    assert res["status"] == "scenario_poll_failed"
    assert "run_id" not in res
    assert res["trigger_fire_id"] == "TRIG-PARTIAL"
    assert res["error_type"] == "ConnectionError"


class _HostileTriggerFire:
    """A trigger-fire handle whose .run_id raises after run() succeeded.

    The SDK reads run_id straight from the fire payload, so a partial payload
    makes it raise. run_scenario captures the id once, guarded, so no post-start
    payload reads .run_id again and none can escape into transport masking.
    """

    @property
    def run_id(self):
        raise KeyError("runId")

    def get_scenario_run(self):
        raise ConnectionError("poll dropped")

    def is_cancelled(self, refresh=False):
        return False


def test_run_scenario_hostile_trigger_fire_id_stays_structured():
    client = _scenario_client(_HostileTriggerFire())

    with patch("dataiku_mcp.tools.scenarios.get_dss_client", return_value=client):
        res = _load(scenarios.run_scenario("PK", "sc1", FakeCtx()))

    # .run_id is unreadable and resolving failed: the tool must still RETURN a
    # structured payload rather than raise. trigger_fire_id is always present as
    # a key (null here, since the handle would not yield it) so a client never
    # has to distinguish an omitted key from a null; the outcome is identified so
    # no blind re-trigger.
    assert res["status"] == "scenario_poll_failed"
    assert "trigger_fire_id" in res
    assert res["trigger_fire_id"] is None
    assert res["error_type"] == "ConnectionError"


def test_run_scenario_captures_client_before_first_await():
    trigger_fire = MagicMock()
    trigger_fire.run_id = "TRIGGER-CAPTURED"
    scenario_run = MagicMock()
    scenario_run.id = "RUN-CAPTURED"
    trigger_fire.get_scenario_run.return_value = scenario_run
    captured = _scenario_client(trigger_fire)
    later = MagicMock()
    current = [captured]

    class SwitchingCtx(FakeCtx):
        async def info(self, message, **kwargs):
            await super().info(message, **kwargs)
            current[0] = later

    with patch(
        "dataiku_mcp.tools.scenarios.get_dss_client",
        side_effect=lambda: current[0],
    ):
        result = _load(scenarios.run_scenario("PK", "sc1", SwitchingCtx()))

    assert result["run_id"] == "RUN-CAPTURED"
    captured.get_project.assert_called_once_with("PK")
    later.get_project.assert_not_called()


def test_run_scenario_rejects_unbounded_inline_wait():
    with pytest.raises(ValueError, match="<= 3600"):
        _load(
            scenarios.run_scenario(
                "PK",
                "sc1",
                FakeCtx(),
                wait_for_completion=True,
                timeout_seconds=3601,
            )
        )
