"""dku llm — list, completion, embeddings, generate-image, rerank."""

from __future__ import annotations

import json

import typer

from dku_cli.errors import exit_with_error, handle_api_error
from dku_cli.helpers import get_client_from_ctx, resolve_project
from dku_cli.output import info, render, resolve_output_format

app = typer.Typer(help="Interact with DSS LLM endpoints.")


@app.command("list")
def list_llms(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    purpose: str = typer.Option(
        "GENERIC_COMPLETION",
        "--purpose",
        help="LLM purpose: GENERIC_COMPLETION, TEXT_EMBEDDING_EXTRACTION, IMAGE_EMBEDDING_EXTRACTION, RERANKING, IMAGE_GENERATION",
    ),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List available LLMs."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        llms = proj.list_llms(purpose=purpose)

        data = []
        for llm in llms:
            data.append(
                {
                    "id": llm.get("id", ""),
                    "type": llm.get("type", ""),
                    "description": llm.get("description", ""),
                }
            )

        render(
            data,
            ["id", "type", "description"],
            output_format=output,
            title=f"LLMs ({project_key})",
        )
        # Hint about other purposes when using default
        if purpose == "GENERIC_COMPLETION" and output != "json":
            info(
                "Showing completion models. For embedding models: dku llm list --purpose TEXT_EMBEDDING_EXTRACTION"
            )
    except Exception as e:
        handle_api_error(e)


@app.command()
def completion(
    ctx: typer.Context,
    llm_id: str = typer.Argument(help="LLM ID"),
    message: str = typer.Argument(help="Message to send"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    system: str | None = typer.Option(
        None, "--system", help="System message to prepend"
    ),
    json_output: bool = typer.Option(
        False, "--json-output", help="Instruct LLM to respond in JSON"
    ),
    json_schema: str | None = typer.Option(
        None,
        "--json-schema",
        help="JSON schema for structured output (string or @file.json)",
    ),
    output: str | None = typer.Option(
        None, "-o", "--output", help="Output format (text or json)"
    ),
) -> None:
    """Send a completion request to an LLM.

    Use --json-output for freeform JSON. Use --json-schema for structured
    output conforming to a specific schema.
    """
    project_key = resolve_project(project)
    output = resolve_output_format(output, allowed=("text", "json"), default="text")
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        llm = proj.get_llm(llm_id)

        # Builder pattern: new_completion().with_message().execute()
        completion_obj = llm.new_completion()

        if system:
            # SDK has no `with_system_message`; system messages use `with_message(role="system")`
            completion_obj.with_message(system, role="system")

        actual_message = message
        if json_schema:
            from dku_cli.helpers import read_json_input

            schema = read_json_input(json_schema)
            completion_obj.with_json_output(schema=schema)
        elif json_output:
            actual_message = f"{message}\n\nRespond in valid JSON format."

        completion_obj.with_message(actual_message)
        result = completion_obj.execute()

        if output == "json":
            detail = {
                "text": result.text,
                "success": result.success,
                "total_usage": result.total_usage,
            }
            print(json.dumps(detail, indent=2, default=str))
        else:
            print(result.text)
    except Exception as e:
        handle_api_error(e)


@app.command()
def embeddings(
    ctx: typer.Context,
    llm_id: str = typer.Argument(help="LLM ID"),
    text: str = typer.Option(..., "--text", "-t", help="Text to embed"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Generate embeddings for a text string."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        embedding_llm_ids = {
            item.get("id", "")
            for item in proj.list_llms(purpose="TEXT_EMBEDDING_EXTRACTION")
        }
        if llm_id not in embedding_llm_ids:
            exit_with_error(
                f"Selected LLM is not available for text embeddings in project '{project_key}'. "
                "Use 'dku llm list --purpose TEXT_EMBEDDING_EXTRACTION' to find a compatible model.",
                code="invalid_llm_purpose",
                details=[f"Requested LLM ID: {llm_id}"],
            )

        llm = proj.get_llm(llm_id)
        emb = llm.new_embeddings()
        emb.add_text(text)
        result = emb.execute()

        print(json.dumps(result.get_embeddings(), indent=2))
    except Exception as e:
        handle_api_error(e)


@app.command("generate-image")
def generate_image(
    ctx: typer.Context,
    llm_id: str = typer.Argument(help="Image generation LLM ID"),
    prompt: str = typer.Option(..., "--prompt", "-p", help="Image generation prompt"),
    negative_prompt: str | None = typer.Option(
        None, "--negative-prompt", help="What to avoid in the image"
    ),
    dest: str | None = typer.Option(
        None, "--dest", "-d", help="Save image to file (default: print base64)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Generate an image using an image generation LLM.

    Example:
      dku llm generate-image "openai:dall-e-3" --prompt "A cat on a surfboard" -P PROJ
      dku llm generate-image IMG_LLM -p "Sunset over mountains" --dest sunset.png -P PROJ
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        llm = proj.get_llm(llm_id)

        query = llm.new_images_generation()
        query.with_prompt(prompt)
        if negative_prompt:
            query.with_negative_prompt(negative_prompt)

        result = query.execute()

        if not result.success:
            exit_with_error(
                "Image generation failed.",
                code="image_gen_failed",
                details=[
                    "The LLM may not support image generation.",
                    f"List image LLMs: dku llm list --purpose IMAGE_GENERATION -P {project_key}",
                ],
            )

        if dest:
            image_bytes = result.first_image(as_type="bytes")
            with open(dest, "wb") as f:
                f.write(image_bytes)
            info(f"Image saved to {dest}")
        else:
            image_b64 = result.first_image(as_type="str")
            print(
                json.dumps(
                    {"success": True, "image_base64": image_b64[:100] + "..."}, indent=2
                )
            )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def rerank(
    ctx: typer.Context,
    llm_id: str = typer.Argument(help="Reranking LLM ID"),
    query: str = typer.Option(..., "--query", "-q", help="Query text"),
    documents: list[str] = typer.Option(
        ..., "--doc", help="Document text (repeat for multiple)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Rerank documents by relevance to a query.

    Example:
      dku llm rerank RERANK_LLM -q "best restaurant" --doc "Pizza place" --doc "Sushi bar" -P PROJ
    """
    project_key = resolve_project(project)
    fmt = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        llm = proj.get_llm(llm_id)

        rerank_query = llm.new_reranking()
        rerank_query.with_query(query)
        for doc in documents:
            rerank_query.with_document(doc)

        result = rerank_query.execute()
        ranked_docs = result.documents

        if fmt == "json":
            json_results = [
                {"rank": i + 1, "index": doc.index, "score": doc.relevance_score}
                for i, doc in enumerate(ranked_docs)
            ]
            print(json.dumps(json_results, indent=2, default=str))
        else:
            data = []
            for i, doc in enumerate(ranked_docs):
                idx = doc.index
                data.append(
                    {
                        "rank": str(i + 1),
                        "score": f"{doc.relevance_score:.4f}",
                        "document": documents[idx] if idx < len(documents) else "",
                    }
                )
            render(
                data,
                ["rank", "score", "document"],
                output_format=fmt,
                title="Reranked Documents",
                headers={"rank": "RANK", "score": "SCORE", "document": "DOCUMENT"},
            )
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)
