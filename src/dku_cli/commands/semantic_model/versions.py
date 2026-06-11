"""Semantic-model version commands."""

# ruff: noqa: F403,F405
from ._common import *


@app.command()
def versions(
    ctx: typer.Context,
    sm_ref: str = typer.Argument(help="Semantic model ID or name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """List versions of a semantic model."""
    project_key = resolve_project(project)
    output = resolve_output_format()
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
) -> None:
    """Show version settings (entities, relationships, glossary, etc.).

    Defaults to the active version. Use --version to inspect a specific one.

    Note: freshly `create-version`'d versions exist in the version list but
    return a 404 here until something is written (DSS lazy-materialises the
    version settings doc on first write). This command surfaces that case with
    a prescriptive next-step instead of a bare "not found".
    """
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        sm = resolve_semantic_model(proj, sm_ref)
        version_id = _resolve_version_id(sm, version)
        try:
            settings = sm.get_version(version_id).get_settings()
        except Exception as fetch_exc:
            msg_lower = str(fetch_exc).lower()
            is_not_found = (
                "not found" in msg_lower
                or "notfoundexception" in msg_lower
                or "does not exist" in msg_lower
                or "404" in msg_lower
            )
            # If the version appears in `list_versions_ids()` we know it was
            # created but is empty — surface a useful hint. Otherwise, fall
            # through to the generic error handler.
            if is_not_found:
                try:
                    known_ids = sm.list_versions_ids()
                except Exception:
                    known_ids = []
                if version_id in known_ids:
                    exit_with_error(
                        f"Version '{version_id}' exists but has no settings yet.",
                        details=[
                            "Newly-created semantic-model versions lazy-materialise",
                            "the settings doc on first write. Add at least one entity",
                            "or glossary term so the version becomes inspectable.",
                            "",
                            "Examples:",
                            f"  dku semantic-model add-entity {sm_ref} \\",
                            "      -n ENTITY_NAME --from-dataset DS \\",
                            f"      --version {version_id} -P {project_key}",
                            f"  dku semantic-model set-version {sm_ref} \\",
                            f"      --version {version_id} -d '{{}}' -P {project_key}",
                        ],
                        status=3,
                    )
            raise
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
    The new version's settings doc is materialised immediately so that
    `dku semantic-model get-version` works without an intermediate write.
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        sm = resolve_semantic_model(proj, sm_ref)
        version_settings = sm.new_version(version_id, duplicate_of=duplicate_of)
        version_settings.save()
        # Best-effort second-touch: some DSS builds leave the version's
        # settings endpoint returning 404 until a downstream write happens.
        # Re-fetch and re-save initialises the doc so `get-version` returns
        # an empty settings dict instead of a confusing not-found error.
        try:
            settings = sm.get_version(version_id).get_settings()
            settings.save()
        except Exception:
            pass
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
    Get current settings first: dku --format json semantic-model get-version SM -P PROJ

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
) -> None:
    """Show indexed distinct values for a semantic model version.

    Without --entity/--attribute, shows values for all attributes.
    With both, shows values for a specific entity attribute.
    Run 'dku semantic-model update-index' first to populate the index.
    """
    project_key = resolve_project(project)
    output = resolve_output_format()

    if (entity is None) != (attribute is None):
        exit_with_error(
            "Both --entity and --attribute are required together.",
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
