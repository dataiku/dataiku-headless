"""dku notebook — list, get, create, delete, sessions, stop, clear-outputs, history."""

from __future__ import annotations

import typer

from dku_cli.errors import handle_api_error
from dku_cli.helpers import get_client_from_ctx, resolve_project
from dku_cli.output import hint, render, render_raw, resolve_output_format, success

app = typer.Typer(help="Manage DSS notebooks (Jupyter and SQL).")


@app.command("list")
def list_notebooks(
    ctx: typer.Context,
    nb_type: str | None = typer.Option(
        None,
        "--type",
        "-t",
        help="Filter by type: jupyter, sql (default: all)",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """List notebooks in a project. Combines Jupyter and SQL notebooks."""
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)

        data = []
        if nb_type is None or nb_type == "jupyter":
            for nb in proj.list_jupyter_notebooks(as_type="listitems"):
                nb_name = getattr(nb, "name", None) or getattr(
                    nb, "notebook_name", str(nb)
                )
                data.append({"name": nb_name, "type": "jupyter"})

        if nb_type is None or nb_type == "sql":
            for nb in proj.list_sql_notebooks(as_type="listitems"):
                nb_name = getattr(nb, "name", None) or getattr(nb, "_data", {}).get(
                    "name", str(nb)
                )
                data.append({"name": nb_name, "type": "sql"})

        render(
            data,
            ["name", "type"],
            output_format=output,
            title=f"Notebooks ({project_key})",
        )
    except Exception as e:
        handle_api_error(e)


@app.command()
def get(
    ctx: typer.Context,
    name: str = typer.Argument(help="Jupyter notebook name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Get a Jupyter notebook's content."""
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        nb = proj.get_jupyter_notebook(name)
        content = nb.get_content()
        render_raw(content.get_raw(), output_format=output)
    except Exception as e:
        handle_api_error(e)


@app.command()
def create(
    ctx: typer.Context,
    name: str = typer.Argument(help="Notebook name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a new Jupyter notebook."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        default_content = {
            "metadata": {
                "kernelspec": {
                    "display_name": "Python 3",
                    "language": "python",
                    "name": "python3",
                },
                "language_info": {"name": "python"},
            },
            "nbformat": 4,
            "nbformat_minor": 2,
            "cells": [],
        }
        proj.create_jupyter_notebook(name, default_content)
        success(f"Created notebook '{name}' in {project_key}")
        hint(f"dku notebook get {name} -P {project_key}")
    except Exception as e:
        handle_api_error(e)


@app.command()
def delete(
    ctx: typer.Context,
    name: str = typer.Argument(help="Jupyter notebook name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip safety guard"),
) -> None:
    """Delete a Jupyter notebook."""
    from dku_cli.safety import Tier, guard

    project_key = resolve_project(project)
    guard(
        ctx,
        tier=Tier.DELETE,
        action="notebook.delete",
        subject=f"notebook '{name}' in {project_key}",
        yes=yes,
        prompt=f"Delete notebook '{name}' from project {project_key}?",
    )
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        nb = proj.get_jupyter_notebook(name)
        nb.delete()
        success(f"Deleted notebook '{name}' from {project_key}")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def sessions(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """List running notebook sessions."""
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        running = proj.list_running_notebooks()

        data = []
        for s in running:
            data.append(
                {
                    "name": s.get("name", ""),
                    "kernel_id": s.get("kernelId", ""),
                    "session_id": s.get("sessionId", ""),
                }
            )

        render(
            data,
            ["name", "kernel_id", "session_id"],
            output_format=output,
            title=f"Running Notebooks ({project_key})",
        )
    except Exception as e:
        handle_api_error(e)


@app.command()
def stop(
    ctx: typer.Context,
    name: str = typer.Argument(help="Jupyter notebook name"),
    session: str | None = typer.Option(
        None, "--session", "-s", help="Session ID to stop"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Stop a running notebook session."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        nb = proj.get_jupyter_notebook(name)
        kwargs = {}
        if session is not None:
            kwargs["session_id"] = session
        nb.unload(**kwargs)
        success(f"Stopped notebook '{name}' in {project_key}")
    except Exception as e:
        handle_api_error(e)


@app.command("clear-outputs")
def clear_outputs(
    ctx: typer.Context,
    name: str = typer.Argument(help="Jupyter notebook name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip safety guard"),
) -> None:
    """Clear all outputs from a Jupyter notebook."""
    from dku_cli.safety import Tier, guard

    project_key = resolve_project(project)
    guard(
        ctx,
        tier=Tier.DELETE,
        action="notebook.clear_outputs",
        subject=f"all outputs in notebook '{name}' ({project_key})",
        yes=yes,
        prompt=f"Clear all outputs from notebook '{name}' in {project_key}?",
    )
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        nb = proj.get_jupyter_notebook(name)
        nb.clear_outputs()
        success(f"Cleared outputs for notebook '{name}' in {project_key}")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def history(
    ctx: typer.Context,
    name: str = typer.Argument(help="SQL notebook name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Show execution history of a SQL notebook."""
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        nb = proj.get_sql_notebook(name)
        hist = nb.get_history()
        if hasattr(hist, "get_raw"):
            render_raw(hist.get_raw(), output_format=output)
        else:
            render_raw(hist, output_format=output)
    except Exception as e:
        handle_api_error(e)
