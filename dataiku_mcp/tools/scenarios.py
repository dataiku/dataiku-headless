"""Scenario operations for Dataiku DSS."""

from fastmcp import Context

from .. import mcp
from .utils.async_executor import run_blocking
from .utils.serialization import columnar, compact_json
from .utils.auth import get_dss_client
from .utils.parsing import coerce_json_object as _coerce_json_object
from .utils.validation import (
    require_allowed_value as _require_allowed_value,
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

    def _run():
        scenario = get_dss_client().get_project(project_key).get_scenario(scenario_id)
        return scenario.get_settings().get_raw()

    raw = await run_blocking(_run)
    return compact_json(raw)


@mcp.tool()
async def run_scenario(
    project_key: str,
    scenario_id: str,
    ctx: Context,
    wait_for_completion: bool = True,
) -> str:
    """Request a manual run of a scenario.

    Args:
        wait_for_completion: If true, wait for the run to finish; if false, return immediately
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    scenario_id = _require_non_empty_string(scenario_id, "scenario_id")
    await ctx.info(
        f"Triggering scenario {scenario_id} in {project_key} "
        f"(wait_for_completion={wait_for_completion})..."
    )

    if not wait_for_completion:
        def _trigger():
            get_dss_client().get_project(project_key).get_scenario(scenario_id).run()

        await run_blocking(_trigger)
        return compact_json({
                "status": "scenario_run_triggered",
                "hint": "Use get_scenario_run_history to check the run result.",
            })

    def _run_and_wait():
        scenario = get_dss_client().get_project(project_key).get_scenario(scenario_id)
        trigger_fire = scenario.run()
        scenario_run = trigger_fire.wait_for_scenario_run(no_fail=True)
        if scenario_run is None:
            raise ValueError(
                f"Scenario {scenario_id} trigger was cancelled before a run could start "
                "(possibly because the scenario was already running)"
            )
        scenario_run.wait_for_completion(no_fail=True)
        info = scenario_run.get_info()
        return {
            "run_id": scenario_run.id,
            "outcome": (info.get("result") or {}).get("outcome"),
        }

    result = await run_blocking(_run_and_wait)

    outcome = result["outcome"]
    top_level_status = (
        "scenario_run_completed"
        if outcome == "SUCCESS"
        else "scenario_run_completed_with_errors"
    )

    return compact_json({
            "status": top_level_status,
            "run_id": result["run_id"],
            "outcome": outcome,
        })


@mcp.tool()
async def get_scenario_run_history(
    project_key: str,
    scenario_id: str,
    ctx: Context,
    limit: int = 10,
) -> str:
    """Get the last runs of a scenario.

    Args:
        limit: Number of recent runs to return (max 50)
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    scenario_id = _require_non_empty_string(scenario_id, "scenario_id")
    limit = _require_positive_int(limit, "limit")
    limit = min(limit, 50)

    await ctx.info(
        f"Fetching run history for scenario {scenario_id} in {project_key}..."
    )

    def _run():
        scenario = get_dss_client().get_project(project_key).get_scenario(scenario_id)
        runs = scenario.get_last_runs(limit=limit)
        summaries = []
        for r in runs:
            info = r.get_info()
            result = info.get("result") or {}
            trigger = (info.get("trigger") or {}).get("trigger") or {}
            summaries.append(
                {
                    "run_id": info.get("runId"),
                    "running": r.running,
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
async def create_scenario(
    project_key: str,
    scenario_name: str,
    ctx: Context,
    type: str = "step_based",
    definition=None,
) -> str:
    """Create a new scenario in the project.

    Args:
        scenario_name: Display name (uniqueness recommended but not required)
        type: One of "step_based" or "custom_python"
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    scenario_name = _require_non_empty_string(scenario_name, "scenario_name")
    type = _require_allowed_value(type, "type", {"step_based", "custom_python"})
    definition_obj = _coerce_json_object(definition, "definition") if definition is not None else None

    await ctx.info(f"Creating {type} scenario '{scenario_name}' in {project_key}...")

    def _run():
        project = get_dss_client().get_project(project_key)
        scenario = project.create_scenario(scenario_name, type, definition_obj)
        return scenario.id

    scenario_id = await run_blocking(_run)

    return compact_json({
            "scenario_id": scenario_id,
            "type": type,
        })


@mcp.tool()
async def list_messaging_channels(ctx: Context) -> str:
    """List the messaging channels configured on this DSS instance (used as reporter channelIds in scenarios)."""
    await ctx.info("Listing messaging channels...")

    channels = await run_blocking(
        lambda: get_dss_client().list_messaging_channels()
    )

    result = [
        {
            "id": ch.id,
            "type": ch.type,
            "family": ch.family,
            "default_sender": ch.get_raw().get("sender"),
        }
        for ch in channels
    ]

    return compact_json({"channels": columnar(result, ["id", "type", "family", "default_sender"])})


@mcp.tool()
async def delete_scenario(
    project_key: str,
    scenario_id: str,
    ctx: Context,
) -> str:
    """Delete the scenario."""
    project_key = _require_non_empty_string(project_key, "project_key")
    scenario_id = _require_non_empty_string(scenario_id, "scenario_id")
    await ctx.info(f"Deleting scenario {scenario_id} in {project_key}...")

    def _run():
        get_dss_client().get_project(project_key).get_scenario(scenario_id).delete()
        return {}

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def set_scenario_settings(
    project_key: str,
    scenario_id: str,
    new_settings,
    ctx: Context,
) -> str:
    """Set the full scenario settings (steps, triggers, reporters, active flag).

    Args:
        new_settings: A modified version of the object returned by get_scenario_settings
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    scenario_id = _require_non_empty_string(scenario_id, "scenario_id")
    settings_obj = _coerce_json_object(new_settings, "new_settings")

    await ctx.info(f"Updating settings for scenario {scenario_id} in {project_key}...")

    def _run():
        scenario = get_dss_client().get_project(project_key).get_scenario(scenario_id)
        current = scenario.get_settings()
        raw = current.get_raw()  # reference to current.data — mutate in-place for save()
        raw.clear()
        raw.update(settings_obj)
        current.save()

    await run_blocking(_run)

    return compact_json({})
