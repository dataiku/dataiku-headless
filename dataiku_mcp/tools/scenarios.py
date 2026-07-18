"""Scenario inspection and execution tools for Dataiku DSS."""

import asyncio
import time

from fastmcp import Context

from .. import mcp
from .utils.async_executor import run_blocking
from .utils.auth import get_dss_client
from .utils.serialization import columnar, compact_json, omit_empty
from .utils.validation import (
    require_non_empty_string as _require_non_empty_string,
    require_positive_int as _require_positive_int,
)

SCENARIO_POLL_INTERVAL_SECONDS = 2
# Short budget to poll for the scenario run id after firing a trigger. The run is
# created asynchronously by DSS, so we give it a few seconds to appear.
SCENARIO_RUN_ID_RESOLVE_BUDGET_SECONDS = 4


def _summarize_reporter(reporter: dict) -> dict:
    messaging = reporter.get("messaging") or {}
    configuration = messaging.get("configuration") or {}
    return omit_empty(
        {
            "messaging_channel": configuration.get("channelId") or messaging.get("type"),
            "condition": reporter.get("runCondition"),
        }
    )


async def _resolve_scenario_run_id(trigger_fire, budget_seconds: int):
    """Poll briefly for the scenario run id created by a fired trigger.

    ``scenario.run()`` returns a ``DSSTriggerFire`` whose ``run_id`` identifies the
    *trigger* firing, not the scenario run. DSS creates the scenario run
    asynchronously, so we poll ``trigger_fire.get_scenario_run()`` (which returns a
    ``DSSScenarioRun`` or None) to obtain the real ``DSSScenarioRun.id`` — the same
    identifier ``get_scenario_run_history`` reports.

    Returns ``(state, run_id)`` where state is one of "resolved", "cancelled",
    "unresolved".
    """
    deadline = time.monotonic() + budget_seconds
    while True:
        scenario_run = await run_blocking(trigger_fire.get_scenario_run)
        if scenario_run is not None:
            return "resolved", scenario_run.id
        if await run_blocking(lambda: trigger_fire.is_cancelled(refresh=True)):
            return "cancelled", None
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return "unresolved", None
        await asyncio.sleep(min(SCENARIO_POLL_INTERVAL_SECONDS, remaining))


async def _wait_for_scenario_run_result(trigger_fire, timeout_seconds: int):
    """Bounded poll for the completion of a scenario run created by a fired trigger.

    Never delegates to the SDK's unbounded ``wait_for_completion`` /
    ``wait_for_scenario_run``: we own a deadline-bounded poll loop so the tool always
    returns within ``timeout_seconds``.

    Returns ``(state, run_id, outcome)`` where state is one of "completed",
    "cancelled", "timed_out".
    """
    deadline = time.monotonic() + timeout_seconds
    scenario_run = None
    while True:
        if scenario_run is None:
            scenario_run = await run_blocking(trigger_fire.get_scenario_run)
            if scenario_run is None:
                if await run_blocking(lambda: trigger_fire.is_cancelled(refresh=True)):
                    return "cancelled", None, None
        else:
            await run_blocking(scenario_run.refresh)

        if scenario_run is not None and not scenario_run.running:
            result = scenario_run.get_info().get("result") or {}
            return "completed", scenario_run.id, result.get("outcome")

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            run_id = scenario_run.id if scenario_run is not None else None
            return "timed_out", run_id, None

        await asyncio.sleep(min(SCENARIO_POLL_INTERVAL_SECONDS, remaining))


@mcp.tool()
async def list_scenarios(project_key: str, ctx: Context) -> str:
    """List the scenarios in the project with their active and running status."""
    project_key = _require_non_empty_string(project_key, "project_key")
    await ctx.info(f"Listing scenarios in {project_key}...")

    items = await run_blocking(
        lambda: get_dss_client().get_project(project_key).list_scenarios()
    )
    scenarios = [
        {
            "id": item.get("id"),
            "name": item.get("name"),
            "active": item.get("active", False),
            "type": item.get("type"),
            "running": item.get("running", False),
            "shortDesc": item.get("shortDesc", ""),
            "tags": item.get("tags", []),
        }
        for item in items
    ]
    return compact_json(
        {
            "scenarios": columnar(
                scenarios,
                ["id", "name", "active", "type", "running", "shortDesc", "tags"],
            ),
        }
    )


@mcp.tool()
async def get_scenario_settings(
    project_key: str,
    scenario_id: str,
    ctx: Context,
) -> str:
    """Summarize a scenario's settings: run-as, triggers, steps, and reporters."""
    project_key = _require_non_empty_string(project_key, "project_key")
    scenario_id = _require_non_empty_string(scenario_id, "scenario_id")
    await ctx.info(f"Fetching settings for scenario {scenario_id} in {project_key}...")

    def _run():
        raw = (
            get_dss_client()
            .get_project(project_key)
            .get_scenario(scenario_id)
            .get_settings()
            .get_raw()
        )
        params = raw.get("params") or {}
        summary = {
            "id": raw.get("id"),
            "name": raw.get("name"),
            "active": raw.get("active"),
            "run_as": raw.get("runAsUser"),
            "triggers": [
                omit_empty({"type": trigger.get("type"), "active": trigger.get("active")})
                for trigger in (raw.get("triggers") or [])
            ],
            "steps": [
                omit_empty({"type": step.get("type"), "name": step.get("name")})
                for step in (params.get("steps") or [])
            ],
            "reporters": [
                _summarize_reporter(reporter)
                for reporter in (raw.get("reporters") or [])
            ],
        }
        return omit_empty(summary)

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def run_scenario(
    project_key: str,
    scenario_id: str,
    ctx: Context,
    wait_for_completion: bool = False,
    timeout_seconds: int = 600,
) -> str:
    """Request a manual run of an existing scenario.

    Direct execution of an existing asset; for creating or modifying assets use Cobuild.

    Defaults to fire-and-return (wait_for_completion=False): the scenario is fired and
    the run id is returned immediately; poll the result later with
    get_scenario_run_history(project_key, scenario_id). Set wait_for_completion=true to
    wait inline for the run to finish, bounded by timeout_seconds.

    Args:
        wait_for_completion: If true, wait up to timeout_seconds for the run to finish; if false (default), fire it and return the run id
        timeout_seconds: Max seconds to wait before returning "scenario_still_running" (only used when wait_for_completion=true)
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    scenario_id = _require_non_empty_string(scenario_id, "scenario_id")
    timeout_seconds = _require_positive_int(timeout_seconds, "timeout_seconds")

    await ctx.info(
        f"Triggering scenario {scenario_id} in {project_key} "
        f"(wait_for_completion={wait_for_completion})..."
    )

    trigger_fire = await run_blocking(
        lambda: get_dss_client()
        .get_project(project_key)
        .get_scenario(scenario_id)
        .run()
    )

    cancelled_payload = {
        "status": "scenario_run_cancelled",
        "project_key": project_key,
        "scenario_id": scenario_id,
        "hint": (
            "The trigger was cancelled before a run started (the scenario may already "
            "be running). Check get_scenario_run_history(project_key, scenario_id)."
        ),
    }

    if not wait_for_completion:
        state, run_id = await _resolve_scenario_run_id(
            trigger_fire, SCENARIO_RUN_ID_RESOLVE_BUDGET_SECONDS
        )
        if state == "cancelled":
            return compact_json(cancelled_payload)

        payload = {
            "status": "scenario_run_triggered",
            "project_key": project_key,
            "scenario_id": scenario_id,
        }
        if state == "resolved":
            payload["run_id"] = run_id
            payload["hint"] = (
                "Use get_scenario_run_history(project_key, scenario_id) to check the "
                "run result."
            )
        else:  # unresolved: run not yet created; return the trigger fire id instead
            payload["trigger_run_id"] = trigger_fire.run_id
            payload["hint"] = (
                "The scenario run id was not available yet; trigger_run_id identifies "
                "the trigger fire, not the run. Use "
                "get_scenario_run_history(project_key, scenario_id) to find the run."
            )
        return compact_json(payload)

    state, run_id, outcome = await _wait_for_scenario_run_result(
        trigger_fire, timeout_seconds
    )

    if state == "cancelled":
        return compact_json(cancelled_payload)

    if state == "timed_out":
        return compact_json(
            {
                "status": "scenario_still_running",
                "project_key": project_key,
                "scenario_id": scenario_id,
                **({"run_id": run_id} if run_id is not None else {}),
                "hint": (
                    "The scenario run did not finish within timeout_seconds. Do not "
                    "fire it again; poll get_scenario_run_history(project_key, "
                    "scenario_id) for the final outcome."
                ),
            }
        )

    top_level_status = (
        "scenario_run_completed"
        if outcome == "SUCCESS"
        else "scenario_run_completed_with_errors"
    )
    return compact_json(
        {
            "status": top_level_status,
            "project_key": project_key,
            "scenario_id": scenario_id,
            "run_id": run_id,
            "outcome": outcome,
        }
    )


@mcp.tool()
async def get_scenario_run_history(
    project_key: str,
    scenario_id: str,
    ctx: Context,
    limit: int = 10,
) -> str:
    """Get the last runs of a scenario."""
    project_key = _require_non_empty_string(project_key, "project_key")
    scenario_id = _require_non_empty_string(scenario_id, "scenario_id")
    limit = min(_require_positive_int(limit, "limit"), 50)

    await ctx.info(
        f"Fetching run history for scenario {scenario_id} in {project_key}..."
    )

    def _run():
        scenario = get_dss_client().get_project(project_key).get_scenario(scenario_id)
        runs = scenario.get_last_runs(limit=limit)
        summaries = []
        for run in runs:
            info = run.get_info()
            result = info.get("result") or {}
            trigger = (info.get("trigger") or {}).get("trigger") or {}
            summaries.append(
                {
                    "run_id": info.get("runId"),
                    "running": run.running,
                    "outcome": result.get("outcome"),
                    "start": info.get("start"),
                    "end": result.get("endTime"),
                    "trigger_type": trigger.get("type"),
                }
            )
        return summaries

    summaries = await run_blocking(_run)
    return compact_json(
        {
            "runs": columnar(
                summaries,
                ["run_id", "running", "outcome", "start", "end", "trigger_type"],
            ),
        }
    )
