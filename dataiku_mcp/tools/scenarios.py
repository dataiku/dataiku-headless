"""Scenario inspection and execution tools for Dataiku DSS."""

import asyncio
import time

from fastmcp import Context

from .. import mcp
from .utils.async_executor import run_blocking
from .utils.auth import get_dss_client
from .utils.serialization import columnar, compact_json
from .utils.validation import (
    require_non_empty_string as _require_non_empty_string,
    require_positive_int as _require_positive_int,
)

SCENARIO_POLL_INTERVAL_SECONDS = 2
# DSS creates a scenario run asynchronously after firing its trigger. Keep this
# lookup short; callers can always use run history if the run id appears later.
SCENARIO_RUN_ID_RESOLVE_BUDGET_SECONDS = 4
MAX_SCENARIO_WAIT_SECONDS = 3600


async def _resolve_scenario_run_id(trigger_fire, budget_seconds: int):
    """Return the real scenario-run id, not the trigger-fire id, when available."""
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
    """Poll a fired trigger and its run within one explicit deadline.

    ``timeout_seconds`` is a soft deadline: it is checked between SDK polls
    (``get_scenario_run`` / ``refresh`` / ``is_cancelled``), not inside them. The
    installed DSS client sets no per-request HTTP timeout, so a single hung call
    can make the wait exceed ``timeout_seconds``. The run is never cancelled by a
    timeout; the caller polls ``get_scenario_run_history``.
    """
    deadline = time.monotonic() + timeout_seconds
    scenario_run = None
    while True:
        if scenario_run is None:
            scenario_run = await run_blocking(trigger_fire.get_scenario_run)
            if scenario_run is None and await run_blocking(
                lambda: trigger_fire.is_cancelled(refresh=True)
            ):
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
    """Get the full scenario settings (steps, triggers, reporters)."""
    project_key = _require_non_empty_string(project_key, "project_key")
    scenario_id = _require_non_empty_string(scenario_id, "scenario_id")
    await ctx.info(f"Fetching settings for scenario {scenario_id} in {project_key}...")

    raw = await run_blocking(
        lambda: (
            get_dss_client().get_project(project_key).get_scenario(scenario_id)
            .get_settings()
            .get_raw()
        )
    )
    return compact_json(raw)


@mcp.tool()
async def run_scenario(
    project_key: str,
    scenario_id: str,
    ctx: Context,
    wait_for_completion: bool = False,
    timeout_seconds: int = 600,
) -> str:
    """Run one existing scenario; creation and modification remain with Cobuild.

    When wait_for_completion=true, timeout_seconds is a soft deadline checked
    between SDK polls — a single hung DSS HTTP call can exceed it. A timeout
    returns the run id (when known) for polling get_scenario_run_history; the run
    is never cancelled. Every post-start response carries trigger_fire_id, and
    run_id additionally once DSS has materialized the run, so the caller can
    always identify this request in run history instead of re-triggering.
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    scenario_id = _require_non_empty_string(scenario_id, "scenario_id")
    timeout_seconds = _require_positive_int(timeout_seconds, "timeout_seconds")
    if timeout_seconds > MAX_SCENARIO_WAIT_SECONDS:
        raise ValueError(
            f"'timeout_seconds' must be <= {MAX_SCENARIO_WAIT_SECONDS}"
        )
    client = get_dss_client()

    await ctx.info(
        f"Triggering scenario {scenario_id} in {project_key} "
        f"(wait_for_completion={wait_for_completion})..."
    )
    try:
        trigger_fire = await run_blocking(
            lambda: client.get_project(project_key).get_scenario(scenario_id).run()
        )
    except Exception as exc:
        raise RuntimeError(
            f"DSS did not return a trigger-fire handle for scenario '{scenario_id}'. "
            "Inspect scenario run history before retrying because the trigger may "
            "have reached DSS."
        ) from exc
    cancelled_payload = {
        "status": "scenario_run_cancelled",
        "project_key": project_key,
        "scenario_id": scenario_id,
        "trigger_fire_id": trigger_fire.run_id,
        "hint": (
            "The trigger was cancelled before a run started; the scenario may "
            "already be running. Check get_scenario_run_history."
        ),
    }

    if not wait_for_completion:
        try:
            state, run_id = await _resolve_scenario_run_id(
                trigger_fire, SCENARIO_RUN_ID_RESOLVE_BUDGET_SECONDS
            )
        except Exception as exc:
            raise RuntimeError(
                f"Scenario trigger fire '{trigger_fire.run_id}' was accepted, but "
                "its run id could not be resolved. Use get_scenario_run_history; "
                "do not trigger the scenario again."
            ) from exc
        if state == "cancelled":
            return compact_json(cancelled_payload)
        payload = {
            "status": "scenario_run_triggered",
            "project_key": project_key,
            "scenario_id": scenario_id,
            "trigger_fire_id": trigger_fire.run_id,
        }
        if state == "resolved":
            payload["run_id"] = run_id
            payload["hint"] = (
                "Use get_scenario_run_history(project_key, scenario_id) to check "
                "the final result."
            )
        else:
            payload["hint"] = (
                "The scenario run id was not available yet. trigger_fire_id "
                "identifies only the trigger request; use run history to find the "
                "scenario run."
            )
        return compact_json(payload)

    try:
        state, run_id, outcome = await _wait_for_scenario_run_result(
            trigger_fire, timeout_seconds
        )
    except Exception as exc:
        raise RuntimeError(
            f"Scenario trigger fire '{trigger_fire.run_id}' was accepted, but "
            "status polling failed. Use get_scenario_run_history; do not trigger "
            "the scenario again."
        ) from exc
    if state == "cancelled":
        return compact_json(cancelled_payload)
    if state == "timed_out":
        return compact_json(
            {
                "status": "scenario_run_still_running",
                "project_key": project_key,
                "scenario_id": scenario_id,
                "trigger_fire_id": trigger_fire.run_id,
                **({"run_id": run_id} if run_id is not None else {}),
                "hint": (
                    "The scenario did not finish within timeout_seconds. Do not "
                    "trigger it again; poll get_scenario_run_history. If run_id is "
                    "absent, DSS has not materialized the run yet; trigger_fire_id "
                    "identifies this trigger request."
                ),
            }
        )

    return compact_json(
        {
            "status": (
                "scenario_run_completed"
                if outcome == "SUCCESS"
                else "scenario_run_completed_with_errors"
            ),
            "project_key": project_key,
            "scenario_id": scenario_id,
            "trigger_fire_id": trigger_fire.run_id,
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


@mcp.tool()
async def list_messaging_channels(ctx: Context) -> str:
    """List the messaging channels configured on this DSS instance."""
    await ctx.info("Listing messaging channels...")

    channels = await run_blocking(lambda: get_dss_client().list_messaging_channels())
    result = [
        {
            "id": channel.id,
            "type": channel.type,
            "family": channel.family,
            "default_sender": channel.get_raw().get("sender"),
        }
        for channel in channels
    ]
    return compact_json(
        {"channels": columnar(result, ["id", "type", "family", "default_sender"])}
    )
