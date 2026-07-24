"""Scenario inspection tools for Dataiku DSS."""

from fastmcp import Context

from .. import mcp
from .utils.async_executor import run_blocking
from .utils.auth import get_dss_client
from .utils.serialization import columnar, compact_json
from .utils.validation import (
    require_non_empty_string as _require_non_empty_string,
    require_positive_int as _require_positive_int,
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
    """Get the full scenario settings (steps, triggers, reporters)."""
    project_key = _require_non_empty_string(project_key, "project_key")
    scenario_id = _require_non_empty_string(scenario_id, "scenario_id")
    await ctx.info(f"Fetching settings for scenario {scenario_id} in {project_key}...")

    raw = await run_blocking(
        lambda: (
            get_dss_client()
            .get_project(project_key)
            .get_scenario(scenario_id)
            .get_settings()
            .get_raw()
        )
    )
    return compact_json(raw)


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
