"""dku webapp — list, create, start, stop, status, logs, get/set-definition."""

from __future__ import annotations

import json
import time

import typer

from dku_cli.errors import exit_with_error, handle_api_error
from dku_cli.helpers import get_client_from_ctx, read_json_input, resolve_project
from dku_cli.output import info, render, render_raw, resolve_output_format, success

app = typer.Typer(
    help="Manage DSS web applications (list, start/stop, read/edit code)."
)


@app.command("list")
def list_webapps(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List web applications in a project."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        webapps = proj.list_webapps()

        data = []
        for w in webapps:
            data.append(
                {
                    "id": w.get("id", ""),
                    "name": w.get("name", ""),
                    "type": w.get("type", ""),
                }
            )

        render(
            data,
            ["id", "name", "type"],
            output_format=output,
            title=f"Web Apps ({project_key})",
        )
    except Exception as e:
        handle_api_error(e)


WEBAPP_TYPES = ("STANDARD", "BOKEH", "DASH", "STREAMLIT", "SHINY")


@app.command()
def create(
    ctx: typer.Context,
    name: str = typer.Argument(help="Name for the new web app"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    webapp_type: str = typer.Option(
        "STANDARD",
        "--type",
        "-t",
        help=f"Web app type: {', '.join(WEBAPP_TYPES)}",
    ),
) -> None:
    """Create a new web application.

    Supported types: STANDARD (HTML/CSS/JS + Python backend),
    BOKEH, DASH, STREAMLIT, SHINY.
    """
    project_key = resolve_project(project)
    upper_type = webapp_type.upper()
    if upper_type not in WEBAPP_TYPES:
        exit_with_error(
            f"Unsupported web app type: '{webapp_type}'",
            details=[
                f"Supported types: {', '.join(WEBAPP_TYPES)}",
                "Example: dku webapp create MyApp -P PROJ --type DASH",
            ],
        )
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        webapp = proj.create_webapp(name, webapp_type=upper_type)
        success(f"Created {upper_type} web app '{name}' (id={webapp.webapp_id})")
    except Exception as e:
        handle_api_error(e)


@app.command()
def start(
    ctx: typer.Context,
    webapp_id: str = typer.Argument(help="Web app ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Start or restart a web app backend."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        webapp = proj.get_webapp(webapp_id)
        webapp.start_or_restart_backend()
        success(f"Started web app '{webapp_id}'")
    except Exception as e:
        handle_api_error(e)


@app.command()
def restart(
    ctx: typer.Context,
    webapp_id: str = typer.Argument(help="Web app ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Restart a running web app backend."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        webapp = proj.get_webapp(webapp_id)
        webapp.start_or_restart_backend()
        success(f"Restarted web app '{webapp_id}'")
    except Exception as e:
        handle_api_error(e)


@app.command()
def stop(
    ctx: typer.Context,
    webapp_id: str = typer.Argument(help="Web app ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Stop a web app backend."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        webapp = proj.get_webapp(webapp_id)
        webapp.stop_backend()
        success(f"Stopped web app '{webapp_id}'")
    except Exception as e:
        handle_api_error(e)


@app.command()
def status(
    ctx: typer.Context,
    webapp_id: str = typer.Argument(help="Web app ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show web app backend status."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        webapp = proj.get_webapp(webapp_id)
        backend_state = webapp.get_state()

        data = [
            {"field": "ID", "value": webapp_id},
            {"field": "Running", "value": str(backend_state.running)},
        ]

        render(
            data,
            ["field", "value"],
            output_format=output,
            title=f"Web App: {webapp_id}",
        )
    except Exception as e:
        handle_api_error(e)


@app.command("get-definition")
def get_definition(
    ctx: typer.Context,
    webapp_id: str = typer.Argument(help="Web app ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Get the raw definition of a web app as JSON (includes source code in params)."""
    project_key = resolve_project(project)
    output = resolve_output_format(output, allowed=("json",), default="json")
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        webapp = proj.get_webapp(webapp_id)
        defn = webapp.get_settings().get_raw()
        render_raw(defn, output_format=output)
    except Exception as e:
        handle_api_error(e)


@app.command("set-definition")
def set_definition(
    ctx: typer.Context,
    webapp_id: str = typer.Argument(help="Web app ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    definition: str = typer.Option(
        ...,
        "--definition",
        "-d",
        help="JSON definition (string, @file.json, or - for stdin)",
    ),
) -> None:
    """Update a web app's definition from JSON (use get-definition to read current state first)."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        webapp = proj.get_webapp(webapp_id)
        new_def = read_json_input(definition)
        settings = webapp.get_settings()
        raw = settings.get_raw()
        raw.clear()
        raw.update(new_def)
        settings.save()
        success(f"Updated definition for web app '{webapp_id}'")
    except Exception as e:
        handle_api_error(e)


# ── logs ───────────────────────────────────────────────────────────────
#
# DSS exposes the webapp backend log tail via the same endpoint as backend
# state (/projects/{P}/webapps/{W}/backend/state). The response body carries a
# `currentLogTail` object with `{totalLines, lines[]}`. The server returns at
# most ~80 lines per call regardless of query params (verified live — `lines`,
# `tail`, `maxLines`, `nbLines` all return 80). `totalLines` is the monotonic
# overall count, which we use as a high-water mark for --follow.
#
# When the backend is stopped, `currentLogTail` is absent — that's the cue to
# emit a prescriptive "start the backend first" error rather than printing
# nothing.


def _fetch_log_tail(
    webapp, project_key: str, webapp_id: str
) -> tuple[int, list[str], bool]:
    """Return (totalLines, lines, running) from DSS backend state.

    Raises (via exit_with_error) when the backend is stopped, since the API
    omits `currentLogTail` entirely in that case and a blank exit would leave
    the agent guessing.
    """
    state_wrapper = webapp.get_state()
    raw = state_wrapper.state  # public property → underlying dict
    running = bool(state_wrapper.running)
    tail = raw.get("currentLogTail") if isinstance(raw, dict) else None
    if not tail:
        if not running:
            exit_with_error(
                f"Web app '{webapp_id}' has no logs — backend is not running.",
                code="webapp_not_running",
                details=[
                    f"Start it with: dku webapp start {webapp_id} -P {project_key}",
                    "Then re-run `dku webapp logs` after a few seconds.",
                ],
                status=1,
            )
        # Running but no tail yet (just started, log file not flushed). Treat as empty.
        return 0, [], running
    return int(tail.get("totalLines", 0) or 0), list(tail.get("lines") or []), running


def _follow_logs(
    webapp, project_key: str, webapp_id: str, initial_tail: int | None
) -> None:
    """Stream new log lines until Ctrl-C, polling every 2s."""
    total, lines, _ = _fetch_log_tail(webapp, project_key, webapp_id)
    seed = lines if initial_tail is None else lines[-initial_tail:]
    for line in seed:
        print(line, flush=True)
    last_total = total
    info(f"Following {webapp_id} — Ctrl-C to stop (polls every 2s).")
    try:
        while True:
            time.sleep(2)
            total, lines, _ = _fetch_log_tail(webapp, project_key, webapp_id)
            new_count = total - last_total
            if new_count <= 0:
                continue
            # New lines sit at the tail of `lines`. The server caps `lines` at
            # ~80, so if we missed more than 80 we'll lose history — print
            # everything we got and warn once.
            if new_count > len(lines):
                info(
                    f"(missed {new_count - len(lines)} lines — poll interval too slow)"
                )
                n_to_show = len(lines)
            else:
                n_to_show = new_count
            for line in lines[-n_to_show:]:
                print(line, flush=True)
            last_total = total
    except KeyboardInterrupt:
        info("Stopped.")


@app.command()
def logs(
    ctx: typer.Context,
    webapp_id: str = typer.Argument(help="Web app ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    tail: int | None = typer.Option(
        None,
        "--tail",
        "-n",
        help="Show only the last N lines (DSS caps server-side tail at ~80).",
    ),
    follow: bool = typer.Option(
        False,
        "--follow",
        "-f",
        help="Stream new log lines as they appear (Ctrl-C to stop).",
    ),
    output: str | None = typer.Option(
        None,
        "-o",
        "--output",
        help="Output format: text (default, one line per row, pipe-friendly) or json.",
    ),
) -> None:
    """Read recent backend logs for a web app.

    DSS returns the most recent ~80 lines per call (server-side cap). Use
    `--tail N` to trim further, or `--follow` to stream new lines live.
    Default output is plain text (one line per row) so you can pipe to grep:

        dku webapp logs WEBAPP_ID -P PROJ | grep ERROR
    """
    project_key = resolve_project(project)
    fmt = resolve_output_format(output, allowed=("text", "json"), default="text")

    if follow and fmt == "json":
        exit_with_error(
            "`--follow` cannot be combined with `-o json`.",
            code="invalid_flag_combo",
            details=[
                "Streaming requires line-by-line text output.",
                "Use --follow alone, or drop --follow and use -o json for a snapshot.",
            ],
        )
    if tail is not None and tail <= 0:
        exit_with_error(
            f"--tail must be a positive integer (got {tail}).",
            code="invalid_argument",
            details=["Example: dku webapp logs WEBAPP_ID -P PROJ --tail 20"],
        )

    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        webapp = proj.get_webapp(webapp_id)

        if follow:
            _follow_logs(webapp, project_key, webapp_id, tail)
            return

        total, lines, running = _fetch_log_tail(webapp, project_key, webapp_id)
        shown = lines if tail is None else lines[-tail:]

        if fmt == "json":
            payload = {
                "webappId": webapp_id,
                "projectKey": project_key,
                "running": running,
                "totalLines": total,
                "returnedLines": len(shown),
                "serverTailSize": len(lines),
                "lines": shown,
            }
            print(json.dumps(payload, indent=2))
            return

        for line in shown:
            print(line)
        if tail is None and total > len(shown):
            info(
                f"Showing {len(shown)} of {total} total log lines "
                f"(DSS caps server-side tail at ~80)."
            )
    except Exception as e:
        handle_api_error(e)
