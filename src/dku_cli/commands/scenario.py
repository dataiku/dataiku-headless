"""dku scenario — list, run, abort, status, runs, last-run, avg-duration, run-log, set-metadata, create, delete, get/set-definition, get/set-code, triggers."""

from __future__ import annotations

import contextlib

import typer

from dku_cli.commands.scenario_payloads import (
    KNOWN_STEP_TYPES,
    build_python_trigger,
    build_step,
    build_targets,
    build_temporal_trigger,
    dataset_items,
    env_selection,
    mixed_typed_items,
    validate_build_job_type,
    validate_handle_warnings_as,
    validate_run_options,
)
from dku_cli.enums import EnvMode
from dku_cli.errors import exit_with_error, handle_api_error, is_already_exists_error
from dku_cli.helpers import (
    get_client_from_ctx,
    mutate_settings,
    object_write_lock,
    read_json_input,
    read_text_input,
    resolve_project,
)
from dku_cli.output import (
    error,
    info,
    print_text,
    render,
    render_raw,
    resolve_output_format,
    success,
    warn,
)

app = typer.Typer(help="Manage DSS scenarios.")


def _wait_for_run_outcome(trigger_fire) -> str:
    """Resolve and wait on the scenario run THIS trigger fire launched.

    Waiting on the trigger fire — not scenario.get_last_runs() — guarantees we
    report the outcome of the run this invocation started. get_last_runs(limit=1)
    can return a previously-finished run, which made `run --wait` report a stale
    outcome (e.g. a SUCCESS for a run that never started).

    DSSScenarioRun.outcome is a @property that RAISES ValueError until the run's
    result dict is populated; wait_for_completion ensures it is, but stay
    defensive for test mocks.
    """
    scenario_run = trigger_fire.wait_for_scenario_run(no_fail=True)
    if scenario_run is None:
        # The trigger fire was cancelled (scenario already running, or a later
        # trigger superseded it) — this call started no run.
        return "CANCELLED"
    scenario_run.wait_for_completion(no_fail=True)
    try:
        outcome = scenario_run.outcome
        # Property — str in real dataikuapi, callable in some test mocks.
        outcome = outcome() if callable(outcome) else outcome
        return outcome or "UNKNOWN"
    except (ValueError, AttributeError):
        return "UNKNOWN"


@app.command("list")
def list_scenarios(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """List scenarios in a project."""
    project_key = resolve_project(project)
    output = resolve_output_format()
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
                    "active": bool(s.get("active", False)),
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
        trigger_fire = scenario.run()

        success(f"Scenario '{scenario_id}' triggered")

        if wait:
            info("Waiting for completion...")
            # Wait on the run THIS trigger fire started — never get_last_runs(),
            # which can return a previously-finished run and report a stale
            # outcome for a run this call never started.
            outcome = _wait_for_run_outcome(trigger_fire)

            if outcome == "SUCCESS":
                success(f"Scenario completed: {outcome}")
            elif outcome == "WARNING":
                # WARNING = finished, but a step emitted a warning. Distinguish
                # it from a hard failure yet keep exit 0 so chained `&&` steps
                # proceed — matches DSS's own treatment of WARNING as a
                # successful terminal outcome.
                warn(f"Scenario completed with warnings: {outcome}")
            else:
                # FAILED / ABORTED / TIMEOUT must exit non-zero — agents chain
                # `scenario run --wait && next-step`; exit 0 here would let the
                # chain march on past a failed scenario.
                error(f"Scenario completed: {outcome}")
                info(f"Inspect why: dku scenario runs {scenario_id} -P {project_key}")
                raise typer.Exit(1)
    except typer.Exit:
        raise
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
) -> None:
    """Show last run status of a scenario."""
    project_key = resolve_project(project)
    output = resolve_output_format()
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
        from dku_cli.output import hint

        hint(f"dku scenario run {scenario.id} -P {project_key}")
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
) -> None:
    """Get the raw definition of a scenario as JSON.

    Uses the full settings endpoint (DSSScenarioSettings.get_raw) so
    params.steps, triggers, and reporters are all returned. The legacy
    DSSScenario.get_definition endpoint hits /scenarios/X/light which
    omits params.steps — this command deliberately does NOT use it.
    """
    project_key = resolve_project(project)
    output = resolve_output_format()
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

        def merge(settings):
            raw = settings.get_raw()
            for k, v in new_def.items():
                raw[k] = v

        mutate_settings(
            client,
            project_key,
            "scenario",
            scenario_id,
            fetch=scenario.get_settings,
            mutate=merge,
        )

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


@app.command("set-active")
def set_active(
    ctx: typer.Context,
    scenario_id: str = typer.Argument(help="Scenario ID"),
    enable: bool = typer.Option(
        True,
        "--active/--inactive",
        help="Activate (default) or deactivate the scenario.",
    ),
    skip_triggers: bool = typer.Option(
        False,
        "--skip-triggers",
        help="Only flip the scenario-level active flag; leave triggers untouched.",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Enable or disable a scenario AND every trigger in one call.

    DSS gates scenario auto-runs at two levels: scenario.active (top-level)
    AND each triggers[].active. Both must be true for the scenario to fire
    on its own. Many Solutions ship with one or both at false, so flipping
    just the top-level flag still leaves auto-runs blocked.

    This verb flips both. Pass --skip-triggers to flip only the top-level
    flag (rare; use when you want a manual-only scenario whose triggers
    should stay disabled).

    Examples:
      dku scenario set-active daily -P PROJ
      dku scenario set-active daily --inactive -P PROJ
      dku scenario set-active daily --skip-triggers -P PROJ
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        scenario = proj.get_scenario(scenario_id)

        def flip(settings):
            raw = settings.get_raw()
            before_scen = bool(raw.get("active", False))
            triggers = raw.get("triggers") or []
            before_trig_active = sum(1 for t in triggers if t.get("active"))
            raw["active"] = enable
            if not skip_triggers:
                for trigger in triggers:
                    trigger["active"] = enable
            return before_scen, before_trig_active, len(triggers)

        before_scen, before_trig_active, n_triggers = mutate_settings(
            client,
            project_key,
            "scenario",
            scenario_id,
            fetch=scenario.get_settings,
            mutate=flip,
        )

        verb = "enabled" if enable else "disabled"
        if skip_triggers:
            success(
                f"{verb.capitalize()} scenario '{scenario_id}' "
                f"(triggers untouched: {before_trig_active}/{n_triggers} active)"
            )
        else:
            after = n_triggers if enable else 0
            success(
                f"{verb.capitalize()} scenario '{scenario_id}' "
                f"(scenario.active: {before_scen} → {enable}; "
                f"triggers active: {before_trig_active}/{n_triggers} → "
                f"{after}/{n_triggers})"
            )
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
        print_text(payload)
    except Exception as e:
        handle_api_error(e)


def _find_step(steps: list, selector: str, scenario_id: str, project_key: str):
    """Resolve a --step selector (0-based index or step name) to (index, step)."""
    if selector.lstrip("-").isdigit():
        idx = int(selector)
        if idx < 0 or idx >= len(steps):
            exit_with_error(
                f"Step index {idx} out of range (0–{len(steps) - 1}).",
                details=[
                    f"Use: dku scenario list-steps {scenario_id} -P {project_key}",
                ],
            )
        return idx, steps[idx]
    matches = [(i, s) for i, s in enumerate(steps) if s.get("name") == selector]
    if not matches:
        names = ", ".join(repr(s.get("name", "")) for s in steps) or "(none)"
        exit_with_error(
            f"No step named '{selector}'. Steps: {names}.",
            details=[
                f"Use: dku scenario list-steps {scenario_id} -P {project_key}",
            ],
        )
    if len(matches) > 1:
        exit_with_error(
            f"Step name '{selector}' matches {len(matches)} steps — "
            "use the 0-based index instead.",
            details=[
                f"Use: dku scenario list-steps {scenario_id} -P {project_key}",
            ],
        )
    return matches[0]


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
    step: str = typer.Option(
        None,
        "--step",
        help=(
            "For step-based scenarios: target step (0-based index or step name). "
            "Only valid for custom_python steps; writes the step's params.script."
        ),
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Set the script/code of a scenario, or of one custom_python step.

    Bare (no --step) only applies to custom_python (script-based) scenarios.
    On a step-based scenario, target the step: --step <index-or-name>.
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        scenario = proj.get_scenario(scenario_id)
        script = read_text_input(code)
        settings = scenario.get_settings()
        step_based = hasattr(settings, "raw_steps")

        if step is not None:
            if not step_based:
                exit_with_error(
                    f"Scenario '{scenario_id}' is script-based (custom_python) — "
                    "it has no steps.",
                    details=[
                        f"Drop --step: dku scenario set-code {scenario_id} "
                        f"--code @file.py -P {project_key}",
                    ],
                )
            steps = settings.raw_steps
            idx, target = _find_step(steps, step, scenario_id, project_key)
            if target.get("type") != "custom_python":
                exit_with_error(
                    f"Step {idx} ('{target.get('name', '')}') is type "
                    f"'{target.get('type', '')}' — only custom_python steps "
                    "hold a script.",
                    details=[
                        f"List steps: dku scenario list-steps {scenario_id} "
                        f"-P {project_key}",
                        f"Or add one: dku scenario add-step-python {scenario_id} "
                        f"--name NAME --code @file.py -P {project_key}",
                    ],
                )
            target.setdefault("params", {})["script"] = script
            settings.save()
            success(
                f"Updated script of custom_python step {idx} "
                f"('{target.get('name', '')}') in scenario '{scenario_id}'"
            )
            return

        if step_based:
            exit_with_error(
                f"Scenario '{scenario_id}' is step-based — a scenario-level "
                "script would be saved but never executed.",
                details=[
                    "Target a custom_python step instead: dku scenario set-code "
                    f"{scenario_id} --step <index-or-name> --code @file.py "
                    f"-P {project_key}",
                    f"List steps: dku scenario list-steps {scenario_id} "
                    f"-P {project_key}",
                ],
            )

        scenario.set_payload(script)
        success(f"Updated code for scenario '{scenario_id}'")
    except typer.Exit:
        raise
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
) -> None:
    """Show the last finished run of a scenario.

    Use --successful to get the last run that completed with SUCCESS or
    WARNING status, skipping FAILED and ABORTED runs.

    Example:
      dku scenario last-run BUILD_ALL -P PROJ
      dku scenario last-run BUILD_ALL --successful -P PROJ
    """
    project_key = resolve_project(project)
    output = resolve_output_format()
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
) -> None:
    """List recent runs of a scenario.

    Use --from/--to to filter by date range instead of --limit.

    Example:
      dku scenario runs BUILD_ALL -P PROJ
      dku scenario runs BUILD_ALL --from 2026-04-01 --to 2026-04-08 -P PROJ
    """
    project_key = resolve_project(project)
    output = resolve_output_format()
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
                with contextlib.suppress(Exception):
                    start = str(r.get_start_time())
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
            # (and --format json emits a partial/invalid stream).
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
) -> None:
    """Show average duration of recent successful scenario runs.

    Computes the average over the last N successful runs (SUCCESS or
    WARNING). Returns None if fewer than N successful runs exist.

    Example:
      dku scenario avg-duration BUILD_ALL -P PROJ
      dku scenario avg-duration BUILD_ALL --limit 5 -P PROJ
    """
    project_key = resolve_project(project)
    fmt = resolve_output_format()
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
        print_text(log_text)
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
        with object_write_lock(client, project_key, "scenario", scenario_id):
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

        def append(settings):
            settings.raw_triggers.append(trigger_dict)
            return len(settings.raw_triggers) - 1

        idx = mutate_settings(
            client,
            project_key,
            "scenario",
            scenario_id,
            fetch=scenario.get_settings,
            mutate=append,
        )
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
) -> None:
    """List triggers on a scenario."""
    project_key = resolve_project(project)
    output = resolve_output_format()
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
                    "active": bool(t.get("active", False)),
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
        )
    if "type" not in trigger_dict:
        exit_with_error(
            "Trigger JSON must have a 'type' field.",
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


@app.command("add-trigger-time")
def add_trigger_time(
    ctx: typer.Context,
    scenario_id: str = typer.Argument(help="Scenario ID"),
    frequency: str = typer.Option(
        ...,
        "--frequency",
        "-f",
        help="Schedule frequency: Minutely, Hourly, Daily, Weekly, Monthly",
    ),
    hour: int = typer.Option(
        2, "--hour", help="Hour of day (0–23) for Daily/Weekly/Monthly (default: 2)"
    ),
    minute: int = typer.Option(
        0, "--minute", help="Minute of hour (0–59) (default: 0)"
    ),
    days: str | None = typer.Option(
        None,
        "--days",
        help="Comma-separated days of week for Weekly: Monday,Tuesday,...",
    ),
    monthly_run_on: str = typer.Option(
        "ON_THE_DAY",
        "--monthly-run-on",
        help="Monthly run mode: ON_THE_DAY, LAST_DAY_OF_THE_MONTH, FIRST_DAY_OF_THE_MONTH, FIRST_WEEK, LAST_WEEK",
    ),
    repeat_every: int = typer.Option(
        1,
        "--repeat-every",
        help="Repeat every N units (e.g. every 2 hours, every 3 days). Default: 1",
    ),
    timezone: str = typer.Option(
        "SERVER",
        "--timezone",
        help="Timezone (e.g. SERVER, UTC, Europe/Paris). Default: SERVER",
    ),
    active: bool = typer.Option(
        True,
        "--active/--inactive",
        help="Whether the trigger is active (default: active)",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Add a time-based (temporal) trigger to a scenario.

    Replaces hand-crafted JSON for daily/weekly/hourly schedules.

    Examples:
        Daily at 02:00:
            dku scenario add-trigger-time SCEN --frequency Daily --hour 2 -P PROJ
        Weekly Mon/Wed/Fri at 06:30:
            dku scenario add-trigger-time SCEN --frequency Weekly \\
              --days Monday,Wednesday,Friday --hour 6 --minute 30 -P PROJ
        Every 15 minutes:
            dku scenario add-trigger-time SCEN --frequency Minutely --repeat-every 15 -P PROJ
        Hourly at :00 (every 2 hours):
            dku scenario add-trigger-time SCEN --frequency Hourly --minute 0 --repeat-every 2 -P PROJ
        Monthly on the last day at 03:00:
            dku scenario add-trigger-time SCEN --frequency Monthly --monthly-run-on LAST_DAY_OF_THE_MONTH --hour 3 -P PROJ
    """
    _add_trigger(
        ctx,
        scenario_id,
        project,
        build_temporal_trigger(
            frequency=frequency,
            hour=hour,
            minute=minute,
            days=days,
            monthly_run_on=monthly_run_on,
            repeat_every=repeat_every,
            timezone=timezone,
            active=active,
        ),
    )


@app.command("add-trigger-python")
def add_trigger_python(
    ctx: typer.Context,
    scenario_id: str = typer.Argument(help="Scenario ID"),
    code: str = typer.Option(
        ...,
        "--code",
        help=(
            "Python trigger script: literal, @file.py, or '-' for stdin. The "
            "script must call Trigger().fire() from dataiku.scenario to fire "
            "the scenario; returning silently means 'don't fire'. Canonical "
            "shape:\n"
            "  from dataiku.scenario import Trigger\n"
            "  if some_state_check(): Trigger().fire()"
        ),
    ),
    name: str | None = typer.Option(
        None,
        "--name",
        help="Trigger display name in the UI (optional).",
    ),
    delay: int = typer.Option(
        86400,
        "--delay",
        help=(
            "Polling interval in seconds — how often DSS evaluates the script. "
            "Default 86400 (once per day)."
        ),
    ),
    grace_delay: int = typer.Option(
        0,
        "--grace-delay",
        help="Seconds to wait after the script fires before launching the run (default 0).",
    ),
    check_again: bool = typer.Option(
        False,
        "--check-again/--no-check-again",
        help="Re-check after grace delay before firing.",
    ),
    env_mode: EnvMode = typer.Option(
        EnvMode.INHERIT,
        "--env-mode",
        case_sensitive=False,
        help=(
            "Code env mode for the trigger: INHERIT | USE_BUILTIN_MODE | EXPLICIT_ENV."
        ),
    ),
    env_name: str | None = typer.Option(
        None,
        "--env-name",
        help="Code env name (required when --env-mode EXPLICIT_ENV).",
    ),
    inactive: bool = typer.Option(
        False,
        "--inactive",
        help="Create the trigger in disabled state. By default, triggers are active.",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Add a custom_python trigger (fire-on-state-condition).

    Use this for "fire when a project variable / external system state
    matches a condition" patterns — far more flexible than dataset_change or
    temporal triggers but undocumented in the SDK. The script is polled every
    --delay seconds; it fires the scenario when Trigger().fire() is called.

    Example (fires when var.activate_hourly_build is true, polled hourly):
        dku scenario add-trigger-python SCEN --code @trigger.py --delay 3600 -P PROJ
    """
    body = read_text_input(code)
    _add_trigger(
        ctx,
        scenario_id,
        project,
        build_python_trigger(
            code=body,
            env_mode=env_mode,
            env_name=env_name,
            delay=delay,
            grace_delay=grace_delay,
            check_again=check_again,
            active=not inactive,
            name=name,
        ),
    )


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

        def pop_trigger(settings):
            triggers = settings.raw_triggers
            if index < 0 or index >= len(triggers):
                exit_with_error(
                    f"Index {index} out of range (0–{len(triggers) - 1}).",
                    details=[
                        f"Use: dku scenario list-triggers {scenario_id} -P {project_key}",
                    ],
                )
            return triggers.pop(index)

        removed = mutate_settings(
            client,
            project_key,
            "scenario",
            scenario_id,
            fetch=scenario.get_settings,
            mutate=pop_trigger,
        )
        success(
            f"Removed {removed.get('type', 'unknown')} trigger "
            f"at index {index} from scenario '{scenario_id}'"
        )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


# ---------------------------------------------------------------------------
# Step commands (step-based scenarios only)
# ---------------------------------------------------------------------------


def _resolve_step_settings(scenario):
    """Return raw_steps list for a step-based scenario, or exit with a
    prescriptive error if the scenario is custom_python (whole-scenario
    Python script, no steps)."""
    settings = scenario.get_settings()
    if not hasattr(settings, "raw_steps"):
        exit_with_error(
            "This scenario is not step-based — it has no steps to manage.",
            details=[
                "Scenario type must be 'step_based'. For custom_python scenarios, "
                "use 'dku scenario set-code SCEN --code @file.py' to update the script.",
            ],
        )
    return settings


def _add_step(
    ctx: typer.Context,
    scenario_id: str,
    project: str | None,
    step: dict,
    at: int | None = None,
) -> None:
    """Shared logic for all add-step commands."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        scenario = proj.get_scenario(scenario_id)

        def insert_step(settings):
            steps = settings.raw_steps
            if at is None or at >= len(steps):
                steps.append(step)
                return len(steps) - 1
            steps.insert(max(at, 0), step)
            return max(at, 0)

        idx = mutate_settings(
            client,
            project_key,
            "scenario",
            scenario_id,
            fetch=lambda: _resolve_step_settings(scenario),
            mutate=insert_step,
        )
        _warn_dropped_step_params(scenario, idx, step)
        success(
            f"Added {step.get('type', 'unknown')} step "
            f"'{step.get('name', step.get('id', ''))}' to scenario '{scenario_id}' at index {idx}"
        )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


def _warn_dropped_step_params(scenario, idx: int, step: dict) -> None:
    """Re-read the saved step and warn about any param key DSS silently dropped.

    DSS accepts unrecognized step params, drops them on save (exit 0), and
    applies nothing — the breakage surfaces only at run time (#228, same class
    as #216). The classic case is ``buildMode`` (a non-key) instead of
    ``jobType`` on a build step. DSS *adds* its own default keys on save, so we
    only flag keys we SENT that did not survive, never the additions.
    """
    sent = step.get("params")
    if not isinstance(sent, dict) or not sent:
        return
    try:
        fresh_steps = _resolve_step_settings(scenario).raw_steps
        kept = fresh_steps[idx].get("params", {})
    except Exception:
        return
    if not isinstance(kept, dict):
        return
    dropped = [key for key in sent if key not in kept]
    if not dropped:
        return
    hint = ""
    if "buildMode" in dropped:
        hint = (
            " Build steps use 'jobType' (NON_RECURSIVE_FORCED_BUILD | "
            "RECURSIVE_BUILD | RECURSIVE_FORCED_BUILD), not 'buildMode'."
        )
    warn(
        f"DSS ignored unknown param key(s) on step "
        f"'{step.get('name', step.get('id', ''))}': {', '.join(dropped)} — "
        f"silently dropped, no effect." + hint
    )


@app.command("list-steps")
def list_steps(
    ctx: typer.Context,
    scenario_id: str = typer.Argument(help="Scenario ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """List steps in a step-based scenario.

    Examples:
        dku scenario list-steps daily_refresh -P PROJ
        dku --format json scenario list-steps daily_refresh -P PROJ
    """
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        scenario = proj.get_scenario(scenario_id)
        settings = _resolve_step_settings(scenario)
        steps = settings.raw_steps
        if output == "json":
            render_raw(steps, output_format="json")
            return
        rows = [
            {
                "index": str(i),
                "id": s.get("id", ""),
                "name": s.get("name", ""),
                "type": s.get("type", ""),
            }
            for i, s in enumerate(steps)
        ]
        render(
            rows,
            ["index", "id", "name", "type"],
            output_format=output,
            title=f"Steps ({scenario_id})",
        )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("remove-step")
def remove_step(
    ctx: typer.Context,
    scenario_id: str = typer.Argument(help="Scenario ID"),
    index: int = typer.Option(
        ...,
        "--index",
        help="Step index to remove (0-based, from list-steps)",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip safety guard"),
) -> None:
    """Remove a step from a step-based scenario by index."""
    from dku_cli.safety import Tier, guard

    project_key = resolve_project(project)
    guard(
        ctx,
        tier=Tier.DELETE,
        action="scenario.remove_step",
        subject=f"step index {index} from scenario '{scenario_id}' in {project_key}",
        yes=yes,
        prompt=f"Remove step at index {index} from scenario '{scenario_id}'?",
    )
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        scenario = proj.get_scenario(scenario_id)

        def pop_step(settings):
            steps = settings.raw_steps
            if index < 0 or index >= len(steps):
                exit_with_error(
                    f"Index {index} out of range (0–{len(steps) - 1}).",
                    details=[
                        f"Use: dku scenario list-steps {scenario_id} -P {project_key}",
                    ],
                )
            return steps.pop(index)

        removed = mutate_settings(
            client,
            project_key,
            "scenario",
            scenario_id,
            fetch=lambda: _resolve_step_settings(scenario),
            mutate=pop_step,
        )
        success(
            f"Removed {removed.get('type', 'unknown')} step "
            f"at index {index} from scenario '{scenario_id}'"
        )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("add-step")
def add_step(
    ctx: typer.Context,
    scenario_id: str = typer.Argument(help="Scenario ID"),
    type_: str = typer.Option(
        ...,
        "--type",
        help=(
            "Step type. Common: build_flowitem, custom_python, exec_sql, "
            "check_dataset, compute_metrics, reload_schema, run_scenario, "
            "restart_webapp, refresh_chart_cache. Prefer typed shortcuts "
            "(add-step-build, add-step-python, …) over this generic verb."
        ),
    ),
    name: str = typer.Option(..., "--name", help="Step name (label shown in UI)"),
    params: str | None = typer.Option(
        None,
        "--params",
        help="Step params as JSON literal, @file.json, or '-' for stdin",
    ),
    at: int | None = typer.Option(
        None, "--at", help="Insert at index (default: append)"
    ),
    proceed_on_failure: bool = typer.Option(
        False, "--proceed-on-failure", help="Continue scenario if this step fails"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Add a step to a step-based scenario (generic; supports any step type).

    Prefer the typed shortcuts when available — they construct the right
    `params` shape for you. Use this generic verb for step types not yet
    covered by a shortcut.

    Examples:
        dku scenario add-step daily --type build_flowitem --name "Build all" \\
            --params '{"builds":[{"type":"DATASET","itemId":"final"}],"jobType":"NON_RECURSIVE_FORCED_BUILD"}' -P PROJ
        dku scenario add-step daily --type set_project_variables --name "Set day" \\
            --params '{"variables":{"day":"$(date +%F)"}}' -P PROJ
    """
    if type_ not in KNOWN_STEP_TYPES:
        if type_.startswith("pystep_"):
            exit_with_error(
                f"Step type '{type_}' looks plugin-provided and is not a "
                "built-in step type — DSS will reject it with 'Unknown step "
                "type' unless the plugin is installed and its components "
                "reloaded.",
                details=[
                    "Check the plugin exposes it: dku plugin components <plugin-id> "
                    "(kind: scenario-step).",
                    "After installing/updating the plugin, reload it from the "
                    "plugin's page (Actions > Reload) so DSS registers the step type.",
                    "Meanwhile, an inline Python step works everywhere: "
                    f"dku scenario add-step-python {scenario_id} --name {name!r} "
                    f"--code @file.py -P <PROJ>",
                ],
            )
        warn(
            f"Step type '{type_}' is not in the known catalog "
            f"({', '.join(sorted(KNOWN_STEP_TYPES))[:120]}...) — proceeding anyway."
        )
    params_dict = read_json_input(params) if params else {}
    if not isinstance(params_dict, dict):
        exit_with_error(
            "--params must be a JSON object.",
        )
    if proceed_on_failure:
        params_dict["proceedOnFailure"] = True
    step = {"type": type_, "name": name, "params": params_dict}
    _add_step(ctx, scenario_id, project, step, at=at)


@app.command("add-step-build")
def add_step_build(
    ctx: typer.Context,
    scenario_id: str = typer.Argument(help="Scenario ID"),
    name: str = typer.Option(..., "--name", help="Step name"),
    build: list[str] = typer.Option(
        ...,
        "--build",
        help="Dataset/folder to build (repeatable; PROJECT.NAME for cross-project)",
    ),
    job_type: str = typer.Option(
        "NON_RECURSIVE_FORCED_BUILD",
        "--job-type",
        help="NON_RECURSIVE_FORCED_BUILD | RECURSIVE_BUILD | RECURSIVE_FORCED_BUILD | RECURSIVE_MISSING_ONLY_BUILD",
    ),
    proceed_on_failure: bool = typer.Option(False, "--proceed-on-failure"),
    handle_warnings_as: str | None = typer.Option(
        None,
        "--handle-warnings-as",
        help=(
            "Outcome to record when the build emits warnings: WARNING "
            "(server default), FAILED (treat warnings as failures), "
            "SUCCESS (ignore warnings), or ABORTED."
        ),
    ),
    refresh_metastore: bool = typer.Option(
        False,
        "--refresh-metastore",
        help=(
            "Refresh the Hive metastore after each built table. Only relevant "
            "for Hive/Impala/Spark-SQL outputs whose downstream consumers query "
            "via metastore."
        ),
    ),
    stop_at_zone_boundary: bool = typer.Option(
        False,
        "--stop-at-zone-boundary",
        help=(
            "When --job-type RECURSIVE, do NOT cross flow-zone boundaries when "
            "walking upstream — only rebuild items in the same zone(s) as the "
            "explicit --build targets."
        ),
    ),
    max_retries: int | None = typer.Option(
        None,
        "--max-retries",
        help=(
            "Re-run the step on failure up to N times before marking the "
            "scenario as FAILED. 0 disables retry. Maps to maxRetriesOnFail."
        ),
    ),
    delay_between_retries: int | None = typer.Option(
        None,
        "--delay-between-retries",
        help="Seconds to wait between retries. Requires --max-retries.",
    ),
    run_condition_type: str | None = typer.Option(
        None,
        "--run-condition-type",
        help=(
            "Gate the step on prior steps' status: RUN_ALWAYS, "
            "RUN_IF_STATUS_MATCH (use with --run-condition-statuses), or "
            "RUN_CONDITIONALLY (use with --run-condition-expression). "
            "Omitted = server default RUN_IF_STATUS_MATCH on SUCCESS,WARNING "
            "(the step is skipped after a prior failure)."
        ),
    ),
    run_condition_expression: str | None = typer.Option(
        None,
        "--run-condition-expression",
        help=(
            "GREL boolean expression evaluated before the step runs. "
            "Implies --run-condition-type RUN_CONDITIONALLY if not set."
        ),
    ),
    run_condition_statuses: list[str] = typer.Option(
        [],
        "--run-condition-statuses",
        help=(
            "Status whitelist when --run-condition-type RUN_IF_STATUS_MATCH "
            "(repeatable; comma/space accepted). DSS UI 'run if previous "
            "succeeded' default writes SUCCESS,WARNING — not just SUCCESS."
        ),
    ),
    reset_scenario_status: bool = typer.Option(
        False,
        "--reset-scenario-status",
        help="Reset accumulated status before this step runs.",
    ),
    at: int | None = typer.Option(None, "--at"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Add a build_flowitem step (the most common scenario step).

    Example:
        dku scenario add-step-build daily --name "Build core" \\
            --build sales_clean --build inventory_clean -P PROJ

    With retry + warnings-as-failure:
        dku scenario add-step-build daily --name "Build core" \\
            --build sales_clean --max-retries 3 --delay-between-retries 60 \\
            --handle-warnings-as FAILED -P PROJ
    """
    handle_warnings_as = validate_handle_warnings_as(handle_warnings_as)
    rct, rcs = validate_run_options(
        run_condition_type,
        run_condition_expression,
        run_condition_statuses,
        max_retries,
        delay_between_retries,
    )

    job_type = validate_build_job_type(job_type)

    params: dict = {"builds": build_targets(build), "jobType": job_type}
    if handle_warnings_as:
        params["handleWarningsAs"] = handle_warnings_as
    if refresh_metastore:
        params["refreshHiveMetastore"] = True
    if stop_at_zone_boundary:
        params["stopAtFlowZoneBoundary"] = True
    step = build_step(
        "build_flowitem",
        name,
        params,
        proceed_on_failure=proceed_on_failure,
        delay_between_retries=delay_between_retries,
        max_retries=max_retries,
        run_condition_type=rct,
        run_condition_expression=run_condition_expression,
        run_condition_statuses=rcs,
        reset_scenario_status=reset_scenario_status,
    )
    _add_step(ctx, scenario_id, project, step, at=at)


@app.command("add-step-python")
def add_step_python(
    ctx: typer.Context,
    scenario_id: str = typer.Argument(help="Scenario ID"),
    name: str = typer.Option(..., "--name", help="Step name"),
    code: str = typer.Option(
        ..., "--code", help="Python script: literal, @file.py, or '-' for stdin"
    ),
    env_mode: EnvMode = typer.Option(
        EnvMode.INHERIT,
        "--env-mode",
        case_sensitive=False,
        help="Code env mode: INHERIT | USE_BUILTIN_MODE | EXPLICIT_ENV",
    ),
    env_name: str | None = typer.Option(
        None, "--env-name", help="Code env name (required when --env-mode EXPLICIT_ENV)"
    ),
    proceed_on_failure: bool = typer.Option(False, "--proceed-on-failure"),
    max_retries: int | None = typer.Option(
        None,
        "--max-retries",
        help="Re-run the step on failure up to N times. 0 disables retry.",
    ),
    delay_between_retries: int | None = typer.Option(
        None,
        "--delay-between-retries",
        help="Seconds between retries. Requires --max-retries.",
    ),
    run_condition_type: str | None = typer.Option(
        None,
        "--run-condition-type",
        help=(
            "Gate the step on prior steps' status: RUN_ALWAYS, "
            "RUN_IF_STATUS_MATCH (use --run-condition-statuses), or "
            "RUN_CONDITIONALLY (use --run-condition-expression). Omitted = "
            "server default RUN_IF_STATUS_MATCH on SUCCESS,WARNING."
        ),
    ),
    run_condition_statuses: list[str] = typer.Option(
        [],
        "--run-condition-statuses",
        help=(
            "Status whitelist when --run-condition-type RUN_IF_STATUS_MATCH "
            "(repeatable; comma- or space-separated also accepted). DSS UI "
            "default 'run if previous succeeded' writes SUCCESS,WARNING — "
            "agents writing fixtures often wrongly assume just SUCCESS."
        ),
    ),
    run_condition_expression: str | None = typer.Option(
        None,
        "--run-condition-expression",
        help=(
            "GREL boolean. Implies --run-condition-type RUN_CONDITIONALLY if not set."
        ),
    ),
    reset_scenario_status: bool = typer.Option(
        False,
        "--reset-scenario-status",
        help="Reset accumulated status before this step runs.",
    ),
    at: int | None = typer.Option(None, "--at"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Add a custom_python step (inline Python script in a step-based scenario).

    Example:
        dku scenario add-step-python daily --name "Notify" --code @notify.py -P PROJ
    """
    rct, rcs = validate_run_options(
        run_condition_type,
        run_condition_expression,
        run_condition_statuses,
        max_retries,
        delay_between_retries,
    )
    script = read_text_input(code)
    params: dict = {
        "script": script,
        "envSelection": env_selection(env_mode, env_name),
    }
    step = build_step(
        "custom_python",
        name,
        params,
        proceed_on_failure=proceed_on_failure,
        max_retries=max_retries,
        delay_between_retries=delay_between_retries,
        run_condition_type=rct,
        run_condition_expression=run_condition_expression,
        run_condition_statuses=rcs,
        reset_scenario_status=reset_scenario_status,
    )
    _add_step(ctx, scenario_id, project, step, at=at)


@app.command("add-step-sql")
def add_step_sql(
    ctx: typer.Context,
    scenario_id: str = typer.Argument(help="Scenario ID"),
    name: str = typer.Option(..., "--name", help="Step name"),
    connection: str = typer.Option(..., "--connection", help="SQL connection name"),
    sql: str = typer.Option(
        ..., "--sql", help="SQL query: literal, @file.sql, or '-' for stdin"
    ),
    override_default_limit: bool = typer.Option(
        False,
        "--override-default-limit/--no-override-default-limit",
        help=(
            "Disable DSS's default 10k-row LIMIT cap on the query result. "
            "Required for SELECT-with-side-effects when the agent expects "
            "all rows. DDL (CREATE/DROP/ALTER) is unaffected."
        ),
    ),
    extra_conf: list[str] = typer.Option(
        [],
        "--extra-conf",
        help=(
            "Connection-level session knob KEY=VALUE (repeatable). E.g. "
            "--extra-conf STATEMENT_TIMEOUT_IN_SECONDS=300 for Snowflake. "
            "Maps to params.extraConf[]."
        ),
    ),
    proceed_on_failure: bool = typer.Option(False, "--proceed-on-failure"),
    max_retries: int | None = typer.Option(None, "--max-retries"),
    delay_between_retries: int | None = typer.Option(None, "--delay-between-retries"),
    run_condition_type: str | None = typer.Option(None, "--run-condition-type"),
    run_condition_statuses: list[str] = typer.Option([], "--run-condition-statuses"),
    run_condition_expression: str | None = typer.Option(
        None, "--run-condition-expression"
    ),
    reset_scenario_status: bool = typer.Option(False, "--reset-scenario-status"),
    at: int | None = typer.Option(None, "--at"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Add an exec_sql step (run a SQL query against a connection).

    Example:
        dku scenario add-step-sql daily --name "Cleanup" \\
            --connection prod_pg --sql 'DELETE FROM staging WHERE day < CURRENT_DATE - 30' -P PROJ
    """
    rct, rcs = validate_run_options(
        run_condition_type,
        run_condition_expression,
        run_condition_statuses,
        max_retries,
        delay_between_retries,
    )
    body = read_text_input(sql)
    params: dict = {"connection": connection, "sql": body}
    if override_default_limit:
        params["overrideDefaultLimit"] = True
    if extra_conf:
        parsed_conf = []
        for entry in extra_conf:
            if "=" not in entry:
                exit_with_error(
                    f"Invalid --extra-conf '{entry}'. Expected 'KEY=VALUE'.",
                )
            k, v = entry.split("=", 1)
            parsed_conf.append({"key": k.strip(), "value": v.strip()})
        params["extraConf"] = parsed_conf
    step = build_step(
        "exec_sql",
        name,
        params,
        proceed_on_failure=proceed_on_failure,
        max_retries=max_retries,
        delay_between_retries=delay_between_retries,
        run_condition_type=rct,
        run_condition_expression=run_condition_expression,
        run_condition_statuses=rcs,
        reset_scenario_status=reset_scenario_status,
    )
    _add_step(ctx, scenario_id, project, step, at=at)


@app.command("add-step-check-dataset")
def add_step_check_dataset(
    ctx: typer.Context,
    scenario_id: str = typer.Argument(help="Scenario ID"),
    name: str = typer.Option(..., "--name", help="Step name"),
    dataset: list[str] = typer.Option(
        ...,
        "--dataset",
        help="Dataset to check (repeatable; PROJECT.NAME cross-project)",
    ),
    handle_warnings_as: str = typer.Option(
        "WARNING",
        "--handle-warnings-as",
        help=(
            "Outcome to record when checks emit warnings: WARNING "
            "(server default), FAILED, SUCCESS, or ABORTED."
        ),
    ),
    compute_automatic_rules: bool = typer.Option(False, "--compute-automatic-rules"),
    proceed_on_failure: bool = typer.Option(False, "--proceed-on-failure"),
    max_retries: int | None = typer.Option(None, "--max-retries"),
    delay_between_retries: int | None = typer.Option(None, "--delay-between-retries"),
    run_condition_type: str | None = typer.Option(None, "--run-condition-type"),
    run_condition_statuses: list[str] = typer.Option([], "--run-condition-statuses"),
    run_condition_expression: str | None = typer.Option(
        None, "--run-condition-expression"
    ),
    reset_scenario_status: bool = typer.Option(False, "--reset-scenario-status"),
    at: int | None = typer.Option(None, "--at"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Add a check_dataset step (run dataset checks defined on the dataset).

    Example:
        dku scenario add-step-check-dataset daily --name "QC" \\
            --dataset sales_clean --dataset orders_clean -P PROJ
    """
    handle_warnings_as = validate_handle_warnings_as(handle_warnings_as)
    rct, rcs = validate_run_options(
        run_condition_type,
        run_condition_expression,
        run_condition_statuses,
        max_retries,
        delay_between_retries,
    )
    params = {
        "checks": dataset_items(dataset),
        "handleWarningsAs": handle_warnings_as,
        "computeAutomaticRules": compute_automatic_rules,
    }
    step = build_step(
        "check_dataset",
        name,
        params,
        proceed_on_failure=proceed_on_failure,
        max_retries=max_retries,
        delay_between_retries=delay_between_retries,
        run_condition_type=rct,
        run_condition_expression=run_condition_expression,
        run_condition_statuses=rcs,
        reset_scenario_status=reset_scenario_status,
    )
    _add_step(ctx, scenario_id, project, step, at=at)


@app.command("add-step-compute-metrics")
def add_step_compute_metrics(
    ctx: typer.Context,
    scenario_id: str = typer.Argument(help="Scenario ID"),
    name: str = typer.Option(..., "--name", help="Step name"),
    dataset: list[str] = typer.Option(
        [],
        "--dataset",
        help="Dataset to compute metrics on (repeatable; PROJECT.NAME cross-project).",
    ),
    folder: list[str] = typer.Option(
        [],
        "--folder",
        help=(
            "Managed folder to refresh file-count/size metrics on (repeatable). "
            "Maps to {type:MANAGED_FOLDER, itemId} in computes[]."
        ),
    ),
    saved_model: list[str] = typer.Option(
        [],
        "--saved-model",
        help=(
            "Saved model to refresh drift metrics on (repeatable). Maps to "
            "{type:SAVED_MODEL, itemId} in computes[]."
        ),
    ),
    proceed_on_failure: bool = typer.Option(False, "--proceed-on-failure"),
    max_retries: int | None = typer.Option(None, "--max-retries"),
    delay_between_retries: int | None = typer.Option(None, "--delay-between-retries"),
    run_condition_type: str | None = typer.Option(None, "--run-condition-type"),
    run_condition_statuses: list[str] = typer.Option([], "--run-condition-statuses"),
    run_condition_expression: str | None = typer.Option(
        None, "--run-condition-expression"
    ),
    reset_scenario_status: bool = typer.Option(False, "--reset-scenario-status"),
    at: int | None = typer.Option(None, "--at"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Add a compute_metrics step. Refreshes metrics on datasets, managed
    folders, and/or saved models — DSS computes_metrics accepts a polymorphic
    computes[] mixing all three. Dataset metrics include row counts; folder
    metrics include file-count/size/timestamp; saved-model metrics include
    drift detectors against stored evaluations.
    """
    if not (dataset or folder or saved_model):
        exit_with_error(
            "compute-metrics needs at least one --dataset, --folder, or --saved-model.",
        )
    rct, rcs = validate_run_options(
        run_condition_type,
        run_condition_expression,
        run_condition_statuses,
        max_retries,
        delay_between_retries,
    )
    params = {
        "computes": mixed_typed_items(
            datasets=dataset, folders=folder, saved_models=saved_model
        )
    }
    step = build_step(
        "compute_metrics",
        name,
        params,
        proceed_on_failure=proceed_on_failure,
        max_retries=max_retries,
        delay_between_retries=delay_between_retries,
        run_condition_type=rct,
        run_condition_expression=run_condition_expression,
        run_condition_statuses=rcs,
        reset_scenario_status=reset_scenario_status,
    )
    _add_step(ctx, scenario_id, project, step, at=at)


@app.command("add-step-reload-schema")
def add_step_reload_schema(
    ctx: typer.Context,
    scenario_id: str = typer.Argument(help="Scenario ID"),
    name: str = typer.Option(..., "--name", help="Step name"),
    dataset: list[str] = typer.Option(
        ..., "--dataset", help="Dataset to reload schema on (repeatable)"
    ),
    proceed_on_failure: bool = typer.Option(False, "--proceed-on-failure"),
    max_retries: int | None = typer.Option(None, "--max-retries"),
    delay_between_retries: int | None = typer.Option(None, "--delay-between-retries"),
    run_condition_type: str | None = typer.Option(None, "--run-condition-type"),
    run_condition_statuses: list[str] = typer.Option([], "--run-condition-statuses"),
    run_condition_expression: str | None = typer.Option(
        None, "--run-condition-expression"
    ),
    reset_scenario_status: bool = typer.Option(False, "--reset-scenario-status"),
    at: int | None = typer.Option(None, "--at"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Add a reload_schema step (refresh source schemas before downstream builds).

    Common before recursive builds when source tables/columns may have changed.
    """
    rct, rcs = validate_run_options(
        run_condition_type,
        run_condition_expression,
        run_condition_statuses,
        max_retries,
        delay_between_retries,
    )
    params = {"items": dataset_items(dataset)}
    step = build_step(
        "reload_schema",
        name,
        params,
        proceed_on_failure=proceed_on_failure,
        max_retries=max_retries,
        delay_between_retries=delay_between_retries,
        run_condition_type=rct,
        run_condition_expression=run_condition_expression,
        run_condition_statuses=rcs,
        reset_scenario_status=reset_scenario_status,
    )
    _add_step(ctx, scenario_id, project, step, at=at)


@app.command("add-step-run-scenario")
def add_step_run_scenario(
    ctx: typer.Context,
    scenario_id: str = typer.Argument(help="Scenario ID"),
    name: str = typer.Option(..., "--name", help="Step name"),
    target_scenario: str = typer.Option(
        ..., "--scenario-id", help="Scenario to invoke"
    ),
    proceed_on_failure: bool = typer.Option(False, "--proceed-on-failure"),
    max_retries: int | None = typer.Option(None, "--max-retries"),
    delay_between_retries: int | None = typer.Option(None, "--delay-between-retries"),
    run_condition_type: str | None = typer.Option(None, "--run-condition-type"),
    run_condition_statuses: list[str] = typer.Option([], "--run-condition-statuses"),
    run_condition_expression: str | None = typer.Option(
        None, "--run-condition-expression"
    ),
    reset_scenario_status: bool = typer.Option(False, "--reset-scenario-status"),
    at: int | None = typer.Option(None, "--at"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Add a run_scenario step (chain another scenario)."""
    rct, rcs = validate_run_options(
        run_condition_type,
        run_condition_expression,
        run_condition_statuses,
        max_retries,
        delay_between_retries,
    )
    params = {"scenarioId": target_scenario}
    step = build_step(
        "run_scenario",
        name,
        params,
        proceed_on_failure=proceed_on_failure,
        max_retries=max_retries,
        delay_between_retries=delay_between_retries,
        run_condition_type=rct,
        run_condition_expression=run_condition_expression,
        run_condition_statuses=rcs,
        reset_scenario_status=reset_scenario_status,
    )
    _add_step(ctx, scenario_id, project, step, at=at)


@app.command("add-step-restart-webapp")
def add_step_restart_webapp(
    ctx: typer.Context,
    scenario_id: str = typer.Argument(help="Scenario ID"),
    name: str = typer.Option(..., "--name", help="Step name"),
    webapp: str = typer.Option(..., "--webapp", help="Webapp ID to restart"),
    proceed_on_failure: bool = typer.Option(False, "--proceed-on-failure"),
    max_retries: int | None = typer.Option(None, "--max-retries"),
    delay_between_retries: int | None = typer.Option(None, "--delay-between-retries"),
    run_condition_type: str | None = typer.Option(None, "--run-condition-type"),
    run_condition_statuses: list[str] = typer.Option([], "--run-condition-statuses"),
    run_condition_expression: str | None = typer.Option(
        None, "--run-condition-expression"
    ),
    reset_scenario_status: bool = typer.Option(False, "--reset-scenario-status"),
    at: int | None = typer.Option(None, "--at"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Add a restart_webapp step (used to refresh dashboard-attached webapps)."""
    rct, rcs = validate_run_options(
        run_condition_type,
        run_condition_expression,
        run_condition_statuses,
        max_retries,
        delay_between_retries,
    )
    params = {"webAppId": webapp}
    step = build_step(
        "restart_webapp",
        name,
        params,
        proceed_on_failure=proceed_on_failure,
        max_retries=max_retries,
        delay_between_retries=delay_between_retries,
        run_condition_type=rct,
        run_condition_expression=run_condition_expression,
        run_condition_statuses=rcs,
        reset_scenario_status=reset_scenario_status,
    )
    _add_step(ctx, scenario_id, project, step, at=at)


@app.command("add-step-refresh-chart-cache")
def add_step_refresh_chart_cache(
    ctx: typer.Context,
    scenario_id: str = typer.Argument(help="Scenario ID"),
    name: str = typer.Option(..., "--name", help="Step name"),
    dashboard: list[str] = typer.Option(
        [], "--dashboard", help="Dashboard ID (repeatable)"
    ),
    dataset: list[str] = typer.Option(
        [], "--dataset", help="Dataset to refresh charts for (repeatable)"
    ),
    force: bool = typer.Option(
        False, "--force", help="Force refresh even if cache fresh"
    ),
    proceed_on_failure: bool = typer.Option(False, "--proceed-on-failure"),
    max_retries: int | None = typer.Option(None, "--max-retries"),
    delay_between_retries: int | None = typer.Option(None, "--delay-between-retries"),
    run_condition_type: str | None = typer.Option(None, "--run-condition-type"),
    run_condition_statuses: list[str] = typer.Option([], "--run-condition-statuses"),
    run_condition_expression: str | None = typer.Option(
        None, "--run-condition-expression"
    ),
    reset_scenario_status: bool = typer.Option(False, "--reset-scenario-status"),
    at: int | None = typer.Option(None, "--at"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Add a refresh_chart_cache step (precompute dashboard tile data)."""
    rct, rcs = validate_run_options(
        run_condition_type,
        run_condition_expression,
        run_condition_statuses,
        max_retries,
        delay_between_retries,
    )
    # Server shape is List<RefreshItem> ({smartName, name}), not plain strings.
    params: dict = {
        "dashboards": [{"smartName": d, "name": d} for d in dashboard],
        "datasets": [{"smartName": d, "name": d} for d in dataset],
        "force": force,
    }
    step = build_step(
        "refresh_chart_cache",
        name,
        params,
        proceed_on_failure=proceed_on_failure,
        max_retries=max_retries,
        delay_between_retries=delay_between_retries,
        run_condition_type=rct,
        run_condition_expression=run_condition_expression,
        run_condition_statuses=rcs,
        reset_scenario_status=reset_scenario_status,
    )
    _add_step(ctx, scenario_id, project, step, at=at)


@app.command("add-step-clear-items")
def add_step_clear_items(
    ctx: typer.Context,
    scenario_id: str = typer.Argument(help="Scenario ID"),
    name: str = typer.Option(..., "--name", help="Step name"),
    clear: list[str] = typer.Option(
        [],
        "--clear",
        help=(
            "Dataset to wipe data on (repeatable; PROJECT.NAME cross-project). "
            "Definition stays; only data is cleared. For folders/models, use "
            "--clear-folder / --clear-model — DSS clear_items accepts a "
            "polymorphic items[] mixing all three."
        ),
    ),
    clear_folder: list[str] = typer.Option(
        [],
        "--clear-folder",
        help=(
            "Managed folder to wipe (repeatable). Definition + permissions "
            "stay; only stored files are deleted. Maps to {type:MANAGED_FOLDER}."
        ),
    ),
    clear_model: list[str] = typer.Option(
        [],
        "--clear-model",
        help=(
            "Saved model to clear training history + predictions on (repeatable). "
            "Maps to {type:SAVED_MODEL}."
        ),
    ),
    proceed_on_failure: bool = typer.Option(False, "--proceed-on-failure"),
    max_retries: int | None = typer.Option(None, "--max-retries"),
    delay_between_retries: int | None = typer.Option(None, "--delay-between-retries"),
    run_condition_type: str | None = typer.Option(None, "--run-condition-type"),
    run_condition_statuses: list[str] = typer.Option([], "--run-condition-statuses"),
    run_condition_expression: str | None = typer.Option(
        None, "--run-condition-expression"
    ),
    reset_scenario_status: bool = typer.Option(False, "--reset-scenario-status"),
    at: int | None = typer.Option(None, "--at"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Add a clear_items step. Wipes data on datasets, managed folders, and/or
    saved models — DSS clear_items accepts a polymorphic items[] mixing all three.

    Common before a full rebuild: clear the target so partial leftovers don't
    pollute the new run. Cheaper than `dku dataset delete` + `create` because
    downstream recipe wiring is preserved.
    """
    if not (clear or clear_folder or clear_model):
        exit_with_error(
            "clear-items needs at least one --clear (dataset), --clear-folder, "
            "or --clear-model.",
        )
    rct, rcs = validate_run_options(
        run_condition_type,
        run_condition_expression,
        run_condition_statuses,
        max_retries,
        delay_between_retries,
    )
    # DSS clear_items step writes the polymorphic array under `clears`, NOT
    # `items` (verified against localhost — DSS silently accepts `items` but
    # drops the data, leaving the step with an empty `clears: []`).
    params: dict = {
        "clears": mixed_typed_items(
            datasets=clear, folders=clear_folder, saved_models=clear_model
        )
    }
    step = build_step(
        "clear_items",
        name,
        params,
        proceed_on_failure=proceed_on_failure,
        max_retries=max_retries,
        delay_between_retries=delay_between_retries,
        run_condition_type=rct,
        run_condition_expression=run_condition_expression,
        run_condition_statuses=rcs,
        reset_scenario_status=reset_scenario_status,
    )
    _add_step(ctx, scenario_id, project, step, at=at)


@app.command("add-step-propagate-schema")
def add_step_propagate_schema(
    ctx: typer.Context,
    scenario_id: str = typer.Argument(help="Scenario ID"),
    name: str = typer.Option(..., "--name", help="Step name"),
    dataset: str = typer.Option(
        ...,
        "--dataset",
        help="Origin dataset (the one whose schema changed). Propagation flows downstream from here.",
    ),
    behavior: str = typer.Option(
        "AUTO_NO_BUILD",
        "--behavior",
        help="Propagation behaviour: AUTO_NO_BUILD (default — only update schemas), AUTO_WITH_BUILDS (also rebuild downstream), MANUAL.",
    ),
    exclude_recipe: list[str] = typer.Option(
        [],
        "--exclude-recipe",
        help="Recipe to skip during propagation (repeatable). Useful for recipes that intentionally drop columns.",
    ),
    mark_as_ok_recipe: list[str] = typer.Option(
        [],
        "--mark-as-ok-recipe",
        help="Recipe to mark as schema-OK without re-applying (repeatable).",
    ),
    proceed_on_failure: bool = typer.Option(False, "--proceed-on-failure"),
    max_retries: int | None = typer.Option(None, "--max-retries"),
    delay_between_retries: int | None = typer.Option(None, "--delay-between-retries"),
    run_condition_type: str | None = typer.Option(None, "--run-condition-type"),
    run_condition_statuses: list[str] = typer.Option([], "--run-condition-statuses"),
    run_condition_expression: str | None = typer.Option(
        None, "--run-condition-expression"
    ),
    reset_scenario_status: bool = typer.Option(False, "--reset-scenario-status"),
    at: int | None = typer.Option(None, "--at"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Add a schema_propagation step.

    Propagates schema changes from --dataset down through the flow. Replaces
    the per-recipe `dku recipe apply-schema` chain when many downstream
    recipes need updating.
    """
    _VALID_BEHAVIORS = {"AUTO_NO_BUILD", "AUTO_WITH_BUILDS", "MANUAL"}
    behavior = behavior.upper()
    if behavior == "AUTO_WITH_BUILD":
        behavior = "AUTO_WITH_BUILDS"
    if behavior not in _VALID_BEHAVIORS:
        exit_with_error(
            f"Invalid --behavior '{behavior}'.",
            details=[f"Valid: {', '.join(sorted(_VALID_BEHAVIORS))}"],
        )
    rct, rcs = validate_run_options(
        run_condition_type,
        run_condition_expression,
        run_condition_statuses,
        max_retries,
        delay_between_retries,
    )
    # Server shape (SchemaPropagationStepRunner): everything nests under
    # params.options (an AppHomepageTile.PropagateSchemaTile). Flat keys are
    # silently dropped by Gson and the step NPEs at run time.
    options: dict = {
        "datasetName": dataset,
        "behavior": behavior,
        "excludedRecipes": list(exclude_recipe),
        "markAsOkRecipes": list(mark_as_ok_recipe),
    }
    params: dict = {"options": options}
    step = build_step(
        "schema_propagation",
        name,
        params,
        proceed_on_failure=proceed_on_failure,
        max_retries=max_retries,
        delay_between_retries=delay_between_retries,
        run_condition_type=rct,
        run_condition_expression=run_condition_expression,
        run_condition_statuses=rcs,
        reset_scenario_status=reset_scenario_status,
    )
    _add_step(ctx, scenario_id, project, step, at=at)


@app.command("add-step-prepare-lambda-package")
def add_step_prepare_lambda_package(
    ctx: typer.Context,
    scenario_id: str = typer.Argument(help="Scenario ID"),
    name: str = typer.Option(..., "--name", help="Step name"),
    api_service: str = typer.Option(
        ..., "--api-service", help="API service ID to package"
    ),
    package_id: str | None = typer.Option(
        None,
        "--package-id",
        help="Optional package ID (defaults to a timestamp-derived value).",
    ),
    proceed_on_failure: bool = typer.Option(False, "--proceed-on-failure"),
    max_retries: int | None = typer.Option(None, "--max-retries"),
    delay_between_retries: int | None = typer.Option(None, "--delay-between-retries"),
    run_condition_type: str | None = typer.Option(None, "--run-condition-type"),
    run_condition_statuses: list[str] = typer.Option([], "--run-condition-statuses"),
    run_condition_expression: str | None = typer.Option(
        None, "--run-condition-expression"
    ),
    reset_scenario_status: bool = typer.Option(False, "--reset-scenario-status"),
    at: int | None = typer.Option(None, "--at"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Add a prepare_lambda_package step (build an API-deployer package from this project's API service).

    Pair with add-step-update-deployment to auto-roll-forward an API endpoint
    after a retrain — the canonical "deploy on every successful retrain"
    pattern.
    """
    rct, rcs = validate_run_options(
        run_condition_type,
        run_condition_expression,
        run_condition_statuses,
        max_retries,
        delay_between_retries,
    )
    # Server field (PrepareLambdaPackageStepParams) is serviceId, not
    # apiServiceId — Gson drops unknown keys silently.
    params: dict = {"serviceId": api_service}
    if package_id:
        params["packageId"] = package_id
    step = build_step(
        "prepare_lambda_package",
        name,
        params,
        proceed_on_failure=proceed_on_failure,
        max_retries=max_retries,
        delay_between_retries=delay_between_retries,
        run_condition_type=rct,
        run_condition_expression=run_condition_expression,
        run_condition_statuses=rcs,
        reset_scenario_status=reset_scenario_status,
    )
    _add_step(ctx, scenario_id, project, step, at=at)


@app.command("add-step-update-deployment")
def add_step_update_deployment(
    ctx: typer.Context,
    scenario_id: str = typer.Argument(help="Scenario ID"),
    name: str = typer.Option(..., "--name", help="Step name"),
    deployment_id: str = typer.Option(
        ..., "--deployment-id", help="API-deployer deployment ID to update"
    ),
    version_id: str | None = typer.Option(
        None,
        "--version-id",
        "--package-id",
        help=(
            "Version (package) ID to deploy — maps to newVersionId "
            "(defaults to the package built earlier in the scenario)."
        ),
    ),
    proceed_on_failure: bool = typer.Option(False, "--proceed-on-failure"),
    max_retries: int | None = typer.Option(None, "--max-retries"),
    delay_between_retries: int | None = typer.Option(None, "--delay-between-retries"),
    run_condition_type: str | None = typer.Option(None, "--run-condition-type"),
    run_condition_statuses: list[str] = typer.Option([], "--run-condition-statuses"),
    run_condition_expression: str | None = typer.Option(
        None, "--run-condition-expression"
    ),
    reset_scenario_status: bool = typer.Option(False, "--reset-scenario-status"),
    at: int | None = typer.Option(None, "--at"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Add an update_apideployer_deployment step.

    Pushes a (just-built) package to a running API-deployer deployment,
    completing the auto-deploy-on-retrain chain when paired with
    add-step-prepare-lambda-package.
    """
    rct, rcs = validate_run_options(
        run_condition_type,
        run_condition_expression,
        run_condition_statuses,
        max_retries,
        delay_between_retries,
    )
    # Server fields (UpdateDeployerDeploymentStepParams) are deploymentId +
    # newVersionId; a packageId key is silently dropped.
    params: dict = {"deploymentId": deployment_id}
    if version_id:
        params["newVersionId"] = version_id
    step = build_step(
        "update_apideployer_deployment",
        name,
        params,
        proceed_on_failure=proceed_on_failure,
        max_retries=max_retries,
        delay_between_retries=delay_between_retries,
        run_condition_type=rct,
        run_condition_expression=run_condition_expression,
        run_condition_statuses=rcs,
        reset_scenario_status=reset_scenario_status,
    )
    _add_step(ctx, scenario_id, project, step, at=at)


_VALID_DASHBOARD_EXPORT_FORMATS = frozenset({"PDF", "PNG", "JPEG"})
_VALID_DASHBOARD_PAPER_SIZES = frozenset(
    {"A4", "A3", "A5", "LETTER", "LEGAL", "TABLOID", "EXECUTIVE", "CUSTOM"}
)
_VALID_DASHBOARD_ORIENTATIONS = frozenset({"PORTRAIT", "LANDSCAPE"})


@app.command("add-step-export-dashboard")
def add_step_export_dashboard(
    ctx: typer.Context,
    scenario_id: str = typer.Argument(help="Scenario ID"),
    name: str = typer.Option(..., "--name", help="Step name"),
    dashboard_id: str = typer.Option(
        ..., "--dashboard-id", help="Dashboard ID to export."
    ),
    output_folder: str = typer.Option(
        ...,
        "--output-folder",
        help="Managed folder ID where the export file is dumped (timestamped).",
    ),
    format: str = typer.Option(
        "PDF",
        "--format",
        help="Export format: PDF (default), PNG, JPEG.",
    ),
    paper_size: str = typer.Option(
        "A4",
        "--paper-size",
        help=(
            "Paper size: A4 (default), A3, A5, LETTER, LEGAL, TABLOID, EXECUTIVE, "
            "CUSTOM (use --width/--height)."
        ),
    ),
    orientation: str = typer.Option(
        "PORTRAIT",
        "--orientation",
        help="PORTRAIT (default) or LANDSCAPE.",
    ),
    width: int | None = typer.Option(
        None,
        "--width",
        help=(
            "Pixel width (only when not --use-dashboard-format-settings). "
            "1240 ≈ A4 portrait at 150 dpi."
        ),
    ),
    height: int | None = typer.Option(
        None,
        "--height",
        help="Pixel height (paired with --width).",
    ),
    use_dashboard_format_settings: bool = typer.Option(
        False,
        "--use-dashboard-format-settings",
        help=(
            "Inherit format from the dashboard's Export… panel instead of "
            "using --paper-size/--orientation/--width/--height."
        ),
    ),
    proceed_on_failure: bool = typer.Option(False, "--proceed-on-failure"),
    max_retries: int | None = typer.Option(None, "--max-retries"),
    delay_between_retries: int | None = typer.Option(None, "--delay-between-retries"),
    run_condition_type: str | None = typer.Option(None, "--run-condition-type"),
    run_condition_statuses: list[str] = typer.Option([], "--run-condition-statuses"),
    run_condition_expression: str | None = typer.Option(
        None, "--run-condition-expression"
    ),
    reset_scenario_status: bool = typer.Option(False, "--reset-scenario-status"),
    at: int | None = typer.Option(None, "--at"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Add a create_dashboard_export step (PDF/PNG snapshot of a dashboard).

    The canonical "after building the flow, snapshot the dashboard for
    archival or downstream upload" pattern. Output lands in the named
    managed folder as a timestamped file.

    Example:
        dku scenario add-step-export-dashboard daily \\
            --name "Snapshot KPI dashboard" \\
            --dashboard-id ABC123 --output-folder REPORTS \\
            --format PDF --paper-size A4 --orientation LANDSCAPE -P PROJ
    """
    fmt = format.upper()
    if fmt not in _VALID_DASHBOARD_EXPORT_FORMATS:
        exit_with_error(
            f"Invalid --format '{format}'.",
            details=[f"Valid: {', '.join(sorted(_VALID_DASHBOARD_EXPORT_FORMATS))}"],
        )
    ps = paper_size.upper()
    if ps not in _VALID_DASHBOARD_PAPER_SIZES:
        exit_with_error(
            f"Invalid --paper-size '{paper_size}'.",
            details=[f"Valid: {', '.join(sorted(_VALID_DASHBOARD_PAPER_SIZES))}"],
        )
    orient = orientation.upper()
    if orient not in _VALID_DASHBOARD_ORIENTATIONS:
        exit_with_error(
            f"Invalid --orientation '{orientation}'.",
            details=[f"Valid: {', '.join(sorted(_VALID_DASHBOARD_ORIENTATIONS))}"],
        )
    if (width is None) != (height is None):
        exit_with_error(
            "--width and --height must be provided together.",
        )
    rct, rcs = validate_run_options(
        run_condition_type,
        run_condition_expression,
        run_condition_statuses,
        max_retries,
        delay_between_retries,
    )
    export_format: dict = {
        "paperSize": ps,
        "orientation": orient,
        "fileType": fmt,
    }
    if width is not None and height is not None:
        export_format["width"] = width
        export_format["height"] = height
    params: dict = {
        "dashboardId": dashboard_id,
        "exportFormat": export_format,
        "shouldUseDashboardFormatSettings": use_dashboard_format_settings,
        "folderSmartId": output_folder,
    }
    step = build_step(
        "create_dashboard_export",
        name,
        params,
        proceed_on_failure=proceed_on_failure,
        max_retries=max_retries,
        delay_between_retries=delay_between_retries,
        run_condition_type=rct,
        run_condition_expression=run_condition_expression,
        run_condition_statuses=rcs,
        reset_scenario_status=reset_scenario_status,
    )
    _add_step(ctx, scenario_id, project, step, at=at)


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
) -> None:
    """List reporters on a scenario."""
    project_key = resolve_project(project)
    output = resolve_output_format()
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
        help="When to send: failure (outcome != SUCCESS), success, always, or a "
        "raw DSS run-condition expression such as "
        '\'outcome == "SUCCESS" && parseInt(variables["n_alerts"]) > 0\'',
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
    --condition to branch on outcome, or pass a raw run-condition expression
    for variable-driven alerting (set the variable in an earlier scenario
    step, e.g. a custom_python step calling set_scenario_variables).

    Examples:
        Alert on failure:   dku scenario add-reporter nightly --recipient ops@example.com --condition failure -P PROJ
        Notice on success:  dku scenario add-reporter nightly --recipient team@example.com --condition success -P PROJ
        Variable-driven:    dku scenario add-reporter alerts --recipient ops@x \\
            --condition 'parseInt(variables["n_alerts"]) > 0' -P PROJ
    """
    if condition in _REPORTER_CONDITIONS:
        run_condition, cond_enabled = _REPORTER_CONDITIONS[condition]
        condition_label = condition
    elif condition.replace("_", "").isalnum():
        # A bare word that isn't a known keyword is a typo, not an expression.
        exit_with_error(
            f"Unknown condition '{condition}'.",
            details=[
                "Valid conditions: failure, success, always",
                "Or pass a raw run-condition expression, e.g. "
                '\'outcome == "SUCCESS" && parseInt(variables["n_alerts"]) > 0\'',
            ],
        )
    else:
        # A raw DSS run-condition expression, evaluated by the backend at
        # reporter time. Saved as-is; DSS validates at send time.
        run_condition, cond_enabled = condition, True
        condition_label = "custom-condition"
    reporter = {
        "name": name or f"email on {condition_label}",
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

        def append(settings):
            settings.raw_reporters.append(reporter)
            return len(settings.raw_reporters) - 1

        idx = mutate_settings(
            client,
            project_key,
            "scenario",
            scenario_id,
            fetch=scenario.get_settings,
            mutate=append,
        )
        success(
            f"Added '{condition_label}' email reporter to '{recipient}' on scenario "
            f"'{scenario_id}' at index {idx}"
        )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)
