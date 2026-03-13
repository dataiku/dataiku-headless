"""dku knowledge — list, create, get, build, search, delete."""

from __future__ import annotations

import typer

from dku_cli.errors import handle_api_error
from dku_cli.helpers import get_client_from_ctx, resolve_project
from dku_cli.output import info, render, render_raw, resolve_output_format, success

app = typer.Typer(help="Manage DSS knowledge banks.")


@app.command("list")
def list_knowledge_banks(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List knowledge banks in a project."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        banks = proj.list_knowledge_banks()

        data = []
        for kb in banks:
            data.append({
                "id": kb.get("id", ""),
                "name": kb.get("name", ""),
            })

        render(
            data,
            ["id", "name"],
            output_format=output,
            title=f"Knowledge Banks ({project_key})",
        )
    except Exception as e:
        handle_api_error(e)


@app.command()
def create(
    ctx: typer.Context,
    name: str = typer.Argument(help="Knowledge bank name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a new knowledge bank."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        proj.create_knowledge_bank(name)
        success(f"Created knowledge bank '{name}'")
    except Exception as e:
        handle_api_error(e)


@app.command()
def get(
    ctx: typer.Context,
    kb_id: str = typer.Argument(help="Knowledge bank ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show knowledge bank settings."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        kb = proj.get_knowledge_bank(kb_id)
        settings = kb.get_settings()
        raw = settings.get_raw()
        render_raw(raw, output_format=output)
    except Exception as e:
        handle_api_error(e)


@app.command()
def build(
    ctx: typer.Context,
    kb_id: str = typer.Argument(help="Knowledge bank ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    wait: bool = typer.Option(False, "--wait/--no-wait", help="Wait for build to complete"),
) -> None:
    """Build a knowledge bank."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        kb = proj.get_knowledge_bank(kb_id)
        future = kb.build()

        if wait:
            future.wait_for_result()
            success(f"Knowledge bank '{kb_id}' build completed")
        else:
            success(f"Knowledge bank '{kb_id}' build started")
            info("Use --wait to wait for completion")
    except Exception as e:
        handle_api_error(e)


@app.command()
def search(
    ctx: typer.Context,
    kb_id: str = typer.Argument(help="Knowledge bank ID"),
    query: str = typer.Option(..., "--query", "-q", help="Search query"),
    max_results: int = typer.Option(10, "--max", "-n", help="Maximum number of results"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Search a knowledge bank."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        kb = proj.get_knowledge_bank(kb_id)
        results = kb.search(query, max_documents=max_results)
        render_raw(results, output_format=output)
    except Exception as e:
        handle_api_error(e)


@app.command()
def delete(
    ctx: typer.Context,
    kb_id: str = typer.Argument(help="Knowledge bank ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Delete a knowledge bank."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        kb = proj.get_knowledge_bank(kb_id)
        kb.delete()
        success(f"Deleted knowledge bank '{kb_id}'")
    except Exception as e:
        handle_api_error(e)
