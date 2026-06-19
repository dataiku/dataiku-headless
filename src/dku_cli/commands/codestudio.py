"""dku code-studio — list, create, get, delete, status, start, stop, change-owner, templates."""

from __future__ import annotations

import typer

from dku_cli.errors import handle_api_error
from dku_cli.helpers import get_client_from_ctx, resolve_project
from dku_cli.output import info, render, render_raw, resolve_output_format, success

app = typer.Typer(help="Manage DSS Code Studios.")


@app.command("list")
def list_code_studios(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """List Code Studios in a project."""
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        studios = proj.list_code_studios()

        data = []
        for cs in studios:
            data.append(
                {
                    "id": cs.id,
                    "name": cs.name,
                    "owner": cs.owner,
                    "template_id": cs.template_id,
                    "template_label": cs.template_label,
                }
            )

        render(
            data,
            ["id", "name", "owner", "template_id"],
            output_format=output,
            title=f"Code Studios ({project_key})",
        )
    except Exception as e:
        handle_api_error(e, project_key=project_key)


@app.command()
def create(
    ctx: typer.Context,
    name: str = typer.Argument(help="Code Studio name"),
    template: str = typer.Option(
        ...,
        "--template",
        "-t",
        help="Template ID (use 'dku code-studio templates' to list)",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a new Code Studio.

    Use 'dku code-studio templates' to list available templates.
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        cs = proj.create_code_studio(name, template)
        cs_id = getattr(cs, "code_studio_id", getattr(cs, "id", "unknown"))
        success(f"Created Code Studio '{name}' (id={cs_id})")
        # The id is DATA (the create→start chain needs it) — emit it on
        # stdout so `--format ids`/json work instead of stderr-prose regex.
        render(
            [{"id": str(cs_id), "name": name}],
            ["id", "name"],
            output_format=resolve_output_format(),
        )
    except Exception as e:
        handle_api_error(e, project_key=project_key)


@app.command()
def get(
    ctx: typer.Context,
    code_studio_id: str = typer.Argument(help="Code Studio ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Show Code Studio settings."""
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        cs = proj.get_code_studio(code_studio_id)
        settings = cs.get_settings()
        raw = settings.get_raw()
        render_raw(raw, output_format=output)
    except Exception as e:
        handle_api_error(e, project_key=project_key)


@app.command()
def delete(
    ctx: typer.Context,
    code_studio_id: str = typer.Argument(help="Code Studio ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip safety guard"),
) -> None:
    """Delete a Code Studio."""
    from dku_cli.safety import Tier, guard

    project_key = resolve_project(project)
    guard(
        ctx,
        tier=Tier.DELETE,
        action="codestudio.delete",
        subject=f"Code Studio '{code_studio_id}' in {project_key}",
        yes=yes,
        prompt=f"Delete Code Studio '{code_studio_id}' from {project_key}?",
    )
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        cs = proj.get_code_studio(code_studio_id)
        cs.delete()
        success(f"Deleted Code Studio '{code_studio_id}'")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e, project_key=project_key)


@app.command()
def status(
    ctx: typer.Context,
    code_studio_id: str = typer.Argument(help="Code Studio ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Show Code Studio status (STOPPED, STARTING, RUNNING, STOPPING)."""
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        cs = proj.get_code_studio(code_studio_id)
        st = cs.get_status()
        render_raw(st.get_raw(), output_format=output)
    except Exception as e:
        handle_api_error(e, project_key=project_key)


@app.command()
def start(
    ctx: typer.Context,
    code_studio_id: str = typer.Argument(help="Code Studio ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    wait: bool = typer.Option(
        True, "--wait/--no-wait", help="Wait for Code Studio to start"
    ),
) -> None:
    """Start (or restart) a Code Studio."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        cs = proj.get_code_studio(code_studio_id)
        future = cs.restart()

        if wait:
            future.wait_for_result()
            success(f"Code Studio '{code_studio_id}' started")
        else:
            success(f"Code Studio '{code_studio_id}' start initiated")
            info("Check status with: dku code-studio status " + code_studio_id)
    except Exception as e:
        handle_api_error(e, project_key=project_key)


@app.command()
def stop(
    ctx: typer.Context,
    code_studio_id: str = typer.Argument(help="Code Studio ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    wait: bool = typer.Option(
        True, "--wait/--no-wait", help="Wait for Code Studio to stop"
    ),
) -> None:
    """Stop a Code Studio."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        cs = proj.get_code_studio(code_studio_id)
        future = cs.stop()

        if wait:
            future.wait_for_result()
            success(f"Code Studio '{code_studio_id}' stopped")
        else:
            success(f"Code Studio '{code_studio_id}' stop initiated")
            info("Check status with: dku code-studio status " + code_studio_id)
    except Exception as e:
        handle_api_error(e, project_key=project_key)


@app.command("change-owner")
def change_owner(
    ctx: typer.Context,
    code_studio_id: str = typer.Argument(help="Code Studio ID"),
    owner: str = typer.Option(..., "--owner", help="New owner login"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Change the owner of a Code Studio."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        cs = proj.get_code_studio(code_studio_id)
        cs.change_owner(owner)
        success(f"Changed owner of Code Studio '{code_studio_id}' to '{owner}'")
    except Exception as e:
        handle_api_error(e, project_key=project_key)


@app.command()
def templates(
    ctx: typer.Context,
) -> None:
    """List available Code Studio templates (instance-level, no project required)."""
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        tpls = client.list_code_studio_templates()

        data = []
        for t in tpls:
            data.append(
                {
                    "id": t.id,
                    "label": t.label,
                }
            )

        render(
            data,
            ["id", "label"],
            output_format=output,
            title="Code Studio Templates",
        )
    except Exception as e:
        handle_api_error(e)
