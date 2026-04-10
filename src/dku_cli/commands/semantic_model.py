"""dku semantic-model — list, create, get, delete, versions, get-version, create-version, set-version, set-active-version, distinct-values, update-index."""

from __future__ import annotations

import typer

from dku_cli.errors import exit_with_error, handle_api_error, is_already_exists_error
from dku_cli.helpers import (
    get_client_from_ctx,
    read_json_input,
    resolve_project,
    resolve_semantic_model,
)
from dku_cli.output import (
    info,
    render,
    render_raw,
    resolve_output_format,
    success,
    warn,
)

app = typer.Typer(help="Manage DSS semantic models.")


def _resolve_version_id(sm, version: str | None) -> str:
    """Resolve a version ID: explicit value or fall back to active version."""
    if version:
        return version
    try:
        return sm.get_active_version_id()
    except Exception:
        exit_with_error(
            "No active version set and --version not provided.",
            code="no_active_version",
            details=[
                f"List versions: dku semantic-model versions {sm.semantic_model_id} -P PROJECT",
                f"Set active: dku semantic-model set-active-version {sm.semantic_model_id} VERSION_ID -P PROJECT",
            ],
        )


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
) -> None:
    """Delete a semantic model."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        sm = resolve_semantic_model(proj, sm_ref)
        sm.delete()
        success(f"Deleted semantic model '{sm_ref}'")
    except Exception as e:
        handle_api_error(e)


@app.command()
def versions(
    ctx: typer.Context,
    sm_ref: str = typer.Argument(help="Semantic model ID or name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List versions of a semantic model."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        sm = resolve_semantic_model(proj, sm_ref)
        definition = sm._get_definition()
        active_id = definition.get("activeVersionId", "")

        data = []
        for v in definition.get("versions", []):
            data.append(
                {
                    "id": v.get("id", ""),
                    "active": str(v.get("id", "") == active_id),
                    "description": v.get("description", ""),
                }
            )

        render(
            data,
            ["id", "active", "description"],
            output_format=output,
            title=f"Semantic Model Versions: {sm_ref}",
        )
    except Exception as e:
        handle_api_error(e)


@app.command("get-version")
def get_version(
    ctx: typer.Context,
    sm_ref: str = typer.Argument(help="Semantic model ID or name"),
    version: str | None = typer.Option(
        None, "--version", "-v", help="Version ID (default: active version)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show version settings (entities, relationships, glossary, etc.).

    Defaults to the active version. Use --version to inspect a specific one.
    """
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        sm = resolve_semantic_model(proj, sm_ref)
        version_id = _resolve_version_id(sm, version)
        settings = sm.get_version(version_id).get_settings()
        render_raw(settings.get_raw(), output_format=output)
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("create-version")
def create_version(
    ctx: typer.Context,
    sm_ref: str = typer.Argument(help="Semantic model ID or name"),
    version_id: str = typer.Argument(help="New version ID"),
    duplicate_of: str | None = typer.Option(
        None,
        "--duplicate-of",
        help="Existing version ID to duplicate settings from",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a new version of a semantic model.

    Creates a blank version, or duplicates an existing one with --duplicate-of.
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        sm = resolve_semantic_model(proj, sm_ref)
        version_settings = sm.new_version(version_id, duplicate_of=duplicate_of)
        version_settings.save()
        success(f"Created version '{version_id}' on semantic model '{sm_ref}'")
    except Exception as e:
        handle_api_error(e)


@app.command("set-version")
def set_version(
    ctx: typer.Context,
    sm_ref: str = typer.Argument(help="Semantic model ID or name"),
    definition: str = typer.Option(
        ...,
        "--definition",
        "-d",
        help="Version settings JSON — merges into current. String, @file.json, or '-' for stdin.",
    ),
    version: str | None = typer.Option(
        None, "--version", "-v", help="Version ID (default: active version)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Update a version's settings from JSON.

    Merges the provided JSON into the current version settings (shallow merge).
    Get current settings first: dku semantic-model get-version SM -P PROJ -o json

    Examples:
      dku semantic-model set-version my_sm -d '{"description": "Updated"}' -P PROJ
      dku semantic-model set-version my_sm -d @sm_settings.json --version v2 -P PROJ
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        sm = resolve_semantic_model(proj, sm_ref)
        version_id = _resolve_version_id(sm, version)
        updates = read_json_input(definition)
        settings = sm.get_version(version_id).get_settings()
        settings.get_raw().update(updates)
        settings.save()
        success(f"Updated version '{version_id}' on semantic model '{sm_ref}'")
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("set-active-version")
def set_active_version(
    ctx: typer.Context,
    sm_ref: str = typer.Argument(help="Semantic model ID or name"),
    version_id: str = typer.Argument(help="Version ID to activate"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Set the active version of a semantic model.

    Only the active version is used by the Semantic Model Query agent tool.
    Use 'dku semantic-model versions SM' to see available version IDs.
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        sm = resolve_semantic_model(proj, sm_ref)
        sm.set_active_version_id(version_id)
        success(f"Activated version '{version_id}' on semantic model '{sm_ref}'")
    except Exception as e:
        handle_api_error(e)


@app.command("distinct-values")
def distinct_values(
    ctx: typer.Context,
    sm_ref: str = typer.Argument(help="Semantic model ID or name"),
    version: str | None = typer.Option(
        None, "--version", "-v", help="Version ID (default: active version)"
    ),
    entity: str | None = typer.Option(
        None, "--entity", "-e", help="Entity name (requires --attribute)"
    ),
    attribute: str | None = typer.Option(
        None, "--attribute", "-a", help="Attribute name (requires --entity)"
    ),
    max_values: int = typer.Option(
        1000, "--max", "-n", help="Maximum distinct values to return"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show indexed distinct values for a semantic model version.

    Without --entity/--attribute, shows values for all attributes.
    With both, shows values for a specific entity attribute.
    Run 'dku semantic-model update-index' first to populate the index.
    """
    project_key = resolve_project(project)
    output = resolve_output_format(output)

    if (entity is None) != (attribute is None):
        exit_with_error(
            "Both --entity and --attribute are required together.",
            code="missing_argument",
            details=[
                "For all attributes: dku semantic-model distinct-values SM -P PROJ",
                "For one attribute: dku semantic-model distinct-values SM --entity ENT --attribute ATTR -P PROJ",
            ],
        )

    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        sm = resolve_semantic_model(proj, sm_ref)
        version_id = _resolve_version_id(sm, version)
        ver = sm.get_version(version_id)

        if entity and attribute:
            data = ver.get_basic_distinct_values_for_attribute(
                entity, attribute, max_values=max_values
            )
        else:
            data = ver.get_basic_distinct_values_for_model(max_values=max_values)

        render_raw(data, output_format=output)
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("update-index")
def update_index(
    ctx: typer.Context,
    sm_ref: str = typer.Argument(help="Semantic model ID or name"),
    version: str | None = typer.Option(
        None, "--version", "-v", help="Version ID (default: active version)"
    ),
    wait: bool = typer.Option(
        False, "--wait/--no-wait", help="Wait for indexing to complete"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Trigger distinct values indexing for a semantic model version.

    Indexing scans source datasets to populate distinct values used for
    typo correction and value matching in the Semantic Model Query tool.
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        sm = resolve_semantic_model(proj, sm_ref)
        version_id = _resolve_version_id(sm, version)
        future = sm.get_version(version_id).start_update_distinct_values()

        if wait:
            future.wait_for_result()
            success(
                f"Indexing completed for version '{version_id}' on semantic model '{sm_ref}'"
            )
        else:
            success(
                f"Indexing started for version '{version_id}' on semantic model '{sm_ref}'"
            )
            info("Use --wait to wait for completion")
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)
