"""dku eal — Enterprise Asset Library (governed, reusable prompts).

Instance-scoped (no --project): collections and prompts live on the DSS
instance, not in a project. SDK: DSSClient.get_enterprise_asset_library().
"""

from __future__ import annotations

import typer

from dku_cli.errors import handle_api_error
from dku_cli.helpers import get_client_from_ctx, read_text_input
from dku_cli.output import render, render_raw, resolve_output_format, success

app = typer.Typer(help="Enterprise Asset Library — governed, reusable prompts.")


@app.command("list-collections")
def list_collections(
    ctx: typer.Context,
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List Enterprise Asset Library collections you can read."""
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        eal = client.get_enterprise_asset_library()
        collections = eal.list_collections()
        data = [
            {
                "id": c.get("id", ""),
                "name": c.get("name", ""),
                "description": c.get("description", ""),
            }
            for c in collections
        ]
        render(
            data,
            ["id", "name", "description"],
            output_format=output,
            title="Enterprise Asset Collections",
        )
    except Exception as e:
        handle_api_error(e)


@app.command("list-prompts")
def list_prompts(
    ctx: typer.Context,
    collection: list[str] = typer.Option(
        None,
        "--collection",
        "-c",
        help="Restrict to these collection IDs (repeatable). Default: all readable.",
    ),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List governed prompts across readable collections."""
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        eal = client.get_enterprise_asset_library()
        prompts = eal.list_prompts(restrict_collections=list(collection or []))
        data = [
            {
                "id": p.get("id", ""),
                "name": p.get("name", ""),
                "collection": p.get("collectionId", p.get("collection", "")),
                "description": p.get("description", ""),
                "tags": ",".join(p.get("tags", []) or []),
            }
            for p in prompts
        ]
        render(
            data,
            ["id", "name", "collection", "description", "tags"],
            output_format=output,
            title="Enterprise Prompts",
        )
    except Exception as e:
        handle_api_error(e)


@app.command("get-prompt")
def get_prompt(
    ctx: typer.Context,
    collection_id: str = typer.Argument(help="Collection ID (see list-collections)"),
    prompt_id: str = typer.Argument(help="Prompt ID (see list-prompts)"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show a governed prompt, including its full content."""
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        eal = client.get_enterprise_asset_library()
        prompt = eal.get_collection(collection_id).get_prompt(prompt_id)
        render_raw(prompt.get_raw(), output_format=output)
    except Exception as e:
        handle_api_error(e)


@app.command("create-prompt")
def create_prompt(
    ctx: typer.Context,
    collection_id: str = typer.Argument(help="Collection ID (see list-collections)"),
    name: str = typer.Option(..., "--name", "-n", help="Prompt name"),
    content: str = typer.Option(
        ...,
        "--content",
        help="Prompt content: literal text, @file.txt, or '-' for stdin",
    ),
    description: str | None = typer.Option(
        None, "--description", "-d", help="Prompt description"
    ),
    tags: str | None = typer.Option(None, "--tags", help="Comma-separated tags"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Create a governed prompt in a collection (needs contributor rights)."""
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        eal = client.get_enterprise_asset_library()
        prompt = eal.get_collection(collection_id).create_prompt(
            name=name,
            description=description,
            content=read_text_input(content),
            tags=[t.strip() for t in tags.split(",") if t.strip()] if tags else None,
        )
        if output == "json":
            render_raw(prompt.get_raw(), output_format=output)
        else:
            success(f"Created prompt '{name}' (id={prompt.id}) in {collection_id}")
    except Exception as e:
        handle_api_error(e)


@app.command("delete-prompt")
def delete_prompt(
    ctx: typer.Context,
    collection_id: str = typer.Argument(help="Collection ID"),
    prompt_id: str = typer.Argument(help="Prompt ID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip safety guard"),
) -> None:
    """Delete a governed prompt from a collection."""
    from dku_cli.safety import Tier, guard

    guard(
        ctx,
        tier=Tier.DELETE,
        action="eal.delete_prompt",
        subject=f"enterprise prompt '{prompt_id}' in collection {collection_id}",
        yes=yes,
        prompt=f"Delete enterprise prompt '{prompt_id}' from collection {collection_id}?",
    )
    try:
        client = get_client_from_ctx(ctx)
        eal = client.get_enterprise_asset_library()
        prompt = eal.get_collection(collection_id).get_prompt(prompt_id)
        prompt.delete()
        success(f"Deleted prompt '{prompt_id}' from collection {collection_id}")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)
