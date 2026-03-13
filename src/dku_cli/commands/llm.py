"""dku llm — list, completion, embeddings."""

from __future__ import annotations

import json

import typer

from dku_cli.errors import handle_api_error
from dku_cli.helpers import get_client_from_ctx, resolve_project
from dku_cli.output import render, resolve_output_format

app = typer.Typer(help="Interact with DSS LLM endpoints.")


@app.command("list")
def list_llms(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List available LLMs."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        llms = proj.list_llms()

        data = []
        for llm in llms:
            data.append({
                "id": llm.get("id", ""),
                "type": llm.get("type", ""),
                "description": llm.get("description", ""),
            })

        render(
            data,
            ["id", "type", "description"],
            output_format=output,
            title=f"LLMs ({project_key})",
        )
    except Exception as e:
        handle_api_error(e)


@app.command()
def completion(
    ctx: typer.Context,
    llm_id: str = typer.Argument(help="LLM ID"),
    message: str = typer.Argument(help="Message to send"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    system: str | None = typer.Option(None, "--system", help="System message to prepend"),
    json_output: bool = typer.Option(False, "--json-output", help="Instruct LLM to respond in JSON"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format (text or json)"),
) -> None:
    """Send a completion request to an LLM."""
    project_key = resolve_project(project)
    output = resolve_output_format(output, allowed=("text", "json"), default="text")
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        llm = proj.get_llm(llm_id)

        # Builder pattern: new_completion().with_message().execute()
        completion_obj = llm.new_completion()

        if system:
            completion_obj.with_system_message(system)

        actual_message = message
        if json_output:
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
        llm = proj.get_llm(llm_id)

        emb = llm.new_embeddings()
        emb.with_text(text)
        result = emb.execute()

        print(json.dumps(result.vectors, indent=2))
    except Exception as e:
        handle_api_error(e)
