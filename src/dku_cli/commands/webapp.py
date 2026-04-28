"""dku webapp — list, create, start, stop, status, get/set-definition."""

from __future__ import annotations

import typer

from dku_cli.errors import exit_with_error, handle_api_error
from dku_cli.helpers import get_client_from_ctx, read_json_input, resolve_project
from dku_cli.output import render, render_raw, resolve_output_format, success

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
