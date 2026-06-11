"""dku knowledge — list, create, get, set-definition, build, search, delete."""

from __future__ import annotations

import typer

from dku_cli.errors import exit_with_error, handle_api_error, is_already_exists_error
from dku_cli.helpers import (
    get_client_from_ctx,
    read_json_input,
    resolve_knowledge_bank,
    resolve_project,
)
from dku_cli.output import (
    hint,
    info,
    render,
    render_raw,
    resolve_output_format,
    success,
    warn,
)

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
    response = client._perform_http(
        "GET", f"/projects/{project_key}/knowledge-banks/{kb_id}"
    )
    content_type = response.headers.get("Content-Type", "")

    if "text/html" in content_type:
        body = response.text.strip()
        if _is_sleep_page(body):
            raise RuntimeError(_SLEEP_PAGE_MSG)
        raise RuntimeError(
            "Knowledge bank settings endpoint returned HTML instead of JSON."
        )

    try:
        return response.json()
    except ValueError as exc:
        body = response.text.strip()
        if _is_sleep_page(body):
            raise RuntimeError(_SLEEP_PAGE_MSG) from exc
        raise


def _serialize_search_documents(documents: list) -> list:
    """Convert KB search result documents to JSON-serializable dicts.

    DSSKnowledgeBankSearchResultDocument objects have .text, .score, .metadata
    attributes but are not directly JSON-serializable.
    """
    serialized = []
    for doc in documents:
        if isinstance(doc, dict):
            serialized.append(doc)
        else:
            entry = {}
            for attr in ("text", "score", "metadata", "content"):
                if hasattr(doc, attr):
                    val = getattr(doc, attr)
                    if val is not None:
                        entry[attr] = val
            if not entry:
                entry["content"] = str(doc)
            serialized.append(entry)
    return serialized


@app.command("list")
def list_knowledge_banks(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """List knowledge banks in a project."""
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        banks = proj.list_knowledge_banks()

        data = []
        for kb in banks:
            data.append(
                {
                    "id": kb.get("id", ""),
                    "name": kb.get("name", ""),
                }
            )

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
        "CHROMA",
        "--vector-store-type",
        help="Vector store type (CHROMA, FAISS, PINECONE)",
    ),
    if_not_exists: bool = typer.Option(
        False, "--if-not-exists", help="Skip if knowledge bank already exists"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a new knowledge bank."""
    project_key = resolve_project(project)
    if not embedding_llm:
        exit_with_error(
            "Missing required option --embedding-llm.",
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
        hint(f"dku knowledge get {name} -P {project_key}")
    except Exception as e:
        if if_not_exists and is_already_exists_error(e):
            warn(
                f"Knowledge bank '{name}' already exists in {project_key}, skipping create"
            )
            return
        handle_api_error(e)


@app.command()
def get(
    ctx: typer.Context,
    kb_id: str = typer.Argument(help="Knowledge bank ID or name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Show knowledge bank settings."""
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        kb = resolve_knowledge_bank(proj, kb_id)
        raw = _get_knowledge_bank_raw_settings(client, project_key, kb.id)
        render_raw(raw, output_format=output)
    except Exception as e:
        handle_api_error(e)


@app.command("set-definition")
def set_definition(
    ctx: typer.Context,
    kb_ref: str = typer.Argument(help="Knowledge bank ID or name"),
    definition: str = typer.Option(
        ...,
        "--definition",
        "-d",
        help="Definition JSON — merges into current settings. String, @file.json, or '-' for stdin.",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Update a knowledge bank's definition from JSON.

    Merges the provided JSON into the current settings (shallow merge).
    Get current settings first: dku --format json knowledge get KB -P PROJ

    Examples:
      dku knowledge set-definition my_kb -d '{"vectorStoreType": "CHROMA"}' -P PROJ
      dku knowledge set-definition my_kb -d @kb_settings.json -P PROJ
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        kb = resolve_knowledge_bank(proj, kb_ref)
        updates = read_json_input(definition)
        settings = kb.get_settings()
        settings.get_raw().update(updates)
        settings.save()
        success(f"Updated knowledge bank '{kb_ref}' definition")
    except Exception as e:
        handle_api_error(e)


@app.command()
def build(
    ctx: typer.Context,
    kb_id: str = typer.Argument(help="Knowledge bank ID or name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    wait: bool = typer.Option(
        False, "--wait/--no-wait", help="Wait for build to complete"
    ),
) -> None:
    """Build a knowledge bank."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        kb = resolve_knowledge_bank(proj, kb_id)
        try:
            # kb.build(wait=True) blocks until the job finishes and raises on
            # failure; it returns a DSSJob (no wait_for_result()).
            kb.build(wait=wait)
        except Exception as e:
            if "not found or not buildable" in str(
                e
            ).lower() or "Computable not found" in str(e):
                exit_with_error(
                    f"Knowledge bank '{kb_id}' cannot be built — no data source is configured.",
                    details=[
                        "Knowledge banks require a document source before building.",
                        f"Add one with: dku recipe create-embed RECIPE_NAME --input DS --output-kb {kb_id} --embedding-llm LLM_ID --embed-column COLUMN -P {project_key}",
                        f"Find embedding models with: dku llm list --purpose TEXT_EMBEDDING_EXTRACTION -P {project_key}",
                    ],
                )
            raise

        if wait:
            success(f"Knowledge bank '{kb_id}' build completed")
        else:
            success(f"Knowledge bank '{kb_id}' build started")
            info("Use --wait to wait for completion")
    except Exception as e:
        handle_api_error(e)


@app.command()
def search(
    ctx: typer.Context,
    kb_id: str = typer.Argument(help="Knowledge bank ID or name"),
    query: str = typer.Option(..., "--query", "-q", help="Search query"),
    max_results: int = typer.Option(
        10, "--max", "-n", help="Maximum number of results"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Search a knowledge bank."""
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        kb = resolve_knowledge_bank(proj, kb_id)
        results = kb.search(query, max_documents=max_results)

        # DSSKnowledgeBankSearchResult is not directly JSON-serializable.
        # Extract raw data defensively depending on return type.
        if isinstance(results, dict):
            data = results
        elif hasattr(results, "documents"):
            # Real dataikuapi: DSSKnowledgeBankSearchResult.documents is a list
            # of DSSKnowledgeBankSearchResultDocument objects (also not serializable).
            data = _serialize_search_documents(results.documents)
        elif hasattr(results, "get_raw"):
            data = results.get_raw()
        elif hasattr(results, "raw"):
            data = results.raw
        elif isinstance(results, list):
            data = _serialize_search_documents(results)
        else:
            try:
                data = list(results)
            except TypeError:
                data = str(results)

        render_raw(data, output_format=output)
    except Exception as e:
        handle_api_error(e)


@app.command()
def delete(
    ctx: typer.Context,
    kb_id: str = typer.Argument(help="Knowledge bank ID or name"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip safety guard"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Delete a knowledge bank."""
    from dku_cli.safety import Tier, guard

    project_key = resolve_project(project)
    guard(
        ctx,
        tier=Tier.DELETE,
        action="knowledge.delete",
        subject=f"knowledge bank '{kb_id}' in {project_key}",
        yes=yes,
        prompt=f"Delete knowledge bank '{kb_id}' from {project_key}? All chunks are removed.",
    )
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        kb = resolve_knowledge_bank(proj, kb_id)
        kb.delete()
        success(f"Deleted knowledge bank '{kb_id}'")
    except Exception as e:
        handle_api_error(e)
