# Copyright 2026 Dataiku SAS
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Scenario inspection, execution, and Python-script scenario authoring tools."""

import asyncio
import time
from typing import Annotated

from dataikuapi.utils import DataikuException
from fastmcp import Context
from pydantic import Field

from ..instance_policy import (
    ADMIN_POLICY,
    PROJECT_EDIT_POLICY,
    PROJECT_EXECUTION_POLICY,
    PROJECT_READ_POLICY,
)
from ..server import mcp
from ..auth import get_dss_client
from ..executors import run_blocking
from .utils.errors import safe_error_text as _safe_error_text
from .utils.serialization import columnar, compact_json
from .utils.validation import (
    require_non_empty_string as _require_non_empty_string,
    require_int_in_range as _require_int_in_range,
    require_positive_int as _require_positive_int,
)

SCENARIO_POLL_INTERVAL_SECONDS = 2
# Dataiku creates a scenario run asynchronously after firing its trigger.
SCENARIO_RUN_ID_RESOLVE_BUDGET_SECONDS = 4
MAX_SCENARIO_WAIT_SECONDS = 3600

PythonScript = Annotated[
    str, Field(description="Complete Python source; replaces the whole script.")
]


def _python_scenario_settings(scenario, scenario_id: str):
    """Read one scenario's settings, refusing a scenario without a Python script."""
    settings = scenario.get_settings()
    scenario_type = settings.get_raw().get("type")
    if scenario_type != "custom_python":
        raise ValueError(
            f"Scenario '{scenario_id}' is a '{scenario_type}' scenario; only "
            "Python-script (custom_python) scenarios have a script"
        )
    return settings


def _save_script(settings, script: str) -> None:
    # The SDK saves the definition before the script. That definition save runs
    # Dataiku's code-permission and license checks, which the script endpoint
    # alone does not, so a refused caller never reaches the script write.
    settings.code = script
    settings.save()


def _python_scenario_summary(project_key: str, settings) -> dict:
    raw = settings.get_raw()
    return {
        "project_key": project_key,
        "scenario_id": raw.get("id"),
        "name": raw.get("name"),
        "type": raw.get("type"),
        "active": raw.get("active", False),
        "trigger_count": len(raw.get("triggers") or []),
    }


async def _resolve_scenario_run_id(trigger_fire, budget_seconds: int):
    """Resolve the scenario run id after a trigger fires."""
    deadline = time.monotonic() + budget_seconds
    while True:
        try:
            scenario_run = await run_blocking(trigger_fire.get_scenario_run)
            if scenario_run is not None:
                return "resolved", scenario_run.id, None
            if await run_blocking(lambda: trigger_fire.is_cancelled(refresh=True)):
                return "cancelled", None, None
        except Exception as exc:
            return "poll_failed", None, exc
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return "unresolved", None, None
        await asyncio.sleep(min(SCENARIO_POLL_INTERVAL_SECONDS, remaining))


async def _wait_for_scenario_run_result(trigger_fire, timeout_seconds: int):
    """Wait for a triggered scenario run within the timeout."""
    deadline = time.monotonic() + timeout_seconds
    scenario_run = None
    observed_run_id = None
    while True:
        try:
            if scenario_run is None:
                scenario_run = await run_blocking(trigger_fire.get_scenario_run)
                if scenario_run is None and await run_blocking(
                    lambda: trigger_fire.is_cancelled(refresh=True)
                ):
                    return "cancelled", None, None, None
            else:
                await run_blocking(scenario_run.refresh)

            if scenario_run is not None and observed_run_id is None:
                try:
                    observed_run_id = scenario_run.id
                except Exception:
                    observed_run_id = None

            if scenario_run is not None and not scenario_run.running:
                result = scenario_run.get_info().get("result") or {}
                return "completed", observed_run_id, result.get("outcome"), None
        except Exception as exc:
            return "poll_failed", observed_run_id, None, exc

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return "timed_out", observed_run_id, None, None
        await asyncio.sleep(min(SCENARIO_POLL_INTERVAL_SECONDS, remaining))


@mcp.tool(
    meta=PROJECT_READ_POLICY,
    title="List Scenarios",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": False,
    },
)
async def list_scenarios(project_key: str, ctx: Context) -> str:
    """Find a project's scenarios, their IDs, and what is running now."""
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


@mcp.tool(
    meta=PROJECT_READ_POLICY,
    title="Get Scenario Settings",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": False,
    },
)
async def get_scenario_settings(
    project_key: str,
    scenario_id: str,
    ctx: Context,
) -> str:
    """Read a scenario's steps or Python script, its triggers, and who it reports to."""
    project_key = _require_non_empty_string(project_key, "project_key")
    scenario_id = _require_non_empty_string(scenario_id, "scenario_id")
    await ctx.info(f"Fetching settings for scenario {scenario_id} in {project_key}...")

    def _run():
        scenario = get_dss_client().get_project(project_key).get_scenario(scenario_id)
        settings = scenario.get_settings()
        raw = settings.get_raw()
        if raw.get("type") == "custom_python":
            return {**raw, "script": settings.code}
        return raw

    return compact_json(await run_blocking(_run))


@mcp.tool(
    meta=PROJECT_EDIT_POLICY,
    title="Create Python Scenario",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def create_python_scenario(
    project_key: str,
    name: str,
    script: PythonScript,
    ctx: Context,
) -> str:
    """Create a scenario defined by a Python script, inactive and without triggers."""
    project_key = _require_non_empty_string(project_key, "project_key")
    name = _require_non_empty_string(name, "name")
    _require_non_empty_string(script, "script")
    await ctx.info(f"Creating Python scenario '{name}' in {project_key}...")

    def _run():
        project = get_dss_client().get_project(project_key)
        try:
            scenario = project.create_scenario(
                name,
                "custom_python",
                definition={
                    "params": {},
                    "active": False,
                    "triggers": [],
                    "reporters": [],
                },
            )
        except DataikuException:
            # Dataiku answered and refused, so nothing was created.
            raise
        except Exception as exc:
            raise RuntimeError(
                f"Dataiku did not confirm creating scenario '{name}'. Check "
                "list_scenarios before retrying because the request may have "
                "reached Dataiku."
            ) from exc

        # Dataiku creates the scenario with a sample script, so until the real
        # script is confirmed the result must say the scenario is not ready.
        error = None
        try:
            _save_script(_python_scenario_settings(scenario, scenario.id), script)
            saved = _python_scenario_settings(scenario, scenario.id)
            if saved.code == script:
                return {
                    "status": "python_scenario_created",
                    **_python_scenario_summary(project_key, saved),
                }
        except Exception as exc:
            error = exc
        return {
            "status": "python_scenario_script_unconfirmed",
            "project_key": project_key,
            "scenario_id": scenario.id,
            "name": name,
            **(
                {"error_type": type(error).__name__, "error": _safe_error_text(error)}
                if error is not None
                else {}
            ),
            "hint": (
                "The scenario exists, inactive and without triggers, but its script "
                "was not confirmed and may still be Dataiku's sample script. Do not "
                "run it. Call set_python_scenario_script with this scenario_id and "
                "the same script; do not create the scenario again."
            ),
        }

    return compact_json(await run_blocking(_run))


@mcp.tool(
    meta=PROJECT_EDIT_POLICY,
    title="Set Python Scenario Script",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def set_python_scenario_script(
    project_key: str,
    scenario_id: str,
    script: PythonScript,
    ctx: Context,
) -> str:
    """Replace the script of an existing Python-script scenario, keeping its settings."""
    project_key = _require_non_empty_string(project_key, "project_key")
    scenario_id = _require_non_empty_string(scenario_id, "scenario_id")
    _require_non_empty_string(script, "script")
    await ctx.info(f"Saving the script of scenario {scenario_id} in {project_key}...")

    def _run():
        scenario = get_dss_client().get_project(project_key).get_scenario(scenario_id)
        _save_script(_python_scenario_settings(scenario, scenario_id), script)
        saved = _python_scenario_settings(scenario, scenario_id)
        if saved.code != script:
            raise RuntimeError(
                f"Dataiku did not confirm the new script of scenario '{scenario_id}'. "
                "Inspect it with get_scenario_settings; repeating this call is safe."
            )
        return _python_scenario_summary(project_key, saved)

    return compact_json(await run_blocking(_run))


@mcp.tool(
    meta=PROJECT_EXECUTION_POLICY,
    title="Run Scenario",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def run_scenario(
    project_key: str,
    scenario_id: str,
    ctx: Context,
    wait_for_completion: Annotated[
        bool, Field(description="False returns as soon as the run is triggered.")
    ] = False,
    timeout_seconds: Annotated[
        int, Field(description="Soft bound on the inline wait, checked between polls.")
    ] = 600,
) -> str:
    """Trigger an existing scenario, which may build, modify, or delete assets."""
    project_key = _require_non_empty_string(project_key, "project_key")
    scenario_id = _require_non_empty_string(scenario_id, "scenario_id")
    timeout_seconds = _require_int_in_range(
        timeout_seconds, "timeout_seconds", 1, MAX_SCENARIO_WAIT_SECONDS
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
            f"Dataiku did not return a trigger-fire handle for scenario '{scenario_id}'. "
            "Inspect scenario run history before retrying because the trigger may "
            "have reached Dataiku."
        ) from exc

    try:
        trigger_fire_id = trigger_fire.run_id
    except Exception:
        trigger_fire_id = None

    cancelled_payload = {
        "status": "scenario_run_cancelled",
        "project_key": project_key,
        "scenario_id": scenario_id,
        "trigger_fire_id": trigger_fire_id,
        "hint": (
            "The trigger was cancelled before a run started; the scenario may "
            "already be running. Check get_scenario_run_history."
        ),
    }

    def _poll_failed_payload(run_id, error) -> dict:
        """Build a structured post-start failure response."""
        return {
            "status": "scenario_poll_failed",
            "project_key": project_key,
            "scenario_id": scenario_id,
            "trigger_fire_id": trigger_fire_id,
            **({"run_id": run_id} if run_id is not None else {}),
            "error_type": type(error).__name__,
            "error": _safe_error_text(error),
            "hint": (
                "The trigger was accepted but status polling failed. Do not "
                "trigger the scenario again; poll get_scenario_run_history and "
                "match run_id, or trigger_fire_id, against its rows."
            ),
        }

    if not wait_for_completion:
        state, run_id, error = await _resolve_scenario_run_id(
            trigger_fire, SCENARIO_RUN_ID_RESOLVE_BUDGET_SECONDS
        )
        if state == "poll_failed":
            return compact_json(_poll_failed_payload(run_id, error))
        if state == "cancelled":
            return compact_json(cancelled_payload)
        payload = {
            "status": "scenario_run_triggered",
            "project_key": project_key,
            "scenario_id": scenario_id,
            "trigger_fire_id": trigger_fire_id,
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

    state, run_id, outcome, error = await _wait_for_scenario_run_result(
        trigger_fire, timeout_seconds
    )
    if state == "poll_failed":
        return compact_json(_poll_failed_payload(run_id, error))
    if state == "cancelled":
        return compact_json(cancelled_payload)
    if state == "timed_out":
        return compact_json(
            {
                "status": "scenario_run_still_running",
                "project_key": project_key,
                "scenario_id": scenario_id,
                "trigger_fire_id": trigger_fire_id,
                **({"run_id": run_id} if run_id is not None else {}),
                "hint": (
                    "The scenario did not finish within timeout_seconds. Do not "
                    "trigger it again; poll get_scenario_run_history. If run_id is "
                    "absent, Dataiku has not materialized the run yet; match "
                    "trigger_fire_id against the run-history rows to find it."
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
            "trigger_fire_id": trigger_fire_id,
            "run_id": run_id,
            "outcome": outcome,
        }
    )


@mcp.tool(
    meta=PROJECT_EXECUTION_POLICY,
    title="Get Scenario Run History",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": False,
    },
)
async def get_scenario_run_history(
    project_key: str,
    scenario_id: str,
    ctx: Context,
    limit: Annotated[int, Field(description="Most recent runs returned.")] = 10,
) -> str:
    """Check whether a scenario's recent runs succeeded, and why they failed."""
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
            # Dataiku trigger payloads are not always well-formed; keep usable ids
            # and null the rest so one bad record does not crash the read.
            raw_trigger_fire = info.get("trigger")
            trigger_fire = (
                raw_trigger_fire if isinstance(raw_trigger_fire, dict) else {}
            )
            fire_id = trigger_fire.get("runId")
            if isinstance(fire_id, bool) or not isinstance(fire_id, (str, int)):
                fire_id = None
            raw_trigger = trigger_fire.get("trigger")
            trigger = raw_trigger if isinstance(raw_trigger, dict) else {}
            summaries.append(
                {
                    "run_id": info.get("runId"),
                    "running": run.running,
                    "outcome": result.get("outcome"),
                    "start": info.get("start"),
                    "end": result.get("endTime"),
                    "trigger_type": trigger.get("type"),
                    "trigger_fire_id": fire_id,
                }
            )
        return summaries

    summaries = await run_blocking(_run)
    return compact_json(
        {
            "runs": columnar(
                summaries,
                [
                    "run_id",
                    "running",
                    "outcome",
                    "start",
                    "end",
                    "trigger_type",
                    "trigger_fire_id",
                ],
            ),
        }
    )


@mcp.tool(
    meta=ADMIN_POLICY,
    title="List Messaging Channels",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": False,
    },
)
async def list_messaging_channels(ctx: Context) -> str:
    """Find the channels a scenario reporter can send to."""
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
