"""dku scenario — list, run, abort, status, create, delete, get/set-definition."""

from __future__ import annotations

import typer

from dku_cli.errors import handle_api_error, is_already_exists_error
from dku_cli.helpers import get_client_from_ctx, read_json_input, resolve_project
from dku_cli.output import error, info, render, render_raw, resolve_output_format, success, warn

app = typer.Typer(help="Manage DSS scenarios.")


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
            data.append({
                "id": s.get("id", ""),
                "name": s.get("name", ""),
                "active": str(s.get("active", False)),
                "type": s.get("type", ""),
            })

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
            result = trigger.wait_for_result()
            outcome = result.get("scenarioRun", {}).get("result", {}).get("outcome", "unknown")
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
            data.append({
                "run_id": r.id,
                "start": str(r.start_time) if r.start_time else "",
                "outcome": r.outcome or "",
                "trigger": trigger.get("type", ""),
            })

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
        None, "--definition", "-d", help="JSON definition (string, @file.json, or - for stdin)"
    ),
    if_not_exists: bool = typer.Option(False, "--if-not-exists", help="Skip if scenario already exists"),
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
        defn = scenario.get_definition().get_raw()
        render_raw(defn, output_format=output)
    except Exception as e:
        handle_api_error(e)


@app.command("set-definition")
def set_definition(
    ctx: typer.Context,
    scenario_id: str = typer.Argument(help="Scenario ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    definition: str = typer.Option(
        ..., "--definition", "-d", help="JSON definition (string, @file.json, or - for stdin)"
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
