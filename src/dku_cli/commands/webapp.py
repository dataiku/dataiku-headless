"""dku webapp — list, create, start, stop, status, logs, get/set-definition."""

from __future__ import annotations

import json
import time

import typer

from dataikuapi.utils import DataikuException

from dku_cli.errors import exit_with_error, handle_api_error
from dku_cli.helpers import get_client_from_ctx, read_json_input, resolve_project
from dku_cli.output import (
    error,
    hint,
    info,
    render,
    render_raw,
    resolve_output_format,
    success,
    warn,
)

app = typer.Typer(
    help="Manage DSS web applications (list, start/stop, read/edit code)."
)


@app.command("list")
def list_webapps(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """List web applications in a project."""
    project_key = resolve_project(project)
    output = resolve_output_format()
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
        hint(f"dku webapp start {webapp.webapp_id} -P {project_key}")
    except Exception as e:
        handle_api_error(e)


def _warn_unbuilt_image_hint() -> None:
    """Emit the most common cause of a crash with no log: an unbuilt code-env image.

    A webapp backend that inherits a container code env crashes silently (no
    log tail) when that env's container image was never built. Point the user
    at the rebuild verb, or at falling back to the DSS process.
    """
    warn(
        "Backend crashed with no log — the inherited container's code-env "
        "image may not be built."
    )
    hint(
        "Verify: dku code-env update-images <env>; or run the webapp backend "
        "on the DSS process (Container = None)."
    )


def _print_crash_tail(webapp, webapp_id: str) -> None:
    """Print lastCrashLogTail to stdout after a failed boot (best-effort).

    Called right after a DataikuException from wait_for_result() so the caller
    already printed the root-cause message; this adds the raw log tail for
    extra context. When the crash tail is empty (the backend died before
    writing any log), fall back to the unbuilt-image hint. Failures are
    silently swallowed — never mask the original exception.
    """
    try:
        raw = webapp.get_state().state
        crash_tail = raw.get("lastCrashLogTail") if isinstance(raw, dict) else None
        lines = list(crash_tail.get("lines") or []) if crash_tail else []
        if lines:
            warn(f"Last crash log for '{webapp_id}':")
            for line in lines:
                print(line)
        else:
            _warn_unbuilt_image_hint()
    except Exception:
        pass


@app.command()
def start(
    ctx: typer.Context,
    webapp_id: str = typer.Argument(help="Web app ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Start or restart a web app backend.

    Waits until the backend is confirmed up or has crashed. On a failed boot,
    the crash reason and last crash log tail are printed and the command exits
    non-zero — so deploy scripts and CI pipelines get actionable output without
    needing to poll `dku webapp logs` separately.
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        webapp = proj.get_webapp(webapp_id)
        future = webapp.start_or_restart_backend()
        try:
            future.wait_for_result()
        except DataikuException as boot_err:
            error(f"Web app '{webapp_id}' backend failed to start.")
            print(str(boot_err))
            _print_crash_tail(webapp, webapp_id)
            raise typer.Exit(1)
        success(f"Started web app '{webapp_id}'")
        hint(f"dku webapp logs {webapp_id} -P {project_key}")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def restart(
    ctx: typer.Context,
    webapp_id: str = typer.Argument(help="Web app ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Restart a running web app backend.

    Same wait-and-diagnose behaviour as `start`: blocks until the backend is up
    or has crashed, then surfaces the crash reason and last log tail on failure.
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        webapp = proj.get_webapp(webapp_id)
        future = webapp.start_or_restart_backend()
        try:
            future.wait_for_result()
        except DataikuException as boot_err:
            error(f"Web app '{webapp_id}' backend failed to start.")
            print(str(boot_err))
            _print_crash_tail(webapp, webapp_id)
            raise typer.Exit(1)
        success(f"Restarted web app '{webapp_id}'")
    except typer.Exit:
        raise
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
) -> None:
    """Show web app backend status."""
    project_key = resolve_project(project)
    output = resolve_output_format()
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
) -> None:
    """Get the raw definition of a web app as JSON (includes source code in params)."""
    project_key = resolve_project(project)
    output = resolve_output_format()
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
# When the backend crashes on startup, DSS drops `currentLogTail` but sets
# `lastCrashLogTail` with the traceback lines — present precisely when
# `currentLogTail` is absent. We fall back to that so `dku webapp logs` is
# useful even after a failed boot (e.g. missing dependency in the code env).
# Only when both fields are absent do we emit the "start the backend" error.
#
# `--follow` is live-stream only: it always reads from `currentLogTail` and
# refuses to start when the backend is stopped (crash tail or not).


def _fetch_log_tail(
    webapp, project_key: str, webapp_id: str, prefer_crash: bool = False
) -> tuple[int, list[str], bool, bool]:
    """Return (totalLines, lines, running, crashed) from DSS backend state.

    `crashed` is True when the lines come from `lastCrashLogTail` (stopped
    after a failed boot) rather than `currentLogTail` (live backend). Callers
    should surface this distinction to the user.

    When `prefer_crash` is set, `lastCrashLogTail` is read even if a live
    `currentLogTail` is present — used by `logs --crash` to inspect the prior
    crash after a restart has brought the backend back up.

    Exits via exit_with_error when *both* tails are absent and the backend is
    not running — a blank result would leave the user guessing.
    """
    state_wrapper = webapp.get_state()
    raw = state_wrapper.state  # public property → underlying dict
    running = bool(state_wrapper.running)
    tail = (
        None
        if prefer_crash
        else (raw.get("currentLogTail") if isinstance(raw, dict) else None)
    )
    crashed = False
    if not tail:
        crash_tail = raw.get("lastCrashLogTail") if isinstance(raw, dict) else None
        if crash_tail:
            tail = crash_tail
            crashed = True
    if not tail:
        if not running:
            exit_with_error(
                f"Web app '{webapp_id}' has no logs — backend is not running.",
                details=[
                    f"Start it with: dku webapp start {webapp_id} -P {project_key}",
                    "Then re-run `dku webapp logs` after a few seconds.",
                ],
                status=1,
            )
        # Running but no tail yet (just started, log file not flushed). Treat as empty.
        return 0, [], running, False
    return (
        int(tail.get("totalLines", 0) or 0),
        list(tail.get("lines") or []),
        running,
        crashed,
    )


def _grep_lines(lines: list[str], grep: str | None) -> list[str]:
    """Case-insensitive substring filter, or the lines unchanged when grep is None."""
    if not grep:
        return lines
    lower = grep.lower()
    return [line for line in lines if lower in line.lower()]


def _exit_cannot_follow_crash_tail(webapp_id: str, project_key: str) -> None:
    exit_with_error(
        f"Web app '{webapp_id}' is not running — cannot follow logs.",
        details=[
            "The backend crashed. Use `dku webapp logs` (without --follow) "
            "to see the crash log.",
            f"Fix the error, then restart with: "
            f"dku webapp start {webapp_id} -P {project_key}",
        ],
        status=1,
    )


def _follow_logs(
    webapp, project_key: str, webapp_id: str, initial_tail: int | None, grep: str | None
) -> None:
    """Stream new log lines until Ctrl-C, polling every 2s.

    Refuses to follow when the backend is stopped — crash logs are a one-shot
    snapshot, not a live stream. The user should fix the crash and restart first.
    """
    total, lines, _, crashed = _fetch_log_tail(webapp, project_key, webapp_id)
    if crashed:
        _exit_cannot_follow_crash_tail(webapp_id, project_key)
    seed = lines if initial_tail is None else lines[-initial_tail:]
    for line in _grep_lines(seed, grep):
        print(line, flush=True)
    last_total = total
    info(f"Following {webapp_id} — Ctrl-C to stop (polls every 2s).")
    try:
        while True:
            time.sleep(2)
            total, lines, _, crashed = _fetch_log_tail(webapp, project_key, webapp_id)
            if crashed:
                _exit_cannot_follow_crash_tail(webapp_id, project_key)
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
            for line in _grep_lines(lines[-n_to_show:], grep):
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
    grep: str | None = typer.Option(
        None,
        "--grep",
        help="Show only lines containing this text (case-insensitive).",
    ),
    crash: bool = typer.Option(
        False,
        "--crash",
        help="Force the prior crash log (lastCrashLogTail) even if the "
        "backend is now running — inspect the crash after a restart.",
    ),
) -> None:
    """Read recent backend logs for a web app.

    DSS returns the most recent ~80 lines per call (server-side cap). Use
    `--tail N` to trim further, or `--follow` to stream new lines live.
    Default output is plain text (one line per row) so you can pipe to grep:

        dku webapp logs WEBAPP_ID -P PROJ | grep ERROR
    """
    project_key = resolve_project(project)
    fmt = resolve_output_format()

    if follow and fmt == "json":
        exit_with_error(
            "`--follow` cannot be combined with `--format json`.",
            details=[
                "Streaming requires line-by-line text output.",
                "Use --follow alone, or drop --follow and use --format json "
                "for a snapshot.",
            ],
        )
    if tail is not None and tail <= 0:
        exit_with_error(
            f"--tail must be a positive integer (got {tail}).",
            details=["Example: dku webapp logs WEBAPP_ID -P PROJ --tail 20"],
        )

    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        webapp = proj.get_webapp(webapp_id)

        if follow:
            _follow_logs(webapp, project_key, webapp_id, tail, grep)
            return

        total, lines, running, crashed = _fetch_log_tail(
            webapp, project_key, webapp_id, prefer_crash=crash
        )
        shown = lines if tail is None else lines[-tail:]
        shown = _grep_lines(shown, grep)

        if fmt == "json":
            payload = {
                "webappId": webapp_id,
                "projectKey": project_key,
                "running": running,
                "crashed": crashed,
                "source": "lastCrashLogTail" if crashed else "currentLogTail",
                "totalLines": total,
                "returnedLines": len(shown),
                "serverTailSize": len(lines),
                "lines": shown,
            }
            print(json.dumps(payload, indent=2))
            return

        if crashed:
            warn(f"Backend is not running — showing last crash log for '{webapp_id}'.")
        for line in shown:
            print(line)
        if tail is None and total > len(shown):
            info(
                f"Showing {len(shown)} of {total} total log lines "
                f"(DSS caps server-side tail at ~80)."
            )
    except Exception as e:
        handle_api_error(e)
