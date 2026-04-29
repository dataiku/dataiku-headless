"""dku rag — list, create, get, delete, get-definition, set-definition for Retrieval Augmented LLMs."""

from __future__ import annotations

import typer

from dku_cli.errors import handle_api_error
from dku_cli.helpers import get_client_from_ctx, read_json_input, resolve_project
from dku_cli.output import (
    info,
    render,
    render_raw,
    resolve_output_format,
    success,
)

app = typer.Typer(help="Manage Retrieval Augmented LLMs (RAG).")


@app.command("list")
def list_rags(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List RAG LLMs in a project."""
    project_key = resolve_project(project)
    fmt = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        items = proj.list_retrieval_augmented_llms()

        data = []
        for item in items:
            # dataikuapi declares .name but the API may not return it
            try:
                name = item.name
            except (KeyError, AttributeError):
                name = ""
            data.append(
                {
                    "id": item.id,
                    "name": name,
                }
            )

        if fmt == "json":
            render_raw(data, output_format="json")
        else:
            if not data:
                info(f"No RAG LLMs in {project_key}.")
                return
            render(
                data,
                ["id", "name"],
                output_format=fmt,
                title=f"RAG LLMs ({project_key})",
                headers={"id": "ID", "name": "NAME"},
            )
    except Exception as e:
        handle_api_error(e)


@app.command()
def create(
    ctx: typer.Context,
    name: str = typer.Argument(help="Name for the new RAG LLM"),
    kb_ref: str = typer.Option(
        ...,
        "--knowledge-bank",
        "--kb",
        help="Knowledge bank ID to use",
    ),
    llm_id: str = typer.Option(
        ...,
        "--llm",
        help="LLM ID to use for RAG (e.g. openai:gpt-4o)",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Create a RAG LLM that combines a knowledge bank with an LLM.

    This is the final step in the RAG pipeline:
      1. Create a knowledge bank: dku knowledge create KB_NAME -P PROJ
      2. Build embeddings: dku recipe create-embed ... && dku dataset build ...
      3. Create the RAG LLM: dku rag create MY_RAG --kb KB_ID --llm openai:gpt-4o -P PROJ
      4. Attach to an agent or use directly

    Example:
      dku rag create "Customer Support RAG" --kb kb_docs --llm openai:gpt-4o -P PROJ
    """
    project_key = resolve_project(project)
    fmt = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        rag = proj.create_retrieval_augmented_llm(name, kb_ref, llm_id)

        if fmt == "json":
            render_raw(
                {"id": rag.id, "name": name, "project": project_key},
                output_format="json",
            )
        else:
            success(f"Created RAG LLM '{name}' (ID: {rag.id}) in {project_key}")
            info(
                f"Use as LLM: retrieval-augmented-llm:{rag.id}\n"
                f"Get settings: dku rag get-definition {rag.id} -P {project_key}"
            )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def get(
    ctx: typer.Context,
    rag_id: str = typer.Argument(help="RAG LLM ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show RAG LLM details."""
    project_key = resolve_project(project)
    fmt = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        rag = proj.get_retrieval_augmented_llm(rag_id)
        settings = rag.get_settings()
        raw = settings.get_raw()

        if fmt == "json":
            render_raw(raw, output_format="json")
        else:
            # RAG settings are nested: versions[activeVersion].ragllmSettings
            active_ver = raw.get("activeVersion")
            rag_settings = {}
            for v in raw.get("versions", []):
                if v.get("versionId") == active_ver:
                    rag_settings = v.get("ragllmSettings", {})
                    break

            data = [
                {"field": "ID", "value": raw.get("id", rag_id)},
                {"field": "Name", "value": raw.get("name", "(unnamed)")},
                {"field": "LLM ID", "value": rag_settings.get("llmId", "")},
                {
                    "field": "KB Ref",
                    "value": rag_settings.get("kbRef", raw.get("knowledgeBankRef", "")),
                },
                {
                    "field": "Active Version",
                    "value": active_ver or "(none)",
                },
            ]
            render(
                data,
                ["field", "value"],
                output_format=fmt,
                title=f"RAG LLM: {rag_id}",
            )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def delete(
    ctx: typer.Context,
    rag_id: str = typer.Argument(help="RAG LLM ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Delete a RAG LLM."""
    from dku_cli.safety import Tier, guard

    project_key = resolve_project(project)
    guard(
        ctx,
        tier=Tier.DELETE,
        action="rag.delete",
        subject=f"RAG LLM '{rag_id}' in {project_key}",
        yes=yes,
        prompt=f"Delete RAG LLM '{rag_id}' from {project_key}?",
    )
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        rag = proj.get_retrieval_augmented_llm(rag_id)
        rag.delete()
        success(f"Deleted RAG LLM '{rag_id}' from {project_key}")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("get-definition")
def get_definition(
    ctx: typer.Context,
    rag_id: str = typer.Argument(help="RAG LLM ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Get the full definition of a RAG LLM as JSON."""
    project_key = resolve_project(project)
    output = resolve_output_format(output, allowed=("json",), default="json")
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        rag = proj.get_retrieval_augmented_llm(rag_id)
        settings = rag.get_settings()
        render_raw(settings.get_raw(), output_format=output)
    except Exception as e:
        handle_api_error(e)


@app.command("set-definition")
def set_definition(
    ctx: typer.Context,
    rag_id: str = typer.Argument(help="RAG LLM ID"),
    definition: str = typer.Option(
        ...,
        "--definition",
        "-d",
        help="Definition JSON (string, @file.json, or '-' for stdin)",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Set the full definition of a RAG LLM from JSON."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        rag = proj.get_retrieval_augmented_llm(rag_id)
        settings = rag.get_settings()
        new_def = read_json_input(definition)
        # Merge into settings object
        settings._settings.update(new_def)
        settings.save()
        success(f"Updated RAG LLM '{rag_id}' definition")
    except Exception as e:
        handle_api_error(e)
