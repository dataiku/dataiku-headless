"""dku semantic-model — list, create, get, delete, versions, get-version, create-version, set-version, set-active-version, distinct-values, update-index, add-entity, remove-entity, add-relationship, remove-relationship, add-glossary-term, remove-glossary-term, list-entities, list-relationships, list-glossary, add-metric, remove-metric, list-metrics, add-filter, remove-filter, list-filters, set-manual-values, add-golden-query, remove-golden-query, list-golden-queries."""

from __future__ import annotations

import uuid

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


def _default_attribute(column_name: str, dss_type: str, description: str = "") -> dict:
    """Build an attribute dict with DSS defaults from a dataset column."""
    attr = {
        "name": column_name,
        "dssType": dss_type,
        "type": "COLUMN",
        "column": column_name,
        "distinctValuesHandlingMode": "NONE",
        "manualValues": [],
        "indexDistinctValues": False,
        "resolveInUserRequests": False,
        "sqlGenerationConfig": {},
    }
    if description:
        attr["description"] = description
    return attr


def _split_csv(value: str | None) -> list[str]:
    """Parse a comma-separated string into a trimmed list (empty string -> [])."""
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    """Remove duplicates while preserving first-seen order."""
    seen: set[str] = set()
    out: list[str] = []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _require_identifier(value: str, field_label: str) -> str:
    """Reject empty / whitespace-only identifiers. Returns stripped value."""
    stripped = (value or "").strip()
    if not stripped:
        exit_with_error(
            f"{field_label} cannot be empty or whitespace.",
            code="invalid_argument",
            details=[
                f"Provide a non-blank {field_label.lower()}.",
            ],
        )
    return stripped


def _validate_columns_in_schema(
    columns: list[str],
    schema_cols: list[dict],
    flag_name: str,
    dataset: str,
) -> None:
    """Exit with error if any referenced column is missing from the dataset schema."""
    schema_names = {c.get("name") for c in schema_cols}
    missing = [c for c in columns if c not in schema_names]
    if missing:
        exit_with_error(
            f"{flag_name} references column(s) not in dataset '{dataset}': {', '.join(missing)}",
            code="invalid_argument",
            details=[
                f"Available columns: {', '.join(sorted(schema_names)) if schema_names else '(none)'}",
                f"Check schema: dku dataset schema {dataset} -o json",
                "Column names are case-sensitive.",
            ],
        )


def _load_version_settings(sm, version_id: str):
    """Return (settings_obj, raw_dict) for the given SM version.

    settings_obj.save() persists changes made to raw_dict in-place.
    """
    settings = sm.get_version(version_id).get_settings()
    return settings, settings.get_raw()


def _find_entity(raw: dict, entity_name: str) -> dict:
    """Find an entity dict by name, or exit with prescriptive error."""
    entities = raw.get("entities", [])
    for e in entities:
        if e.get("name") == entity_name:
            return e
    exit_with_error(
        f"Entity '{entity_name}' not found on version.",
        code="not_found",
        details=[
            "Available entities: "
            + (", ".join(e.get("name", "") for e in entities) or "(none)"),
        ],
    )


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
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip safety guard"),
) -> None:
    """Delete a semantic model."""
    from dku_cli.safety import Tier, guard

    project_key = resolve_project(project)
    guard(
        ctx,
        tier=Tier.DELETE,
        action="semantic_model.delete",
        subject=f"semantic model '{sm_ref}' in {project_key}",
        yes=yes,
        prompt=f"Delete semantic model '{sm_ref}' from {project_key}?",
    )
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        sm = resolve_semantic_model(proj, sm_ref)
        sm.delete()
        success(f"Deleted semantic model '{sm_ref}'")
    except typer.Exit:
        raise
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


@app.command("add-entity")
def add_entity(
    ctx: typer.Context,
    sm_ref: str = typer.Argument(help="Semantic model ID or name"),
    name: str = typer.Option(
        None,
        "--name",
        "-n",
        help="Entity name (defaults to --from-dataset value lowercased)",
    ),
    from_dataset: str = typer.Option(
        None,
        "--from-dataset",
        help="Auto-generate attributes from this dataset's schema",
    ),
    description: str = typer.Option("", "--description", help="Entity description"),
    tags: str = typer.Option(None, "--tags", help="Comma-separated tags"),
    pk: str = typer.Option(
        None,
        "--pk",
        help="Primary key column(s), comma-separated (default: first column of dataset)",
    ),
    index_values: str = typer.Option(
        None,
        "--index-values",
        help="Columns to enable distinct-values indexing on (comma-separated)",
    ),
    resolve_values: str = typer.Option(
        None,
        "--resolve-values",
        help="Columns to enable fuzzy/semantic value resolution on (comma-separated). Defaults to --index-values if omitted.",
    ),
    version: str | None = typer.Option(
        None, "--version", "-v", help="Version ID (default: active version)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    if_not_exists: bool = typer.Option(
        False, "--if-not-exists", help="Skip if entity with same name already exists"
    ),
) -> None:
    """Add an entity to a semantic model version.

    Auto-generates attribute definitions from a dataset schema via --from-dataset.
    Columns in --index-values get indexDistinctValues=true and resolveInUserRequests=true.

    Example:
      dku semantic-model add-entity MyModel --from-dataset Customers \\
          --pk CustomerID --index-values Name,RiskTolerance -P PROJ
    """
    if not from_dataset:
        exit_with_error(
            "--from-dataset is required (no manual-entity path yet).",
            code="missing_argument",
            details=[
                "Example: dku semantic-model add-entity SM --from-dataset Customers --pk CustomerID -P PROJ",
                "For manual JSON, read current version, edit with jq, then: dku semantic-model set-version SM --version VID --definition @file.json",
            ],
        )

    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        sm = resolve_semantic_model(proj, sm_ref)
        version_id = _resolve_version_id(sm, version)

        # Pull schema from dataset
        try:
            ds = proj.get_dataset(from_dataset)
            ds_def = ds.get_definition()
        except Exception as e:
            exit_with_error(
                f"Could not read dataset '{from_dataset}' in project '{project_key}'.",
                code="dataset_not_found",
                details=[
                    f"Original error: {e}",
                    f"List datasets: dku dataset list -P {project_key}",
                ],
            )
        columns = ds_def.get("schema", {}).get("columns", [])
        if not columns:
            exit_with_error(
                f"Dataset '{from_dataset}' has no schema columns — nothing to map.",
                code="empty_schema",
                details=[
                    f"Check schema: dku dataset schema {from_dataset} -P {project_key}",
                    "Datasets without a defined schema can't be used as entity sources.",
                ],
            )

        entity_name = (name or "").strip() or from_dataset.lower()
        pk_cols = _dedupe_preserve_order(_split_csv(pk)) or [columns[0]["name"]]
        index_cols_list = _dedupe_preserve_order(_split_csv(index_values))
        resolve_cols_list = (
            _dedupe_preserve_order(_split_csv(resolve_values))
            if resolve_values is not None
            else index_cols_list
        )

        _validate_columns_in_schema(pk_cols, columns, "--pk", from_dataset)
        _validate_columns_in_schema(
            index_cols_list, columns, "--index-values", from_dataset
        )
        _validate_columns_in_schema(
            resolve_cols_list, columns, "--resolve-values", from_dataset
        )

        index_cols = set(index_cols_list)
        resolve_cols = set(resolve_cols_list)

        attrs = []
        for c in columns:
            a = _default_attribute(
                c["name"], c.get("type", "string"), c.get("description", "")
            )
            if c["name"] in index_cols:
                a["indexDistinctValues"] = True
            if c["name"] in resolve_cols:
                a["resolveInUserRequests"] = True
            attrs.append(a)

        entity = {
            "name": entity_name,
            "description": description,
            "tags": _split_csv(tags),
            "type": "DATASET",
            "datasetRef": f"{project_key}.{from_dataset}",
            "metrics": [],
            "filters": [],
            "primaryKey": {"attributes": pk_cols},
            "foreignKeys": [],
            "attributes": attrs,
        }

        settings, raw = _load_version_settings(sm, version_id)
        existing = [e.get("name") for e in raw.get("entities", [])]
        if entity_name in existing:
            if if_not_exists:
                warn(
                    f"Entity '{entity_name}' already exists on version '{version_id}', skipping."
                )
                return
            exit_with_error(
                f"Entity '{entity_name}' already exists on version '{version_id}'.",
                code="already_exists",
                details=[
                    f"Remove first: dku semantic-model remove-entity {sm_ref} {entity_name} --version {version_id} -P {project_key}",
                    "Or pass --if-not-exists to skip.",
                ],
            )

        raw.setdefault("entities", []).append(entity)
        settings.save()
        success(
            f"Added entity '{entity_name}' ({len(attrs)} attributes, PK {pk_cols}) to version '{version_id}' on '{sm_ref}'"
        )
        info(
            "Run 'dku semantic-model update-index {} --wait -P {}' to populate distinct values.".format(
                sm_ref, project_key
            )
        )
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("remove-entity")
def remove_entity(
    ctx: typer.Context,
    sm_ref: str = typer.Argument(help="Semantic model ID or name"),
    entity_name: str = typer.Argument(help="Entity name to remove"),
    version: str | None = typer.Option(
        None, "--version", "-v", help="Version ID (default: active version)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Remove an entity from a semantic model version.

    Also removes any relationships that reference this entity.
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        sm = resolve_semantic_model(proj, sm_ref)
        version_id = _resolve_version_id(sm, version)
        settings, raw = _load_version_settings(sm, version_id)

        entities = raw.get("entities", [])
        new_entities = [e for e in entities if e.get("name") != entity_name]
        if len(new_entities) == len(entities):
            exit_with_error(
                f"Entity '{entity_name}' not found on version '{version_id}'.",
                code="not_found",
                details=[
                    "Available entities: "
                    + ", ".join(e.get("name", "") for e in entities)
                    if entities
                    else "No entities defined on this version.",
                ],
            )

        relationships = raw.get("relationships", [])
        new_rels = [
            r
            for r in relationships
            if r.get("firstEntity") != entity_name
            and r.get("secondEntity") != entity_name
        ]
        removed_rels = len(relationships) - len(new_rels)

        raw["entities"] = new_entities
        raw["relationships"] = new_rels
        settings.save()
        msg = (
            f"Removed entity '{entity_name}' from version '{version_id}' on '{sm_ref}'"
        )
        if removed_rels:
            msg += f" (also removed {removed_rels} relationship(s) referencing it)"
        success(msg)
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("add-relationship")
def add_relationship(
    ctx: typer.Context,
    sm_ref: str = typer.Argument(help="Semantic model ID or name"),
    first_entity: str = typer.Option(
        ..., "--from", "-f", help="First entity name (left side of join)"
    ),
    second_entity: str = typer.Option(
        ..., "--to", "-t", help="Second entity name (right side of join)"
    ),
    on: str = typer.Option(
        None,
        "--on",
        help="Join columns (comma-separated). Builds 'left.col = right.col [AND ...]'. Mutually exclusive with --expression.",
    ),
    expression: str = typer.Option(
        None,
        "--expression",
        "-e",
        help="Custom pseudoSQL join predicate using left/right aliases. Mutually exclusive with --on.",
    ),
    version: str | None = typer.Option(
        None, "--version", "-v", help="Version ID (default: active version)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    if_not_exists: bool = typer.Option(
        False,
        "--if-not-exists",
        help="Skip if a relationship between these entities already exists",
    ),
) -> None:
    """Add a relationship between two entities.

    Use --on COL[,COL2] for simple equi-joins, or --expression for custom predicates.

    Example:
      dku semantic-model add-relationship MyModel --from customer --to orders \\
          --on CustomerID -P PROJ
      dku semantic-model add-relationship MyModel --from a --to b \\
          --expression "LOWER(left.email) = LOWER(right.email)" -P PROJ
    """
    if bool(on) == bool(expression):
        exit_with_error(
            "Exactly one of --on or --expression is required.",
            code="invalid_argument",
            details=[
                "Simple: --on CustomerID",
                "Composite: --on ACCOUNT_SK,MONTH",
                'Custom: --expression "LOWER(left.email) = LOWER(right.email)"',
            ],
        )

    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        sm = resolve_semantic_model(proj, sm_ref)
        version_id = _resolve_version_id(sm, version)
        settings, raw = _load_version_settings(sm, version_id)

        entity_names = {e.get("name") for e in raw.get("entities", [])}
        missing = [
            ent for ent in (first_entity, second_entity) if ent not in entity_names
        ]
        if missing:
            exit_with_error(
                f"Entity not found on version '{version_id}': {', '.join(missing)}",
                code="not_found",
                details=[
                    "Available entities: "
                    + (", ".join(sorted(entity_names)) if entity_names else "(none)"),
                    "Add with: dku semantic-model add-entity SM --from-dataset DS -P PROJ",
                ],
            )

        if on:
            cols = _dedupe_preserve_order(_split_csv(on))
            if not cols:
                exit_with_error(
                    "--on produced no valid join columns (empty or whitespace only).",
                    code="invalid_argument",
                    details=[
                        "Simple: --on CustomerID",
                        "Composite: --on ACCOUNT_SK,MONTH",
                    ],
                )
            pseudo_sql = " AND ".join(f"left.{c} = right.{c}" for c in cols)
        else:
            pseudo_sql = (expression or "").strip()
            if not pseudo_sql:
                exit_with_error(
                    "--expression cannot be empty or whitespace.",
                    code="invalid_argument",
                    details=[
                        'Example: --expression "LOWER(left.email) = LOWER(right.email)"'
                    ],
                )

        relationships = raw.setdefault("relationships", [])
        for r in relationships:
            pair = (r.get("firstEntity"), r.get("secondEntity"))
            if pair == (first_entity, second_entity) or pair == (
                second_entity,
                first_entity,
            ):
                if if_not_exists:
                    warn(
                        f"Relationship {first_entity} <-> {second_entity} already exists, skipping."
                    )
                    return
                exit_with_error(
                    f"Relationship between '{first_entity}' and '{second_entity}' already exists on version '{version_id}'.",
                    code="already_exists",
                    details=[
                        f"Existing predicate: {r.get('pseudoSQLExpression')}",
                        f"Remove first: dku semantic-model remove-relationship {sm_ref} --from {first_entity} --to {second_entity} -P {project_key}",
                        "Or pass --if-not-exists to skip.",
                    ],
                )

        relationships.append(
            {
                "firstEntity": first_entity,
                "secondEntity": second_entity,
                "pseudoSQLExpression": pseudo_sql,
            }
        )
        settings.save()
        success(
            f"Added relationship {first_entity} <-> {second_entity} ({pseudo_sql}) to version '{version_id}' on '{sm_ref}'"
        )
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("remove-relationship")
def remove_relationship(
    ctx: typer.Context,
    sm_ref: str = typer.Argument(help="Semantic model ID or name"),
    first_entity: str = typer.Option(..., "--from", "-f", help="First entity name"),
    second_entity: str = typer.Option(..., "--to", "-t", help="Second entity name"),
    version: str | None = typer.Option(
        None, "--version", "-v", help="Version ID (default: active version)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Remove a relationship between two entities (matches either order)."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        sm = resolve_semantic_model(proj, sm_ref)
        version_id = _resolve_version_id(sm, version)
        settings, raw = _load_version_settings(sm, version_id)

        relationships = raw.get("relationships", [])

        def _matches(r: dict) -> bool:
            pair = (r.get("firstEntity"), r.get("secondEntity"))
            return pair == (first_entity, second_entity) or pair == (
                second_entity,
                first_entity,
            )

        kept = [r for r in relationships if not _matches(r)]
        removed = len(relationships) - len(kept)
        if removed == 0:
            exit_with_error(
                f"No relationship found between '{first_entity}' and '{second_entity}' on version '{version_id}'.",
                code="not_found",
                details=[
                    "List relationships: dku semantic-model list-relationships "
                    f"{sm_ref} -P {project_key}",
                ],
            )

        raw["relationships"] = kept
        settings.save()
        success(
            f"Removed {removed} relationship(s) between '{first_entity}' and '{second_entity}' on version '{version_id}'"
        )
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("add-glossary-term")
def add_glossary_term(
    ctx: typer.Context,
    sm_ref: str = typer.Argument(help="Semantic model ID or name"),
    term: str = typer.Option(..., "--term", help="Glossary term"),
    description: str = typer.Option("", "--description", help="Definition of the term"),
    synonyms: str = typer.Option(None, "--synonyms", help="Comma-separated synonyms"),
    version: str | None = typer.Option(
        None, "--version", "-v", help="Version ID (default: active version)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    if_not_exists: bool = typer.Option(
        False, "--if-not-exists", help="Skip if a term with the same label exists"
    ),
) -> None:
    """Add a glossary term (auto-generates UUID)."""
    project_key = resolve_project(project)
    term = _require_identifier(term, "Glossary term")
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        sm = resolve_semantic_model(proj, sm_ref)
        version_id = _resolve_version_id(sm, version)
        settings, raw = _load_version_settings(sm, version_id)

        terms = raw.setdefault("glossaryTerms", [])
        if any(t.get("term") == term for t in terms):
            if if_not_exists:
                warn(f"Glossary term '{term}' already exists, skipping.")
                return
            exit_with_error(
                f"Glossary term '{term}' already exists on version '{version_id}'.",
                code="already_exists",
                details=[
                    f"Remove first: dku semantic-model remove-glossary-term {sm_ref} --term '{term}' -P {project_key}",
                    "Or pass --if-not-exists to skip.",
                ],
            )

        terms.append(
            {
                "id": str(uuid.uuid4()),
                "term": term,
                "description": description,
                "source": "MANUAL",
                "userModified": True,
                "synonyms": _split_csv(synonyms),
                "created": {},
                "privateEditorData": {},
            }
        )
        settings.save()
        success(f"Added glossary term '{term}' to version '{version_id}' on '{sm_ref}'")
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("remove-glossary-term")
def remove_glossary_term(
    ctx: typer.Context,
    sm_ref: str = typer.Argument(help="Semantic model ID or name"),
    term: str = typer.Option(..., "--term", help="Glossary term to remove"),
    version: str | None = typer.Option(
        None, "--version", "-v", help="Version ID (default: active version)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Remove a glossary term by its label."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        sm = resolve_semantic_model(proj, sm_ref)
        version_id = _resolve_version_id(sm, version)
        settings, raw = _load_version_settings(sm, version_id)

        terms = raw.get("glossaryTerms", [])
        kept = [t for t in terms if t.get("term") != term]
        if len(kept) == len(terms):
            exit_with_error(
                f"Glossary term '{term}' not found on version '{version_id}'.",
                code="not_found",
                details=[
                    f"List terms: dku semantic-model list-glossary {sm_ref} -P {project_key}",
                ],
            )
        raw["glossaryTerms"] = kept
        settings.save()
        success(
            f"Removed glossary term '{term}' from version '{version_id}' on '{sm_ref}'"
        )
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("list-entities")
def list_entities(
    ctx: typer.Context,
    sm_ref: str = typer.Argument(help="Semantic model ID or name"),
    version: str | None = typer.Option(
        None, "--version", "-v", help="Version ID (default: active version)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List entities in a semantic model version (name, dataset, attribute count, PK)."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        sm = resolve_semantic_model(proj, sm_ref)
        version_id = _resolve_version_id(sm, version)
        _, raw = _load_version_settings(sm, version_id)

        data = []
        for e in raw.get("entities", []):
            pk_attrs = e.get("primaryKey", {}).get("attributes", [])
            data.append(
                {
                    "name": e.get("name", ""),
                    "dataset": e.get("datasetRef", ""),
                    "attributes": str(len(e.get("attributes", []))),
                    "primary_key": ",".join(pk_attrs),
                }
            )

        render(
            data,
            ["name", "dataset", "attributes", "primary_key"],
            output_format=output,
            title=f"Entities (version {version_id})",
        )
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("list-relationships")
def list_relationships(
    ctx: typer.Context,
    sm_ref: str = typer.Argument(help="Semantic model ID or name"),
    version: str | None = typer.Option(
        None, "--version", "-v", help="Version ID (default: active version)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List relationships in a semantic model version."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        sm = resolve_semantic_model(proj, sm_ref)
        version_id = _resolve_version_id(sm, version)
        _, raw = _load_version_settings(sm, version_id)

        data = [
            {
                "first_entity": r.get("firstEntity", ""),
                "second_entity": r.get("secondEntity", ""),
                "expression": r.get("pseudoSQLExpression", ""),
            }
            for r in raw.get("relationships", [])
        ]

        render(
            data,
            ["first_entity", "second_entity", "expression"],
            output_format=output,
            title=f"Relationships (version {version_id})",
        )
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("list-glossary")
def list_glossary(
    ctx: typer.Context,
    sm_ref: str = typer.Argument(help="Semantic model ID or name"),
    version: str | None = typer.Option(
        None, "--version", "-v", help="Version ID (default: active version)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List glossary terms in a semantic model version."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        sm = resolve_semantic_model(proj, sm_ref)
        version_id = _resolve_version_id(sm, version)
        _, raw = _load_version_settings(sm, version_id)

        data = [
            {
                "term": t.get("term", ""),
                "description": t.get("description", ""),
                "synonyms": ", ".join(t.get("synonyms", [])),
            }
            for t in raw.get("glossaryTerms", [])
        ]

        render(
            data,
            ["term", "description", "synonyms"],
            output_format=output,
            title=f"Glossary (version {version_id})",
        )
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("add-metric")
def add_metric(
    ctx: typer.Context,
    sm_ref: str = typer.Argument(help="Semantic model ID or name"),
    entity: str = typer.Option(..., "--entity", "-e", help="Entity name"),
    name: str = typer.Option(..., "--name", "-n", help="Metric name"),
    expression: str = typer.Option(
        ...,
        "--expression",
        "-x",
        help="Pseudo-SQL aggregate (e.g. 'COUNT(DISTINCT CustomerID)', 'SUM(Amount)')",
    ),
    description: str = typer.Option("", "--description", help="Metric description"),
    version: str | None = typer.Option(
        None, "--version", "-v", help="Version ID (default: active version)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    if_not_exists: bool = typer.Option(
        False, "--if-not-exists", help="Skip if a metric with this name exists"
    ),
) -> None:
    """Add a named aggregate metric (pseudoSQL) to an entity.

    Example:
      dku semantic-model add-metric MyModel --entity customer \\
          --name "Total Customers" \\
          --expression "COUNT(CustomerID)" \\
          --description "Total number of customer records" -P PROJ
    """
    project_key = resolve_project(project)
    name = _require_identifier(name, "Metric name")
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        sm = resolve_semantic_model(proj, sm_ref)
        version_id = _resolve_version_id(sm, version)
        settings, raw = _load_version_settings(sm, version_id)

        ent = _find_entity(raw, entity)
        metrics = ent.setdefault("metrics", [])
        if any(m.get("name") == name for m in metrics):
            if if_not_exists:
                warn(f"Metric '{name}' already exists on entity '{entity}', skipping.")
                return
            exit_with_error(
                f"Metric '{name}' already exists on entity '{entity}'.",
                code="already_exists",
                details=[
                    f"Remove first: dku semantic-model remove-metric {sm_ref} --entity {entity} --name '{name}' -P {project_key}",
                    "Or pass --if-not-exists to skip.",
                ],
            )

        metrics.append(
            {
                "name": name,
                "description": description,
                "pseudoSQLExpression": expression,
                "created": {},
            }
        )
        settings.save()
        success(f"Added metric '{name}' to entity '{entity}' on version '{version_id}'")
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("remove-metric")
def remove_metric(
    ctx: typer.Context,
    sm_ref: str = typer.Argument(help="Semantic model ID or name"),
    entity: str = typer.Option(..., "--entity", "-e", help="Entity name"),
    name: str = typer.Option(..., "--name", "-n", help="Metric name to remove"),
    version: str | None = typer.Option(
        None, "--version", "-v", help="Version ID (default: active version)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Remove a metric from an entity by name."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        sm = resolve_semantic_model(proj, sm_ref)
        version_id = _resolve_version_id(sm, version)
        settings, raw = _load_version_settings(sm, version_id)

        ent = _find_entity(raw, entity)
        metrics = ent.get("metrics", [])
        kept = [m for m in metrics if m.get("name") != name]
        if len(kept) == len(metrics):
            exit_with_error(
                f"Metric '{name}' not found on entity '{entity}'.",
                code="not_found",
                details=[
                    f"List metrics: dku semantic-model list-metrics {sm_ref} --entity {entity} -P {project_key}",
                ],
            )
        ent["metrics"] = kept
        settings.save()
        success(f"Removed metric '{name}' from entity '{entity}'")
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("list-metrics")
def list_metrics(
    ctx: typer.Context,
    sm_ref: str = typer.Argument(help="Semantic model ID or name"),
    entity: str = typer.Option(..., "--entity", "-e", help="Entity name"),
    version: str | None = typer.Option(
        None, "--version", "-v", help="Version ID (default: active version)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List metrics defined on an entity."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        sm = resolve_semantic_model(proj, sm_ref)
        version_id = _resolve_version_id(sm, version)
        _, raw = _load_version_settings(sm, version_id)

        ent = _find_entity(raw, entity)
        data = [
            {
                "name": m.get("name", ""),
                "expression": m.get("pseudoSQLExpression", ""),
                "description": m.get("description", ""),
            }
            for m in ent.get("metrics", [])
        ]
        render(
            data,
            ["name", "expression", "description"],
            output_format=output,
            title=f"Metrics on '{entity}' (version {version_id})",
        )
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("add-filter")
def add_filter(
    ctx: typer.Context,
    sm_ref: str = typer.Argument(help="Semantic model ID or name"),
    entity: str = typer.Option(..., "--entity", "-e", help="Entity name"),
    name: str = typer.Option(..., "--name", "-n", help="Filter name"),
    expression: str = typer.Option(
        ...,
        "--expression",
        "-x",
        help="Pseudo-SQL predicate (e.g. \"Subscribed = 'true'\", 'Amount > 1000')",
    ),
    description: str = typer.Option("", "--description", help="Filter description"),
    version: str | None = typer.Option(
        None, "--version", "-v", help="Version ID (default: active version)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    if_not_exists: bool = typer.Option(
        False, "--if-not-exists", help="Skip if a filter with this name exists"
    ),
) -> None:
    """Add a named pseudo-SQL filter (WHERE-clause fragment) to an entity.

    Example:
      dku semantic-model add-filter MyModel --entity customer \\
          --name "Subscribed customers" \\
          --expression "Subscribed = 'true'" -P PROJ
    """
    project_key = resolve_project(project)
    name = _require_identifier(name, "Filter name")
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        sm = resolve_semantic_model(proj, sm_ref)
        version_id = _resolve_version_id(sm, version)
        settings, raw = _load_version_settings(sm, version_id)

        ent = _find_entity(raw, entity)
        filters = ent.setdefault("filters", [])
        if any(f.get("name") == name for f in filters):
            if if_not_exists:
                warn(f"Filter '{name}' already exists on entity '{entity}', skipping.")
                return
            exit_with_error(
                f"Filter '{name}' already exists on entity '{entity}'.",
                code="already_exists",
                details=[
                    f"Remove first: dku semantic-model remove-filter {sm_ref} --entity {entity} --name '{name}' -P {project_key}",
                    "Or pass --if-not-exists to skip.",
                ],
            )

        filters.append(
            {
                "name": name,
                "description": description,
                "pseudoSQLExpression": expression,
                "created": {},
            }
        )
        settings.save()
        success(f"Added filter '{name}' to entity '{entity}' on version '{version_id}'")
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("remove-filter")
def remove_filter(
    ctx: typer.Context,
    sm_ref: str = typer.Argument(help="Semantic model ID or name"),
    entity: str = typer.Option(..., "--entity", "-e", help="Entity name"),
    name: str = typer.Option(..., "--name", "-n", help="Filter name to remove"),
    version: str | None = typer.Option(
        None, "--version", "-v", help="Version ID (default: active version)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Remove a filter from an entity by name."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        sm = resolve_semantic_model(proj, sm_ref)
        version_id = _resolve_version_id(sm, version)
        settings, raw = _load_version_settings(sm, version_id)

        ent = _find_entity(raw, entity)
        filters = ent.get("filters", [])
        kept = [f for f in filters if f.get("name") != name]
        if len(kept) == len(filters):
            exit_with_error(
                f"Filter '{name}' not found on entity '{entity}'.",
                code="not_found",
                details=[
                    f"List filters: dku semantic-model list-filters {sm_ref} --entity {entity} -P {project_key}",
                ],
            )
        ent["filters"] = kept
        settings.save()
        success(f"Removed filter '{name}' from entity '{entity}'")
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("list-filters")
def list_filters(
    ctx: typer.Context,
    sm_ref: str = typer.Argument(help="Semantic model ID or name"),
    entity: str = typer.Option(..., "--entity", "-e", help="Entity name"),
    version: str | None = typer.Option(
        None, "--version", "-v", help="Version ID (default: active version)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List filters defined on an entity."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        sm = resolve_semantic_model(proj, sm_ref)
        version_id = _resolve_version_id(sm, version)
        _, raw = _load_version_settings(sm, version_id)

        ent = _find_entity(raw, entity)
        data = [
            {
                "name": f.get("name", ""),
                "expression": f.get("pseudoSQLExpression", ""),
                "description": f.get("description", ""),
            }
            for f in ent.get("filters", [])
        ]
        render(
            data,
            ["name", "expression", "description"],
            output_format=output,
            title=f"Filters on '{entity}' (version {version_id})",
        )
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("set-manual-values")
def set_manual_values(
    ctx: typer.Context,
    sm_ref: str = typer.Argument(help="Semantic model ID or name"),
    entity: str = typer.Option(..., "--entity", "-e", help="Entity name"),
    attribute: str = typer.Option(..., "--attribute", "-a", help="Attribute name"),
    values: str = typer.Option(
        None,
        "--values",
        help="Comma-separated manual values (curated enum). Omit with --clear to revert to indexed mode.",
    ),
    clear: bool = typer.Option(
        False,
        "--clear",
        help="Clear manual values and revert attribute to distinctValuesHandlingMode=NONE",
    ),
    version: str | None = typer.Option(
        None, "--version", "-v", help="Version ID (default: active version)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Set or clear curated distinct values on an attribute.

    With --values: sets distinctValuesHandlingMode=MANUAL, enables
    indexDistinctValues and resolveInUserRequests so the text-to-SQL
    agent uses the enum for value resolution.

    With --clear: reverts to NONE (no curated values, relies on indexed scan).

    Example:
      dku semantic-model set-manual-values MyModel --entity customer \\
          --attribute RiskTolerance --values "Low,Medium,High" -P PROJ
    """
    if bool(values) == bool(clear):
        exit_with_error(
            "Exactly one of --values or --clear is required.",
            code="invalid_argument",
            details=[
                'Set:   --values "Low,Medium,High"',
                "Clear: --clear",
            ],
        )

    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        sm = resolve_semantic_model(proj, sm_ref)
        version_id = _resolve_version_id(sm, version)
        settings, raw = _load_version_settings(sm, version_id)

        ent = _find_entity(raw, entity)
        attrs = ent.get("attributes", [])
        target = next((a for a in attrs if a.get("name") == attribute), None)
        if target is None:
            exit_with_error(
                f"Attribute '{attribute}' not found on entity '{entity}'.",
                code="not_found",
                details=[
                    "Available attributes: "
                    + (", ".join(a.get("name", "") for a in attrs) or "(none)"),
                ],
            )

        if clear:
            target["distinctValuesHandlingMode"] = "NONE"
            target["manualValues"] = []
            settings.save()
            success(f"Cleared manual values on {entity}.{attribute} (mode=NONE)")
            return

        vals = _split_csv(values)
        if not vals:
            exit_with_error(
                "--values must be a non-empty comma-separated list.",
                code="invalid_argument",
                details=['Example: --values "Low,Medium,High"'],
            )
        target["distinctValuesHandlingMode"] = "MANUAL"
        target["manualValues"] = vals
        target["indexDistinctValues"] = True
        target["resolveInUserRequests"] = True
        settings.save()
        success(f"Set {len(vals)} manual value(s) on {entity}.{attribute}: {vals}")
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("add-golden-query")
def add_golden_query(
    ctx: typer.Context,
    sm_ref: str = typer.Argument(help="Semantic model ID or name"),
    name: str = typer.Option(..., "--name", "-n", help="Golden query name"),
    question: str = typer.Option(
        ..., "--question", "-q", help="Natural-language question"
    ),
    sql: str = typer.Option(
        ..., "--sql", "-s", help="Target SQL (used as few-shot example)"
    ),
    version: str | None = typer.Option(
        None, "--version", "-v", help="Version ID (default: active version)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    if_not_exists: bool = typer.Option(
        False, "--if-not-exists", help="Skip if a golden query with this name exists"
    ),
) -> None:
    """Add a golden query (NL question → target SQL) as a few-shot example.

    The text-to-SQL agent uses these to learn the model's style and joins.

    Example:
      dku semantic-model add-golden-query MyModel \\
          --name "monthly revenue" \\
          --question "What was revenue by product last month?" \\
          --sql "SELECT p.ProductName, SUM(o.Amount) FROM orders o JOIN products p ON o.ProductID = p.ProductID WHERE o.Date >= CURRENT_DATE - INTERVAL '1 month' GROUP BY p.ProductName" \\
          -P PROJ
    """
    project_key = resolve_project(project)
    name = _require_identifier(name, "Golden query name")
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        sm = resolve_semantic_model(proj, sm_ref)
        version_id = _resolve_version_id(sm, version)
        settings, raw = _load_version_settings(sm, version_id)

        queries = raw.setdefault("goldenQueries", [])
        if any(q.get("name") == name for q in queries):
            if if_not_exists:
                warn(f"Golden query '{name}' already exists, skipping.")
                return
            exit_with_error(
                f"Golden query '{name}' already exists on version '{version_id}'.",
                code="already_exists",
                details=[
                    f"Remove first: dku semantic-model remove-golden-query {sm_ref} --name '{name}' -P {project_key}",
                    "Or pass --if-not-exists to skip.",
                ],
            )

        queries.append(
            {
                "name": name,
                "question": question,
                "generatedSql": sql,
                "created": {},
            }
        )
        settings.save()
        success(f"Added golden query '{name}' to version '{version_id}'")
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("remove-golden-query")
def remove_golden_query(
    ctx: typer.Context,
    sm_ref: str = typer.Argument(help="Semantic model ID or name"),
    name: str = typer.Option(..., "--name", "-n", help="Golden query name to remove"),
    version: str | None = typer.Option(
        None, "--version", "-v", help="Version ID (default: active version)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Remove a golden query by name."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        sm = resolve_semantic_model(proj, sm_ref)
        version_id = _resolve_version_id(sm, version)
        settings, raw = _load_version_settings(sm, version_id)

        queries = raw.get("goldenQueries", [])
        kept = [q for q in queries if q.get("name") != name]
        if len(kept) == len(queries):
            exit_with_error(
                f"Golden query '{name}' not found on version '{version_id}'.",
                code="not_found",
                details=[
                    f"List golden queries: dku semantic-model list-golden-queries {sm_ref} -P {project_key}",
                ],
            )
        raw["goldenQueries"] = kept
        settings.save()
        success(f"Removed golden query '{name}' from version '{version_id}'")
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("list-golden-queries")
def list_golden_queries(
    ctx: typer.Context,
    sm_ref: str = typer.Argument(help="Semantic model ID or name"),
    version: str | None = typer.Option(
        None, "--version", "-v", help="Version ID (default: active version)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List golden queries on a semantic model version."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        sm = resolve_semantic_model(proj, sm_ref)
        version_id = _resolve_version_id(sm, version)
        _, raw = _load_version_settings(sm, version_id)

        data = [
            {
                "name": q.get("name", ""),
                "question": q.get("question", ""),
                "sql": q.get("generatedSql", ""),
            }
            for q in raw.get("goldenQueries", [])
        ]
        render(
            data,
            ["name", "question", "sql"],
            output_format=output,
            title=f"Golden queries (version {version_id})",
        )
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
