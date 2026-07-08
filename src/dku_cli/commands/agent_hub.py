"""dku agent-hub — list, config, set-config, start, stop.

LIMITATION (verified on DSS 14.5.1, agent-hub plugin v1.2.4–v1.3.2):
The Agent Hub plugin stores its UI configuration (orchestrating LLM,
enrolled enterprise agents, logos, RGB colors, Quick Agents, tools,
embedding LLM, augmented LLMs, etc.) in a private SQLite store accessed
via the webapp's Flask backend at `/web-apps-backends/{proj}/{hub}/...`.
That endpoint exists but requires session-cookie auth — NOT the API key
the public DSS SDK uses.

The webapp's `config` field that the public SDK CAN write to holds ONLY
plugin runtime knobs (`log_level`, `storage_type`). Writing other keys
to it (as earlier CLI verbs did) appears to succeed but the plugin never
reads those keys, so the hub's behavior is unchanged.

Until the agent-hub plugin exposes a public REST API for programmatic
configuration, hub creation, agent enrollment (add AND remove — earlier
`add-agent`/`remove-agent` verbs wrote keys the plugin never read and
were removed), and UI-config management remain UI-only.
This CLI surface is therefore intentionally minimal — see commands.md.
"""

from __future__ import annotations

import typer

from dku_cli.errors import exit_with_error, handle_api_error
from dku_cli.helpers import get_client_from_ctx, read_json_input, resolve_project
from dku_cli.output import (
    error,
    hint,
    render,
    render_raw,
    resolve_output_format,
    success,
    warn,
)

app = typer.Typer(
    help="Manage DSS Agent Hub instances (limited surface — see notes). "
    "Agent enrollment (add/remove) lives in the plugin's private store and is UI-only."
)

_HUB_TYPE = "agent-hub"

# Boot failure emitted by the agent-hub plugin when storage_type=LOCAL (SQLite)
# on a containerized instance — the backend pod crash-loops with this message.
_REMOTE_DB_MARKER = "running backend in a docker container requires a remote db"

_REMOTE_DB_FIX = [
    "On containerized instances the hub needs a remote database:",
    '  dku agent-hub set-config -d \'{"storage_type": "REMOTE", '
    '"db_connection": "<SQL_CONNECTION>", "tables_prefix": "<PREFIX>"}\'',
    "Then restart: dku agent-hub start",
]


def _crash_tail_lines(webapp) -> list[str]:
    """Best-effort read of the backend's last crash log tail."""
    try:
        raw = webapp.get_state().state
        crash_tail = raw.get("lastCrashLogTail") if isinstance(raw, dict) else None
        return list(crash_tail.get("lines") or []) if crash_tail else []
    except Exception:
        return []


def _resolve_hub(ctx: typer.Context, project_key: str, hub_id: str | None):
    """Find the AgentHub webapp and return (webapp, config dict).

    If hub_id is provided, uses it directly. Otherwise auto-detects by scanning
    project webapps for type containing 'agent-hub'.
    """
    client = get_client_from_ctx(ctx)
    proj = client.get_project(project_key)

    if hub_id:
        webapp = proj.get_webapp(hub_id)
        settings = webapp.get_settings()
        raw = settings.get_raw()
        return webapp, raw.get("config", {})

    # Auto-detect
    webapps = proj.list_webapps()
    hubs = [w for w in webapps if _HUB_TYPE in w.get("type", "")]

    if len(hubs) == 0:
        exit_with_error(
            f"No Agent Hub webapp found in project {project_key}.",
            details=[
                "Agent Hub is a plugin webapp — create it in the DSS UI:",
                "  Project > Web Apps > New Web App > Agent Hub",
                "The public DSS API does not currently expose plugin webapp creation.",
            ],
        )
    if len(hubs) > 1:
        hub_list = [f"  {h.get('id', '')} ({h.get('name', '')})" for h in hubs]
        exit_with_error(
            f"Multiple Agent Hub webapps found in {project_key}. Use --hub to specify one.",
            details=["Available hubs:", *hub_list],
        )

    webapp = proj.get_webapp(hubs[0].get("id", ""))
    settings = webapp.get_settings()
    raw = settings.get_raw()
    return webapp, raw.get("config", {})


def _save_config(webapp, config: dict) -> None:
    """Write the config dict back to the webapp definition."""
    settings = webapp.get_settings()
    raw = settings.get_raw()
    raw["config"] = config
    settings.save()


@app.command("list")
def list_hubs(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """List Agent Hub instances in a project."""
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        webapps = proj.list_webapps()

        data = []
        for w in webapps:
            if _HUB_TYPE in w.get("type", ""):
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
            title=f"Agent Hubs ({project_key})",
        )
    except Exception as e:
        handle_api_error(e)


@app.command()
def config(
    ctx: typer.Context,
    hub: str | None = typer.Option(
        None, "--hub", help="Agent Hub webapp ID (auto-detected if only one exists)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Show the Agent Hub webapp's plugin-runtime config.

    This is the contents of the webapp `config` field — typically just
    `{log_level, storage_type}`. The hub's UI configuration (LLMs, enrolled
    agents, branding, tools) lives in the plugin's private SQLite store and is
    NOT visible here. Configure those in the DSS Agent Hub UI.
    """
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        _, cfg = _resolve_hub(ctx, project_key, hub)
        render_raw(cfg, output_format=output)
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("set-config")
def set_config(
    ctx: typer.Context,
    definition: str = typer.Option(
        ...,
        "--definition",
        "-d",
        help="Config JSON — shallow merges into current. String, @file.json, or '-' for stdin.",
    ),
    hub: str | None = typer.Option(
        None, "--hub", help="Agent Hub webapp ID (auto-detected if only one exists)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Update the Agent Hub webapp's plugin-runtime config (shallow merge).

    Only the `log_level` and `storage_type` keys are read by the agent-hub
    plugin. Setting other keys (e.g. `default_llm_id`, `agents_ids`) writes the
    fields but the plugin ignores them — those settings live in the plugin's
    private SQLite store and must be configured via the DSS UI.

    Examples:
      dku agent-hub set-config -d '{"log_level": "DEBUG"}' -P PROJ
    """
    project_key = resolve_project(project)
    try:
        webapp, cfg = _resolve_hub(ctx, project_key, hub)
        updates = read_json_input(definition)
        cfg.update(updates)
        _save_config(webapp, cfg)
        success("Updated Agent Hub configuration")
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def start(
    ctx: typer.Context,
    hub: str | None = typer.Option(
        None, "--hub", help="Agent Hub webapp ID (auto-detected if only one exists)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Start or restart the Agent Hub backend and verify it actually boots.

    On containerized instances, storage_type=LOCAL (SQLite) makes the backend
    crash-loop with "running backend in a docker container requires a remote
    db" — this command detects that and prescribes the REMOTE-storage fix.
    """
    from dataikuapi.utils import DataikuException

    project_key = resolve_project(project)
    try:
        webapp, cfg = _resolve_hub(ctx, project_key, hub)
        future = webapp.start_or_restart_backend()
        try:
            future.wait_for_result()
        except DataikuException as boot_err:
            error("Agent Hub backend failed to start.")
            print(str(boot_err))
            crash_lines = _crash_tail_lines(webapp)
            for line in crash_lines:
                print(line)
            blob = " ".join([str(boot_err), *crash_lines]).lower()
            if _REMOTE_DB_MARKER in blob:
                exit_with_error(
                    "The hub uses storage_type=LOCAL, which is unsupported on "
                    "containerized instances.",
                    details=_REMOTE_DB_FIX,
                )
            raise typer.Exit(1) from boot_err
        # Start can report success while the pod crash-loops — check the
        # backend state for the known remote-db failure before claiming OK.
        crash_lines = _crash_tail_lines(webapp)
        if any(_REMOTE_DB_MARKER in line.lower() for line in crash_lines):
            error("Agent Hub backend started but is crash-looping:")
            for line in crash_lines:
                print(line)
            exit_with_error(
                "The hub uses storage_type=LOCAL, which is unsupported on "
                "containerized instances.",
                details=_REMOTE_DB_FIX,
            )
        success("Agent Hub backend started")
        if cfg.get("storage_type") == "LOCAL":
            warn(
                "storage_type is LOCAL (SQLite). If this instance runs webapps "
                "in containers, the backend will crash-loop — switch to REMOTE "
                "storage with a SQL db_connection and tables_prefix."
            )
            hint(f"dku webapp logs {webapp.webapp_id} -P {project_key}")
    except (SystemExit, typer.Exit):
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def stop(
    ctx: typer.Context,
    hub: str | None = typer.Option(
        None, "--hub", help="Agent Hub webapp ID (auto-detected if only one exists)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Stop the Agent Hub backend."""
    project_key = resolve_project(project)
    try:
        webapp, _ = _resolve_hub(ctx, project_key, hub)
        webapp.stop_backend()
        success("Agent Hub backend stopped")
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)
