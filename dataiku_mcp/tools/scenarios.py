"""Scenario inspection tools for Dataiku DSS."""

from fastmcp import Context

from .. import mcp
from .utils.async_executor import run_blocking
from .utils.auth import get_dss_client
from .utils.serialization import columnar, compact_json, omit_empty
from .utils.validation import (
    require_non_empty_string as _require_non_empty_string,
    require_positive_int as _require_positive_int,
)


def _summarize_reporter(reporter: dict) -> dict:
    messaging = reporter.get("messaging") or {}
    configuration = messaging.get("configuration") or {}
    return omit_empty(
        {
            "messaging_channel": configuration.get("channelId") or messaging.get("type"),
            "condition": reporter.get("runCondition"),
        }
    )


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
