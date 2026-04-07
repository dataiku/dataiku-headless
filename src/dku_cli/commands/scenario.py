"""dku scenario — list, run, abort, status, runs, last-run, set-metadata, create, delete, get/set-definition, triggers."""

from __future__ import annotations

import time

import typer

from dku_cli.errors import exit_with_error, handle_api_error, is_already_exists_error
from dku_cli.helpers import get_client_from_ctx, read_json_input, resolve_project
from dku_cli.output import (
    error,
    info,
    render,
    render_raw,
    resolve_output_format,
    success,
    warn,
)

app = typer.Typer(help="Manage DSS scenarios.")


def _poll_scenario_outcome(
    scenario, poll_interval: float = 3.0, timeout: float = 3600
) -> str:
    """Poll scenario last runs until completion or timeout."""
    elapsed = 0.0
    time.sleep(1)  # Brief wait for new run to register before first poll
    elapsed += 1.0
    while elapsed < timeout:
        runs = scenario.get_last_runs(limit=1)
        if runs:
            run = runs[0]
            outcome = run.outcome if hasattr(run, "outcome") else run.get("outcome")
            if outcome is not None:
                return outcome
        time.sleep(poll_interval)
        elapsed += poll_interval
    return "TIMEOUT"


@app.command("list")
def list_scenarios(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List scenarios in a project."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        scenarios = proj.list_scenarios()

        data = []
        for s in scenarios:
            data.append(
                {
                    "id": s.get("id", ""),
                    "name": s.get("name", ""),
                    "active": str(s.get("active", False)),
                    "type": s.get("type", ""),
                }
            )

        render(
            data,
            ["id", "name", "type", "active"],
            output_format=output,
            title=f"Scenarios ({project_key})",
        )
    except Exception as e:
        handle_api_error(e)


@app.command()
def run(
    ctx: typer.Context,
    scenario_id: str = typer.Argument(help="Scenario ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    wait: bool = typer.Option(False, "--wait", "-w", help="Wait for completion"),
) -> None:
    """Run a scenario."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        scenario = proj.get_scenario(scenario_id)
        trigger = scenario.run()

        success(f"Scenario '{scenario_id}' triggered")

        if wait:
            info("Waiting for completion...")
            # DSSTriggerFire may not have wait_for_result() in all dataikuapi versions.
            if hasattr(trigger, "wait_for_result") and callable(
                getattr(trigger, "wait_for_result", None)
            ):
                try:
                    result = trigger.wait_for_result()
                    outcome = (
                        result.get("scenarioRun", {})
                        .get("result", {})
                        .get("outcome", "unknown")
                    )
                except (AttributeError, TypeError):
                    outcome = _poll_scenario_outcome(scenario)
            else:
                outcome = _poll_scenario_outcome(scenario)

            if outcome == "SUCCESS":
                success(f"Scenario completed: {outcome}")
            else:
                error(f"Scenario completed: {outcome}")
    except Exception as e:
        handle_api_error(e)


@app.command()
def abort(
    ctx: typer.Context,
    scenario_id: str = typer.Argument(help="Scenario ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Abort a running scenario."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        scenario = proj.get_scenario(scenario_id)
        scenario.abort()
        success(f"Abort requested for scenario '{scenario_id}'")
    except Exception as e:
        handle_api_error(e)


@app.command()
def status(
    ctx: typer.Context,
    scenario_id: str = typer.Argument(help="Scenario ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show last run status of a scenario."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        scenario = proj.get_scenario(scenario_id)
        runs = scenario.get_last_runs(limit=5)

        data = []
        for r in runs:
            trigger = r.trigger or {}
            data.append(
                {
                    "run_id": r.id,
                    "start": str(r.start_time) if r.start_time else "",
                    "outcome": r.outcome or "",
                    "trigger": trigger.get("type", ""),
                }
            )

        render(
            data,
            ["run_id", "start", "outcome", "trigger"],
            output_format=output,
            title=f"Scenario: {scenario_id} — Recent Runs",
        )
    except Exception as e:
        handle_api_error(e)


@app.command()
def create(
    ctx: typer.Context,
    name: str = typer.Argument(help="Scenario name"),
    type: str = typer.Option("step_based", "--type", "-t", help="Scenario type"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    definition: str | None = typer.Option(
        None,
        "--definition",
        "-d",
        help="JSON definition (string, @file.json, or - for stdin)",
    ),
    if_not_exists: bool = typer.Option(
        False, "--if-not-exists", help="Skip if scenario already exists"
    ),
) -> None:
    """Create a new scenario."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        defn = read_json_input(definition)
        # dataikuapi signature: create_scenario(scenario_name, type, definition)
        kwargs: dict = {"scenario_name": name, "type": type}
        if defn is not None:
            kwargs["definition"] = defn
        scenario = proj.create_scenario(**kwargs)
        success(f"Created scenario '{name}' (id={scenario.id})")
    except Exception as e:
        if if_not_exists and is_already_exists_error(e):
            warn(f"Scenario '{name}' already exists in {project_key}, skipping create")
            return
        handle_api_error(e)


@app.command()
def delete(
    ctx: typer.Context,
    scenario_id: str = typer.Argument(help="Scenario ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Delete a scenario."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        scenario = proj.get_scenario(scenario_id)
        scenario.delete()
        success(f"Deleted scenario '{scenario_id}'")
    except Exception as e:
        handle_api_error(e)


@app.command("get-definition")
def get_definition(
    ctx: typer.Context,
    scenario_id: str = typer.Argument(help="Scenario ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Get the raw definition of a scenario as JSON."""
    project_key = resolve_project(project)
    output = resolve_output_format(output, allowed=("json",), default="json")
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        scenario = proj.get_scenario(scenario_id)
        defn = scenario.get_definition()
        if hasattr(defn, "get_raw"):
            defn = defn.get_raw()
        render_raw(defn, output_format=output)
    except Exception as e:
        handle_api_error(e)


@app.command("set-definition")
def set_definition(
    ctx: typer.Context,
    scenario_id: str = typer.Argument(help="Scenario ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    definition: str = typer.Option(
        ...,
        "--definition",
        "-d",
        help="JSON definition (string, @file.json, or - for stdin)",
    ),
) -> None:
    """Update a scenario's definition from JSON."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        scenario = proj.get_scenario(scenario_id)
        new_def = read_json_input(definition)
        scenario.set_definition(new_def)
        success(f"Updated definition for scenario '{scenario_id}'")
    except Exception as e:
        handle_api_error(e)


# ---------------------------------------------------------------------------
# Run history commands
# ---------------------------------------------------------------------------


@app.command("last-run")
def last_run(
    ctx: typer.Context,
    scenario_id: str = typer.Argument(help="Scenario ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show the last finished run of a scenario."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        scenario = proj.get_scenario(scenario_id)
        run = scenario.get_last_finished_run()
        run_data = (
            run.get_info()
            if hasattr(run, "get_info")
            else {"id": run.id, "state": run.outcome}
        )
        render_raw(run_data, output_format=output)
    except ValueError:
        exit_with_error(
            "No finished runs found.",
            details=[
                f"Run it first: dku scenario run {scenario_id} -P {project_key}",
            ],
        )
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def runs(
    ctx: typer.Context,
    scenario_id: str = typer.Argument(help="Scenario ID"),
    limit: int = typer.Option(10, "--limit", help="Max number of runs to show"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List recent runs of a scenario."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        scenario = proj.get_scenario(scenario_id)
        run_list = scenario.get_last_runs(limit=limit)
        data = []
        for r in run_list:
            start = ""
            if hasattr(r, "get_start_time"):
                try:
                    start = str(r.get_start_time())
                except Exception:
                    pass
            data.append(
                {
                    "id": r.id,
                    "state": getattr(r, "outcome", ""),
                    "start": start,
                }
            )
        render(
            data,
            ["id", "state", "start"],
            output_format=output,
            title=f"Runs ({scenario_id})",
        )
    except Exception as e:
        handle_api_error(e)


# ---------------------------------------------------------------------------
# Metadata commands
# ---------------------------------------------------------------------------


@app.command("set-metadata")
def set_metadata(
    ctx: typer.Context,
    scenario_id: str = typer.Argument(help="Scenario ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    description: str | None = typer.Option(
        None, "--description", "-d", help="Scenario description"
    ),
    short_desc: str | None = typer.Option(
        None, "--short-desc", help="Short description"
    ),
    tags: str | None = typer.Option(
        None, "--tags", help="Comma-separated tags (replaces existing)"
    ),
) -> None:
    """Update scenario description, short description, and/or tags.

    No JSON needed — updates metadata fields via get/set-definition.
    """
    if description is None and short_desc is None and tags is None:
        error("Provide --description, --short-desc, and/or --tags to update.")
        raise typer.Exit(1)
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        scenario = proj.get_scenario(scenario_id)
        defn = scenario.get_definition()
        if hasattr(defn, "get_raw"):
            defn = defn.get_raw()

        if description is not None:
            defn["description"] = description
        if short_desc is not None:
            defn["shortDesc"] = short_desc
        if tags is not None:
            defn["tags"] = [t.strip() for t in tags.split(",") if t.strip()]

        scenario.set_definition(defn)
        success(f"Updated metadata for scenario '{scenario_id}'")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


# ---------------------------------------------------------------------------
# Trigger helpers
# ---------------------------------------------------------------------------


def _trigger_description(trigger: dict) -> str:
    """Produce a human-readable description of a trigger for table display."""
    ttype = trigger.get("type", "")
    params = trigger.get("params", {})

    if ttype == "temporal":
        freq = params.get("frequency", "")
        hour = params.get("hour", 0)
        minute = params.get("minute", 0)
        tz = params.get("timezone", "SERVER")
        repeat = params.get("repeatFrequency", 1)
        if freq == "Minutely":
            return f"Every {repeat} min"
        if freq == "Hourly":
            return f"Every {repeat}h at :{minute:02d} ({tz})"
        if freq == "Daily":
            return f"Daily at {hour:02d}:{minute:02d} ({tz})"
        if freq == "Weekly":
            days = params.get("daysOfWeek", [])
            return f"Weekly {','.join(days)} at {hour:02d}:{minute:02d} ({tz})"
        if freq == "Monthly":
            return f"Monthly at {hour:02d}:{minute:02d} ({tz})"
        return f"Temporal ({freq})"

    if ttype == "ds_modified":
        watches = params.get("watches", [])
        names = [w.get("itemId", "?") for w in watches]
        return f"watches: {', '.join(names)}" if names else "dataset change"

    if ttype == "sql_query":
        return "SQL query trigger"

    if ttype == "custom_python":
        return "Custom Python trigger"

    return ttype or "unknown"


def _add_trigger(
    ctx: typer.Context, scenario_id: str, project: str | None, trigger_dict: dict
) -> None:
    """Shared logic for all trigger add commands."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        scenario = proj.get_scenario(scenario_id)
        settings = scenario.get_settings()
        settings.raw_triggers.append(trigger_dict)
        idx = len(settings.raw_triggers) - 1
        settings.save()
        ttype = trigger_dict.get("type", "unknown")
        success(f"Added {ttype} trigger to scenario '{scenario_id}' at index {idx}")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


# ---------------------------------------------------------------------------
# Trigger commands
# ---------------------------------------------------------------------------


@app.command("list-triggers")
def list_triggers(
    ctx: typer.Context,
    scenario_id: str = typer.Argument(help="Scenario ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List triggers on a scenario."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        scenario = proj.get_scenario(scenario_id)
        settings = scenario.get_settings()
        triggers = settings.raw_triggers

        if output == "json":
            render_raw(triggers, output_format="json")
            return

        if not triggers:
            info(
                f"No triggers on scenario '{scenario_id}'. "
                f"Add one: dku scenario add-trigger-dataset {scenario_id} "
                f"--dataset DS_NAME -P {project_key}"
            )
            return

        rows = []
        for i, t in enumerate(triggers):
            rows.append(
                {
                    "index": str(i),
                    "type": t.get("type", ""),
                    "active": str(t.get("active", False)),
                    "description": _trigger_description(t),
                }
            )

        render(
            rows,
            ["index", "type", "active", "description"],
            output_format=output,
            title=f"Triggers: {scenario_id}",
        )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("add-trigger")
def add_trigger(
    ctx: typer.Context,
    scenario_id: str = typer.Argument(help="Scenario ID"),
    trigger: str = typer.Option(
        ...,
        "--trigger",
        "-t",
        help="Trigger JSON (string, @file.json, or '-' for stdin)",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Add a trigger to a scenario from JSON.

    For dataset change triggers, prefer: dku scenario add-trigger-dataset

    Examples:
        Daily at 2 AM: dku scenario add-trigger SCEN --trigger '{"active":true,"type":"temporal","params":{"frequency":"Daily","hour":2,"minute":0,"repeatFrequency":1,"timezone":"SERVER"}}' -P PROJ
        Dataset change: dku scenario add-trigger-dataset SCEN --dataset my_dataset -P PROJ
    """
    trigger_dict = read_json_input(trigger)
    if not trigger_dict:
        exit_with_error(
            "Trigger JSON cannot be empty.",
            code="invalid_input",
        )
    if "type" not in trigger_dict:
        exit_with_error(
            "Trigger JSON must have a 'type' field.",
            code="invalid_input",
            details=[
                "Valid types: temporal, ds_modified, sql_query, custom_python",
                "Example: dku scenario add-trigger SCEN --trigger "
                '\'{"active":true,"type":"temporal","params":{"frequency":"Daily","hour":2,"minute":0}}\' -P PROJ',
            ],
        )
    if "active" not in trigger_dict:
        trigger_dict["active"] = True
    _add_trigger(ctx, scenario_id, project, trigger_dict)


@app.command("add-trigger-dataset")
def add_trigger_dataset(
    ctx: typer.Context,
    scenario_id: str = typer.Argument(help="Scenario ID"),
    dataset: str = typer.Option(
        ...,
        "--dataset",
        "-d",
        help="Dataset name to watch for changes",
    ),
    delay: int = typer.Option(
        900,
        "--delay",
        help="Check interval in seconds (default: 900 = 15 min)",
    ),
    grace_delay: int = typer.Option(
        120,
        "--grace-delay",
        help="Seconds to wait after change before firing (default: 120)",
    ),
    check_again: bool = typer.Option(
        True,
        "--check-again/--no-check-again",
        help="Re-check after grace delay (default: True)",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Add a dataset change trigger (fires when dataset data is modified).

    Examples:
        dku scenario add-trigger-dataset SCEN --dataset my_dataset -P PROJ
        dku scenario add-trigger-dataset SCEN --dataset my_dataset --delay 600 --grace-delay 60 -P PROJ
    """
    trigger_dict = {
        "active": True,
        "type": "ds_modified",
        "delay": delay,
        "graceDelaySettings": {
            "delay": grace_delay,
            "checkAgainAfterGraceDelay": check_again,
        },
        "params": {
            "watches": [{"type": "DATASET", "itemId": dataset}],
        },
    }
    _add_trigger(ctx, scenario_id, project, trigger_dict)


@app.command("remove-trigger")
def remove_trigger(
    ctx: typer.Context,
    scenario_id: str = typer.Argument(help="Scenario ID"),
    index: int = typer.Option(
        ...,
        "--index",
        help="Trigger index to remove (0-based, from list-triggers)",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Remove a trigger from a scenario by index."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        scenario = proj.get_scenario(scenario_id)
        settings = scenario.get_settings()
        triggers = settings.raw_triggers

        if index < 0 or index >= len(triggers):
            exit_with_error(
                f"Index {index} out of range (0–{len(triggers) - 1}).",
                code="invalid_index",
                details=[
                    f"Use: dku scenario list-triggers {scenario_id} -P {project_key}",
                ],
            )

        removed = triggers.pop(index)
        settings.save()
        success(
            f"Removed {removed.get('type', 'unknown')} trigger "
            f"at index {index} from scenario '{scenario_id}'"
        )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)
