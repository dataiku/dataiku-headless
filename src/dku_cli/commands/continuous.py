"""dku continuous — list, start, stop, status for continuous recipe activities."""

from __future__ import annotations

import typer

from dku_cli.errors import handle_api_error
from dku_cli.helpers import get_client_from_ctx, resolve_project
from dku_cli.output import (
    hint,
    info,
    render,
    render_raw,
    resolve_output_format,
    success,
)

app = typer.Typer(help="Manage continuous recipe activities.")


@app.command("list")
def list_activities(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """List continuous activities in a project."""
    project_key = resolve_project(project)
    fmt = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        activities = proj.list_continuous_activities(as_objects=False)

        if fmt == "json":
            render_raw(activities, output_format="json")
        else:
            if not activities:
                info(f"No continuous activities in {project_key}.")
                return

            data = []
            for a in activities:
                data.append(
                    {
                        "recipe": a.get("recipeId", ""),
                        "desired": a.get("desiredState", ""),
                        "state": a.get("mainLoopState", {}).get("state", ""),
                    }
                )
            render(
                data,
                ["recipe", "desired", "state"],
                output_format=fmt,
                title=f"Continuous Activities ({project_key})",
                headers={
                    "recipe": "RECIPE",
                    "desired": "DESIRED",
                    "state": "STATE",
                },
            )
    except Exception as e:
        handle_api_error(e)


@app.command()
def start(
    ctx: typer.Context,
    recipe_id: str = typer.Argument(help="Recipe ID of the continuous activity"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Start a continuous activity.

    Example:
      dku continuous start my_streaming_recipe -P PROJ
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        activity = proj.get_continuous_activity(recipe_id)
        activity.start()
        success(f"Started continuous activity for recipe '{recipe_id}'")
        hint(f"dku continuous status {recipe_id} -P {project_key}")
    except Exception as e:
        handle_api_error(e)


@app.command()
def stop(
    ctx: typer.Context,
    recipe_id: str = typer.Argument(help="Recipe ID of the continuous activity"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Stop a continuous activity.

    Example:
      dku continuous stop my_streaming_recipe -P PROJ
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        activity = proj.get_continuous_activity(recipe_id)
        activity.stop()
        success(f"Stopped continuous activity for recipe '{recipe_id}'")
    except Exception as e:
        handle_api_error(e)


@app.command()
def status(
    ctx: typer.Context,
    recipe_id: str = typer.Argument(help="Recipe ID of the continuous activity"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Get the status of a continuous activity.

    Example:
      dku continuous status my_streaming_recipe -P PROJ
      dku continuous status my_streaming_recipe -P PROJ
    """
    project_key = resolve_project(project)
    fmt = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        activity = proj.get_continuous_activity(recipe_id)
        st = activity.get_status()

        if fmt == "json":
            render_raw(st, output_format="json")
        else:
            desired = st.get("desiredState", "unknown")
            loop = st.get("mainLoopState", {})
            state = loop.get("state", "unknown")
            info(f"Recipe: {recipe_id}")
            info(f"Desired state: {desired}")
            info(f"Current state: {state}")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)
