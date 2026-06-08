"""Core semantic-model commands."""

# ruff: noqa: F403,F405
from ._common import *


@app.command("list")
def list_semantic_models(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List semantic models in a project."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        models = proj.list_semantic_models()

        data = []
        for m in models:
            data.append(
                {
                    "id": m.get("id", ""),
                    "name": m.get("name", ""),
                }
            )

        render(
            data,
            ["id", "name"],
            output_format=output,
            title=f"Semantic Models ({project_key})",
        )
    except Exception as e:
        handle_api_error(e)


@app.command()
def create(
    ctx: typer.Context,
    name: str = typer.Argument(help="Semantic model name"),
    if_not_exists: bool = typer.Option(
        False, "--if-not-exists", help="Skip if semantic model already exists"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a new semantic model."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        sm = proj.create_semantic_model(name)
        success(f"Created semantic model '{name}' (id: {sm.id})")
    except Exception as e:
        if if_not_exists and is_already_exists_error(e):
            warn(
                f"Semantic model '{name}' already exists in {project_key}, skipping create"
            )
            return
        handle_api_error(e)


@app.command()
def get(
    ctx: typer.Context,
    sm_ref: str = typer.Argument(help="Semantic model ID or name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show semantic model definition."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        sm = resolve_semantic_model(proj, sm_ref)
        definition = sm._get_definition()
        render_raw(definition, output_format=output)
    except Exception as e:
        handle_api_error(e)


@app.command()
def delete(
    ctx: typer.Context,
    sm_ref: str = typer.Argument(help="Semantic model ID or name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip safety guard"),
) -> None:
    """Delete a semantic model."""
    from dku_cli.safety import Tier, guard

    project_key = resolve_project(project)
    guard(
        ctx,
        tier=Tier.DELETE,
        action="semantic_model.delete",
        subject=f"semantic model '{sm_ref}' in {project_key}",
        yes=yes,
        prompt=f"Delete semantic model '{sm_ref}' from {project_key}?",
    )
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        sm = resolve_semantic_model(proj, sm_ref)
        sm.delete()
        success(f"Deleted semantic model '{sm_ref}'")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)
