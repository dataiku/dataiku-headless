"""dku govern-artifact — list (search), get, create, delete, set-definition."""

from __future__ import annotations

from typing import Optional

import typer

from dku_cli.errors import handle_api_error
from dku_cli.helpers import get_govern_client_from_ctx, read_json_input
from dku_cli.output import error, render, render_raw, resolve_output_format, success

app = typer.Typer(help="Manage Govern artifacts.")


@app.command("list")
def list_artifacts(
    ctx: typer.Context,
    blueprint: Optional[str] = typer.Option(
        None, "--blueprint", "-b", help="Filter by blueprint ID"
    ),
    archived: Optional[bool] = typer.Option(
        None, "--archived/--no-archived", help="Filter by archived status"
    ),
    page_size: int = typer.Option(20, "--page-size", help="Number of results to fetch"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Search and list Govern artifacts."""
    from dataikuapi.govern.artifact_search import (
        GovernArtifactFilterArchivedStatus,
        GovernArtifactFilterBlueprints,
        GovernArtifactSearchQuery,
        GovernArtifactSearchSourceAll,
    )

    output = resolve_output_format(output)
    try:
        govern = get_govern_client_from_ctx(ctx)

        query = GovernArtifactSearchQuery()
        query.set_artifact_search_source(GovernArtifactSearchSourceAll())

        if blueprint:
            query.add_artifact_filter(GovernArtifactFilterBlueprints([blueprint]))
        if archived is not None:
            query.add_artifact_filter(GovernArtifactFilterArchivedStatus(archived))

        req = govern.new_artifact_search_request(query)
        resp = req.fetch_next_batch(page_size=page_size)
        hits = resp.get_response_hits()

        data = []
        for hit in hits:
            raw = hit.get_raw()
            art = raw.get("artifact", raw)
            bp_ver = art.get("blueprintVersionId", {})
            data.append(
                {
                    "id": art.get("id", ""),
                    "name": art.get("name", ""),
                    "blueprint": bp_ver.get("blueprintId", ""),
                    "archived": str(art.get("status", {}).get("archived", False)),
                }
            )

        render(
            data,
            ["id", "name", "blueprint", "archived"],
            output_format=output,
            title="Govern Artifacts",
        )
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def get(
    ctx: typer.Context,
    artifact_id: str = typer.Argument(help="Artifact ID (e.g. ar.5)"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Get an artifact definition."""
    output = resolve_output_format(output)
    try:
        govern = get_govern_client_from_ctx(ctx)
        art = govern.get_artifact(artifact_id)
        defn = art.get_definition()
        render_raw(defn.get_raw(), output_format=output)
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def create(
    ctx: typer.Context,
    definition: str = typer.Option(
        ..., "--definition", help="Artifact JSON (string, @file.json, or - for stdin)"
    ),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Create a new Govern artifact."""
    output = resolve_output_format(output)
    try:
        govern = get_govern_client_from_ctx(ctx)
        artifact_data = read_json_input(definition)
        art = govern.create_artifact(artifact_data)
        success(f"Created artifact '{art.artifact_id}'")
        defn = art.get_definition()
        render_raw(defn.get_raw(), output_format=output)
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def delete(
    ctx: typer.Context,
    artifact_id: str = typer.Argument(help="Artifact ID"),
    confirm: bool = typer.Option(
        False, "--confirm", "--yes", "-y", help="Confirm deletion (required)"
    ),
) -> None:
    """Delete a Govern artifact. Requires --confirm / --yes flag."""
    if not confirm:
        error(
            "Deletion requires --confirm (or --yes / -y) flag. This action is irreversible."
        )
        raise typer.Exit(1)
    try:
        govern = get_govern_client_from_ctx(ctx)
        art = govern.get_artifact(artifact_id)
        art.delete()
        success(f"Deleted artifact '{artifact_id}'")
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("set-definition")
def set_definition(
    ctx: typer.Context,
    artifact_id: str = typer.Argument(help="Artifact ID"),
    definition: str = typer.Option(
        ...,
        "--definition",
        help="New definition JSON (string, @file.json, or - for stdin)",
    ),
) -> None:
    """Update an artifact definition from JSON."""
    try:
        govern = get_govern_client_from_ctx(ctx)
        new_def = read_json_input(definition)
        art = govern.get_artifact(artifact_id)
        defn = art.get_definition()
        # GovernArtifactDefinition stores the raw dict internally and save() PUTs it
        defn.definition = new_def
        defn.save()
        success(f"Updated definition for artifact '{artifact_id}'")
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)
