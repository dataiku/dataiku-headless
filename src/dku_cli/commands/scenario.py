"""dku scenario — list, run, abort, status, runs, last-run, avg-duration, run-log, set-metadata, create, delete, get/set-definition, get/set-code, triggers."""

from __future__ import annotations

import time

import typer

from dku_cli.errors import exit_with_error, handle_api_error, is_already_exists_error
from dku_cli.helpers import (
    get_client_from_ctx,
    read_json_input,
    read_text_input,
    resolve_project,
)
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
    """Poll scenario last runs until completion or timeout.

    DSSScenarioRun.running and DSSScenarioRun.outcome are both @property
    accessors (not methods). `outcome` RAISES ValueError until the run's
    `result` dict is populated, so the readiness check must be `running`
    first — which returns `not "result" in self.run` without raising.
    """
    elapsed = 0.0
    time.sleep(1)  # Brief wait for new run to register before first poll
    elapsed += 1.0
    while elapsed < timeout:
        runs = scenario.get_last_runs(limit=1)
        if runs:
            run = runs[0]
            try:
                if isinstance(run, dict):
                    outcome = run.get("result", {}).get("outcome")
                    if outcome:
                        return outcome
                else:
                    # Property — bool in real dataikuapi, callable in test mocks.
                    running = run.running
                    if callable(running):
                        running = running()
                    if not running:
                        return run.outcome
            except (ValueError, AttributeError):
                pass  # still running or unexpected shape — keep polling
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
        scenario.run()

        success(f"Scenario '{scenario_id}' triggered")

        if wait:
            info("Waiting for completion...")
            # Resolve the scenario run from the trigger fire, then poll the run
            # itself until it exits the running state. DSSScenarioRun.outcome is
            # a property that raises until the result dict is populated, so we
            # gate access on run.running() inside _poll_scenario_outcome.
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
            # Same ValueError trap as `runs` and `last-run`.
            try:
                outcome_val = r.outcome or ""
            except (ValueError, AttributeError):
                outcome_val = "RUNNING"
            data.append(
                {
                    "run_id": r.id,
                    "start": str(r.start_time) if r.start_time else "",
                    "outcome": outcome_val,
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
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip safety guard"),
) -> None:
    """Delete a scenario."""
    from dku_cli.safety import Tier, guard

    project_key = resolve_project(project)
    guard(
        ctx,
        tier=Tier.DELETE,
        action="scenario.delete",
        subject=f"scenario '{scenario_id}' in {project_key}",
        yes=yes,
        prompt=f"Delete scenario '{scenario_id}' from project {project_key}?",
    )
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        scenario = proj.get_scenario(scenario_id)
        scenario.delete()
        success(f"Deleted scenario '{scenario_id}'")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("get-definition")
def get_definition(
    ctx: typer.Context,
    scenario_id: str = typer.Argument(help="Scenario ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Get the raw definition of a scenario as JSON.

    Uses the full settings endpoint (DSSScenarioSettings.get_raw) so
    params.steps, triggers, and reporters are all returned. The legacy
    DSSScenario.get_definition endpoint hits /scenarios/X/light which
    omits params.steps — this command deliberately does NOT use it.
    """
    project_key = resolve_project(project)
    output = resolve_output_format(output, allowed=("json",), default="json")
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        scenario = proj.get_scenario(scenario_id)
        defn = scenario.get_settings().get_raw()
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
        help="JSON definition (string, @file.json, or - for stdin). Supports full settings including params.steps for step-based scenarios.",
    ),
) -> None:
    """Update a scenario's definition from JSON.

    Uses the full settings endpoint (DSSScenarioSettings.save) so params.steps,
    triggers, and reporters all persist. The legacy DSSScenario.set_definition
    endpoint hits /scenarios/X/light which is header-only (active / description /
    shortDesc / tags / checklists) and silently drops steps — this command
    deliberately does NOT use it.

    Top-level keys in the input JSON are merged into the existing settings so
    server-managed fields (lastModifiedOn, etc.) are preserved.
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        scenario = proj.get_scenario(scenario_id)
        new_def = read_json_input(definition)

        # Capture expected_steps count BEFORE mutating — since we merge by
        # reference, save-time side effects on raw["params"]["steps"] would
        # otherwise also alias through new_def and mask mismatches.
        expected_steps = new_def.get("params", {}).get("steps")
        expected_step_count = (
            len(expected_steps) if expected_steps is not None else None
        )

        settings = scenario.get_settings()
        raw = settings.get_raw()
        for k, v in new_def.items():
            raw[k] = v
        settings.save()

        if expected_step_count is not None:
            saved_steps = (
                scenario.get_settings().get_raw().get("params", {}).get("steps", [])
            )
            if len(saved_steps) != expected_step_count:
                exit_with_error(
                    f"Save incomplete: sent {expected_step_count} step(s), "
                    f"server persisted {len(saved_steps)}",
                    details=[
                        "Verify the step schema against dataikuapi DSSScenarioSettings.raw_steps.",
                        f"Inspect the saved scenario: dku scenario get-definition {scenario_id} -P {project_key}",
                    ],
                )
        success(f"Updated definition for scenario '{scenario_id}'")
    except Exception as e:
        handle_api_error(e)


@app.command("get-code")
def get_code(
    ctx: typer.Context,
    scenario_id: str = typer.Argument(help="Scenario ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Get the script/code of a scenario."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        scenario = proj.get_scenario(scenario_id)
        payload = scenario.get_payload()
        print(payload)
    except Exception as e:
        handle_api_error(e)


@app.command("set-code")
def set_code(
    ctx: typer.Context,
    scenario_id: str = typer.Argument(help="Scenario ID"),
    code: str = typer.Option(
        ...,
        "--code",
        "-c",
        help="Scenario script (literal, @file.py, or - for stdin)",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Set the script/code of a scenario."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        scenario = proj.get_scenario(scenario_id)
        script = read_text_input(code)
        scenario.set_payload(script)
        success(f"Updated code for scenario '{scenario_id}'")
    except Exception as e:
        handle_api_error(e)


# ---------------------------------------------------------------------------
# Run history commands
# ---------------------------------------------------------------------------


@app.command("last-run")
def last_run(
    ctx: typer.Context,
    scenario_id: str = typer.Argument(help="Scenario ID"),
    successful: bool = typer.Option(
        False,
        "--successful",
        help="Show only the last *successful* run (SUCCESS or WARNING)",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show the last finished run of a scenario.

    Use --successful to get the last run that completed with SUCCESS or
    WARNING status, skipping FAILED and ABORTED runs.

    Example:
      dku scenario last-run BUILD_ALL -P PROJ
      dku scenario last-run BUILD_ALL --successful -P PROJ
    """
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        scenario = proj.get_scenario(scenario_id)
        if successful:
            run = scenario.get_last_successful_run()
        else:
            run = scenario.get_last_finished_run()
        if hasattr(run, "get_info"):
            run_data = run.get_info()
        else:
            # Same ValueError trap as `runs` — fresh runs raise on .outcome.
            try:
                state = run.outcome
            except (ValueError, AttributeError):
                state = "RUNNING"
            run_data = {"id": run.id, "state": state}
        render_raw(run_data, output_format=output)
    except ValueError:
        msg = "No successful runs found." if successful else "No finished runs found."
        exit_with_error(
            msg,
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
    from_date: str | None = typer.Option(
        None, "--from", help="Start date (YYYY-MM-DD), inclusive"
    ),
    to_date: str | None = typer.Option(
        None, "--to", help="End date (YYYY-MM-DD), exclusive"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List recent runs of a scenario.

    Use --from/--to to filter by date range instead of --limit.

    Example:
      dku scenario runs BUILD_ALL -P PROJ
      dku scenario runs BUILD_ALL --from 2026-04-01 --to 2026-04-08 -P PROJ
    """
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        scenario = proj.get_scenario(scenario_id)

        if from_date:
            run_list = scenario.get_runs_by_date(from_date, to_date or from_date)
        else:
            run_list = scenario.get_last_runs(limit=limit)

        data = []
        for r in run_list:
            start = ""
            if hasattr(r, "get_start_time"):
                try:
                    start = str(r.get_start_time())
                except Exception:
                    pass
            duration = ""
            try:
                dur_secs = r.get_duration()
                if dur_secs is not None:
                    duration = f"{dur_secs:.1f}s"
            except Exception:
                pass
            # DSSScenarioRun.outcome is a property that RAISES ValueError on
            # fresh runs ("outcome not available for this scenario run. Maybe
            # still running?"). getattr's default only catches AttributeError,
            # so we must guard explicitly — otherwise the whole command crashes
            # (and -o json emits a partial/invalid stream).
            try:
                state = r.outcome or "RUNNING"
            except (ValueError, AttributeError):
                state = "RUNNING"
            data.append(
                {
                    "id": r.id,
                    "state": state,
                    "start": start,
                    "duration": duration,
                }
            )
        render(
            data,
            ["id", "state", "start", "duration"],
            output_format=output,
            title=f"Runs ({scenario_id})",
        )
    except Exception as e:
        handle_api_error(e)


@app.command("avg-duration")
def avg_duration(
    ctx: typer.Context,
    scenario_id: str = typer.Argument(help="Scenario ID"),
    limit: int = typer.Option(
        3, "--limit", help="Number of recent successful runs to average"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show average duration of recent successful scenario runs.

    Computes the average over the last N successful runs (SUCCESS or
    WARNING). Returns None if fewer than N successful runs exist.

    Example:
      dku scenario avg-duration BUILD_ALL -P PROJ
      dku scenario avg-duration BUILD_ALL --limit 5 -P PROJ -o json
    """
    project_key = resolve_project(project)
    fmt = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        scenario = proj.get_scenario(scenario_id)
        avg = scenario.get_average_duration(limit=limit)

        if fmt == "json":
            render_raw(
                {
                    "scenario": scenario_id,
                    "project": project_key,
                    "avg_duration_seconds": avg,
                    "limit": limit,
                },
                output_format="json",
            )
        else:
            if avg is not None:
                minutes = avg / 60
                if minutes >= 1:
                    info(
                        f"Average duration: {minutes:.1f} min ({avg:.0f}s) over last {limit} successful runs"
                    )
                else:
                    info(
                        f"Average duration: {avg:.1f}s over last {limit} successful runs"
                    )
            else:
                info(
                    f"Not enough successful runs to compute average (need {limit}). "
                    f"Run: dku scenario run {scenario_id} -P {project_key}"
                )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


def _scenario_grep_lines(text: str, pattern: str) -> str:
    """Return only lines matching *pattern* (case-insensitive substring match)."""
    if not pattern:
        return text
    lines = text.splitlines()
    lower = pattern.lower()
    matched = [line for line in lines if lower in line.lower()]
    return "\n".join(matched)


def _scenario_tail_lines(text: str, count: int) -> str:
    """Return the last *count* lines from *text*."""
    if count <= 0:
        return ""
    lines = text.splitlines()
    return "\n".join(lines[-count:])


@app.command("run-log")
def run_log(
    ctx: typer.Context,
    scenario_id: str = typer.Argument(help="Scenario ID"),
    run_id: str = typer.Option(..., "--run", help="Run ID"),
    step_id: str | None = typer.Option(
        None, "--step", help="Step ID to scope logs to (optional)"
    ),
    grep: str | None = typer.Option(
        None, "--grep", help="Show only lines containing this text (case-insensitive)"
    ),
    tail: int | None = typer.Option(
        None, "--tail", help="Show only the last N log lines"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Get logs from a specific scenario run.

    Use --step to get logs for a single step instead of the full run.
    Use --grep to filter lines containing specific text.
    Use --tail to show only the last N lines.

    Find run IDs with 'dku scenario runs' and step IDs from run details.

    Example:
      dku scenario run-log BUILD_ALL --run sc_2026-04-08T10 -P PROJ
      dku scenario run-log BUILD_ALL --run sc_2026-04-08T10 --step step1 -P PROJ
      dku scenario run-log BUILD_ALL --run sc_2026-04-08T10 --grep error -P PROJ
      dku scenario run-log BUILD_ALL --run sc_2026-04-08T10 --tail 50 -P PROJ
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        scenario = proj.get_scenario(scenario_id)
        run = scenario.get_run(run_id)
        log_text = run.get_log(step_id=step_id)
        if grep:
            log_text = _scenario_grep_lines(log_text, grep)
            if not log_text:
                from dku_cli.output import warn as scenario_warn

                scenario_warn(f"No lines matching '{grep}' found in the log.")
                return
        if tail is not None:
            log_text = _scenario_tail_lines(log_text, tail)
        print(log_text)
    except typer.Exit:
        raise
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
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip safety guard"),
) -> None:
    """Remove a trigger from a scenario by index."""
    from dku_cli.safety import Tier, guard

    project_key = resolve_project(project)
    guard(
        ctx,
        tier=Tier.DELETE,
        action="scenario.remove_trigger",
        subject=f"trigger index {index} from scenario '{scenario_id}' in {project_key}",
        yes=yes,
        prompt=f"Remove trigger at index {index} from scenario '{scenario_id}'?",
    )
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


# ---------------------------------------------------------------------------
# Reporter (email) commands
# ---------------------------------------------------------------------------

# runCondition expressions keyed by the --condition shorthand.
# "always" disables the condition so the reporter fires on every outcome.
_REPORTER_CONDITIONS = {
    "failure": ("outcome != 'SUCCESS'", True),
    "success": ("outcome == 'SUCCESS'", True),
    "always": ("", False),
}


@app.command("list-reporters")
def list_reporters(
    ctx: typer.Context,
    scenario_id: str = typer.Argument(help="Scenario ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List reporters on a scenario."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        scenario = proj.get_scenario(scenario_id)
        reporters = scenario.get_settings().raw_reporters

        if output == "json":
            render_raw(reporters, output_format="json")
            return

        if not reporters:
            info(
                f"No reporters on scenario '{scenario_id}'. "
                f"Add one: dku scenario add-reporter {scenario_id} "
                f"--recipient you@example.com --condition failure -P {project_key}"
            )
            return

        rows = []
        for i, r in enumerate(reporters):
            cfg = r.get("messaging", {}).get("configuration", {})
            rows.append(
                {
                    "index": str(i),
                    "type": r.get("messaging", {}).get("type", ""),
                    "recipient": cfg.get("recipient", ""),
                    "condition": r.get("runCondition", "") or "(always)",
                }
            )
        render(
            rows,
            ["index", "type", "recipient", "condition"],
            output_format=output,
            title=f"Reporters: {scenario_id}",
        )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("add-reporter")
def add_reporter(
    ctx: typer.Context,
    scenario_id: str = typer.Argument(help="Scenario ID"),
    recipient: str = typer.Option(..., "--recipient", help="Email recipient address"),
    condition: str = typer.Option(
        "always",
        "--condition",
        help="When to send: failure (outcome != SUCCESS), success, or always",
    ),
    channel: str = typer.Option(
        "mail",
        "--channel",
        help="DSS SMTP channel id. Must exist in Administration to actually "
        "send; the reporter is saved regardless (validated at send time).",
    ),
    sender: str = typer.Option(None, "--sender", help="Sender email address"),
    subject: str = typer.Option(
        "DSS scenario ${scenarioName}: ${outcome}",
        "--subject",
        help="Email subject (supports ${scenarioName}, ${outcome}, ${projectKey})",
    ),
    name: str = typer.Option(None, "--name", help="Reporter display name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Add an email reporter to a scenario.

    Wires a `mail-scenario` reporter that fires at the end of a run. Use
    --condition to branch on outcome.

    Examples:
        Alert on failure:   dku scenario add-reporter nightly --recipient ops@example.com --condition failure -P PROJ
        Notice on success:  dku scenario add-reporter nightly --recipient team@example.com --condition success -P PROJ
    """
    if condition not in _REPORTER_CONDITIONS:
        exit_with_error(
            f"Unknown condition '{condition}'.",
            code="invalid_input",
            details=["Valid conditions: failure, success, always"],
        )
    run_condition, cond_enabled = _REPORTER_CONDITIONS[condition]
    reporter = {
        "name": name or f"email on {condition}",
        "active": True,
        "phase": "END",
        "runConditionEnabled": cond_enabled,
        "runCondition": run_condition,
        "messaging": {
            "type": "mail-scenario",
            "configuration": {
                "channelId": channel,
                "subject": subject,
                "sender": sender or "",
                "recipient": recipient,
                "sendAsHTML": False,
                "messageSource": "TEMPLATE_FILE",
                "templateFormat": "FREEMARKER",
                "templateName": "default.ftl",
            },
        },
    }
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        scenario = proj.get_scenario(scenario_id)
        settings = scenario.get_settings()
        settings.raw_reporters.append(reporter)
        idx = len(settings.raw_reporters) - 1
        settings.save()
        success(
            f"Added '{condition}' email reporter to '{recipient}' on scenario "
            f"'{scenario_id}' at index {idx}"
        )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)
