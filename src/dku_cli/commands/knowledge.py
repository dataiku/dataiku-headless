"""dku knowledge — list, create, get, build, search, delete."""

from __future__ import annotations

import typer

from dku_cli.errors import exit_with_error, handle_api_error, is_already_exists_error
from dku_cli.helpers import get_client_from_ctx, resolve_project
from dku_cli.output import info, render, render_raw, resolve_output_format, success, warn

app = typer.Typer(help="Manage DSS knowledge banks.")


def _is_sleep_page(body: str) -> bool:
    """Check if the response body is a DSS instance sleep/wake page."""
    return (
        "Dataiku instance not found" in body
        or "sleep" in body.lower()
        or body.startswith("<!DOCTYPE html")
        or body.startswith("<html")
    )


_SLEEP_PAGE_MSG = (
    "Knowledge bank settings endpoint returned HTML from the instance sleep/wake page "
    "instead of JSON. Wake the DSS instance in the browser, then retry."
)


def _get_knowledge_bank_raw_settings(client, project_key: str, kb_id: str) -> dict:
    # PRIVATE API: public get_settings() doesn't expose raw JSON needed for display,
    # and can't detect sleep-page HTML. Switch when dataikuapi adds raw settings access.
    response = client._perform_http("GET", f"/projects/{project_key}/knowledge-banks/{kb_id}")
    content_type = response.headers.get("Content-Type", "")

    if "text/html" in content_type:
        body = response.text.strip()
        if _is_sleep_page(body):
            raise RuntimeError(_SLEEP_PAGE_MSG)
        raise RuntimeError("Knowledge bank settings endpoint returned HTML instead of JSON.")

    try:
        return response.json()
    except ValueError as exc:
        body = response.text.strip()
        if _is_sleep_page(body):
            raise RuntimeError(_SLEEP_PAGE_MSG) from exc
        raise


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
    embedding_llm: str | None = typer.Option(
        None,
        "--embedding-llm",
        help="Embedding LLM ID (e.g. openai:conn:text-embedding-3-small). "
             "Find IDs: dku llm list --purpose TEXT_EMBEDDING_EXTRACTION",
    ),
    vector_store_type: str = typer.Option(
        "FAISS", "--vector-store-type", help="Vector store type (FAISS, CHROMA, PINECONE)"
    ),
    if_not_exists: bool = typer.Option(False, "--if-not-exists", help="Skip if knowledge bank already exists"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a new knowledge bank."""
    project_key = resolve_project(project)
    if not embedding_llm:
        exit_with_error(
            "Missing required option --embedding-llm.",
            code="missing_argument",
            details=[
                "Find embedding model IDs: dku llm list --purpose TEXT_EMBEDDING_EXTRACTION -P PROJECT",
                "Example: --embedding-llm openai:connection_name:text-embedding-3-small",
            ],
        )
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        proj.create_knowledge_bank(name, vector_store_type, embedding_llm)
        success(f"Created knowledge bank '{name}'")
    except Exception as e:
        if if_not_exists and is_already_exists_error(e):
            warn(f"Knowledge bank '{name}' already exists in {project_key}, skipping create")
            return
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
        raw = _get_knowledge_bank_raw_settings(client, project_key, kb_id)
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
