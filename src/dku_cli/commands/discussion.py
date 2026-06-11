"""dku discussion — list, get, create, reply on DSS object discussions."""

from __future__ import annotations

import typer

from dku_cli.errors import exit_with_error, handle_api_error
from dku_cli.helpers import get_client_from_ctx, resolve_project
from dku_cli.output import render, render_raw, resolve_output_format, success

app = typer.Typer(help="Manage discussions on DSS objects.")

_OBJECT_RESOLVERS = {
    "dataset": lambda proj, name: proj.get_dataset(name),
    "recipe": lambda proj, name: proj.get_recipe(name),
    "scenario": lambda proj, name: proj.get_scenario(name),
    "model": lambda proj, name: proj.get_saved_model(name),
    "dashboard": lambda proj, name: proj.get_dashboard(name),
    "insight": lambda proj, name: proj.get_insight(name),
}


def _resolve_object(proj, obj_type: str, obj_name: str):
    """Resolve a DSS object by type and name/ID."""
    resolver = _OBJECT_RESOLVERS.get(obj_type)
    if not resolver:
        exit_with_error(
            f"Unknown object type '{obj_type}'",
            details=[f"Valid types: {', '.join(_OBJECT_RESOLVERS.keys())}"],
        )
    return resolver(proj, obj_name)


@app.command("list")
def list_discussions(
    ctx: typer.Context,
    obj_type: str = typer.Option(
        ...,
        "--type",
        "-t",
        help="Object type: dataset, recipe, scenario, model, dashboard, insight",
    ),
    name: str = typer.Option(..., "--name", "-n", help="Object name or ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """List discussions on a DSS object."""
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        obj = _resolve_object(proj, obj_type, name)
        discussions = obj.get_object_discussions().list_discussions()

        data = []
        for d in discussions:
            meta = d.get_metadata()
            data.append(
                {
                    "id": meta.get("id", ""),
                    "topic": meta.get("topic", ""),
                }
            )

        render(
            data,
            ["id", "topic"],
            output_format=output,
            title=f"Discussions on {obj_type} '{name}'",
        )
    except Exception as e:
        handle_api_error(e)


@app.command()
def get(
    ctx: typer.Context,
    discussion_id: str = typer.Argument(help="Discussion ID"),
    obj_type: str = typer.Option(
        ...,
        "--type",
        "-t",
        help="Object type: dataset, recipe, scenario, model, dashboard, insight",
    ),
    name: str = typer.Option(..., "--name", "-n", help="Object name or ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Get a specific discussion with its replies."""
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        obj = _resolve_object(proj, obj_type, name)
        disc = obj.get_object_discussions().get_discussion(discussion_id)
        meta = disc.get_metadata()
        replies = disc.get_replies()

        result = {
            "id": meta.get("id", ""),
            "topic": meta.get("topic", ""),
            "replies": [
                {
                    "author": r.get_author(),
                    "text": r.get_text(),
                }
                for r in replies
            ],
        }
        render_raw(result, output_format=output)
    except Exception as e:
        handle_api_error(e)


@app.command()
def create(
    ctx: typer.Context,
    obj_type: str = typer.Option(
        ...,
        "--type",
        "-t",
        help="Object type: dataset, recipe, scenario, model, dashboard, insight",
    ),
    name: str = typer.Option(..., "--name", "-n", help="Object name or ID"),
    topic: str = typer.Option(..., "--topic", help="Discussion topic"),
    message: str = typer.Option(..., "--message", "-m", help="Initial message"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a new discussion on a DSS object."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        obj = _resolve_object(proj, obj_type, name)
        obj.get_object_discussions().create_discussion(topic, message)
        success(f"Created discussion '{topic}' on {obj_type} '{name}'")
    except Exception as e:
        handle_api_error(e)


@app.command()
def reply(
    ctx: typer.Context,
    discussion_id: str = typer.Argument(help="Discussion ID"),
    obj_type: str = typer.Option(
        ...,
        "--type",
        "-t",
        help="Object type: dataset, recipe, scenario, model, dashboard, insight",
    ),
    name: str = typer.Option(..., "--name", "-n", help="Object name or ID"),
    message: str = typer.Option(..., "--message", "-m", help="Reply message"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Reply to a discussion."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        obj = _resolve_object(proj, obj_type, name)
        disc = obj.get_object_discussions().get_discussion(discussion_id)
        disc.add_reply(message)
        success(f"Replied to discussion '{discussion_id}' on {obj_type} '{name}'")
    except Exception as e:
        handle_api_error(e)
