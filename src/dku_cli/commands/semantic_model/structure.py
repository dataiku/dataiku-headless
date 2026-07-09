"""Semantic-model entity and relationship commands."""

# ruff: noqa: F403,F405
from ._common import *


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
                details=[
                    f"Original error: {e}",
                    f"List datasets: dku dataset list -P {project_key}",
                ],
            )
        columns = ds_def.get("schema", {}).get("columns", [])
        if not columns:
            exit_with_error(
                f"Dataset '{from_dataset}' has no schema columns — nothing to map.",
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
                c["name"], c.get("type", "string"), _column_description(c)
            )
            if c["name"] in index_cols:
                a["indexDistinctValues"] = True
            if c["name"] in resolve_cols:
                a["resolveInUserRequests"] = True
            attrs.append(a)

        entity_description = description or (ds_def.get("shortDesc") or "").strip()

        entity = {
            "name": entity_name,
            "description": entity_description,
            "tags": _split_csv(tags),
            "type": "DATASET",
            "datasetRef": f"{project_key}.{from_dataset}",
            "metrics": [],
            "filters": [],
            "primaryKey": {"attributes": pk_cols},
            "foreignKeys": [],
            "attributes": attrs,
        }

        with _version_write_lock(client, project_key, sm, version_id):
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
                    details=[
                        f"Remove first: dku semantic-model remove-entity {sm_ref} {entity_name} --version {version_id} -P {project_key}",
                        "Or pass --if-not-exists to skip.",
                    ],
                )

            raw.setdefault("entities", []).append(entity)
            settings.save()
            _verify_entity_persisted(sm, version_id, entity_name, sm_ref, project_key)
        described, total = _described_ratio(attrs)
        success(
            f"Added entity '{entity_name}' ({total} attributes, {described} "
            f"described, PK {pk_cols}) to version '{version_id}' on '{sm_ref}'"
        )
        if described == 0:
            warn(
                f"0/{total} columns on dataset '{from_dataset}' carry "
                "descriptions — the text2SQL agent gets no column context. "
                "Descriptions are snapshotted now; describing the dataset "
                "later does NOT update this entity."
            )
            info(
                f"Fix: dku dataset ai-describe {from_dataset} --save "
                f"-P {project_key} && dku semantic-model sync-descriptions "
                f"{sm_ref} -P {project_key}"
            )
        info(
            f"Run 'dku semantic-model update-index {sm_ref} --wait -P {project_key}' to populate distinct values."
        )
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)


def _sync_entity_descriptions(
    client, project_key: str, ent: dict, overwrite: bool
) -> tuple[int, int, int, str | None, str | None]:
    """Copy descriptions from an entity's backing dataset onto the entity.

    Returns (attrs_updated, entity_updated, available, coverage_line, failure).
    `failure` is a reason string (entity left untouched) or None.
    """
    ent_name = ent.get("name", "?")
    dataset_ref = ent.get("datasetRef", "")
    if not dataset_ref:
        return 0, 0, 0, None, f"{ent_name}: no datasetRef (manual entity?)"
    ref_project, _, ref_dataset = dataset_ref.rpartition(".")
    try:
        proj = client.get_project(ref_project or project_key)
        ds_def = proj.get_dataset(ref_dataset).get_definition()
    except Exception as e:
        return 0, 0, 0, None, f"{ent_name}: cannot read dataset '{dataset_ref}' ({e})"

    col_desc = {
        c["name"]: _column_description(c)
        for c in ds_def.get("schema", {}).get("columns", [])
    }
    available = sum(1 for d in col_desc.values() if d)

    attrs_updated = 0
    ent_attrs = ent.get("attributes", [])
    before, total = _described_ratio(ent_attrs)
    for attr in ent_attrs:
        if attr.get("type") not in (None, "COLUMN"):
            continue
        desc = col_desc.get(attr.get("column") or attr.get("name"), "")
        writable = overwrite or not attr.get("description")
        if desc and writable and attr.get("description") != desc:
            attr["description"] = desc
            attrs_updated += 1

    entity_updated = 0
    short_desc = (ds_def.get("shortDesc") or "").strip()
    writable = overwrite or not ent.get("description")
    if short_desc and writable and ent.get("description") != short_desc:
        ent["description"] = short_desc
        entity_updated = 1

    after, _ = _described_ratio(ent_attrs)
    line = f"{ent_name}: {before}->{after} of {total} attributes described"
    if not available:
        line += f" (dataset '{ref_dataset}' has no column descriptions)"
    return attrs_updated, entity_updated, available, line, None


def _report_sync_results(
    *,
    version_id: str,
    sm_ref: str,
    project_key: str,
    targets: list[dict],
    attrs_updated: int,
    entities_updated: int,
    available_total: int,
    coverage: list[str],
    failures: list[str],
) -> None:
    """Report sync outcome; exit non-zero on failures or nothing-to-copy."""
    success(
        f"Synced descriptions on version '{version_id}': {attrs_updated} "
        f"attribute(s), {entities_updated} entity description(s) updated"
    )
    for line in coverage:
        info(f"  {line}")

    if failures:
        exit_with_error(
            f"{len(failures)} entity(ies) could not be synced "
            "(changes for the others are saved):",
            details=[
                *failures,
                f"List datasets: dku dataset list -P {project_key}",
            ],
        )
    if available_total == 0:
        describe_cmds = " && ".join(
            "dku dataset ai-describe "
            f"{e.get('datasetRef', '').rpartition('.')[2]} --save -P {project_key}"
            for e in targets
            if e.get("datasetRef")
        )
        exit_with_error(
            "No column descriptions exist on any backing dataset — nothing to copy.",
            details=[
                f"Generate them first: {describe_cmds}",
                "Then re-run: dku semantic-model sync-descriptions "
                f"{sm_ref} -P {project_key}",
            ],
        )


@app.command("sync-descriptions")
def sync_descriptions(
    ctx: typer.Context,
    sm_ref: str = typer.Argument(help="Semantic model ID or name"),
    entity: str = typer.Option(
        None, "--entity", "-e", help="Sync only this entity (default: all entities)"
    ),
    overwrite: bool = typer.Option(
        False,
        "--overwrite",
        help="Replace existing descriptions too (default: only fill empty ones)",
    ),
    version: str | None = typer.Option(
        None, "--version", "-v", help="Version ID (default: active version)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Backfill entity and attribute descriptions from backing dataset schemas.

    Entities snapshot the dataset schema at add-entity time — descriptions
    added to the dataset afterwards (via `dku dataset ai-describe --save` or
    `set-column-description`) do not propagate. This command re-reads each
    backing dataset and copies column descriptions onto attributes, and the
    dataset's short description onto the entity. Nothing is ever blanked;
    existing descriptions are kept unless --overwrite.

    Typical flow:
      dku dataset ai-describe DS --save -P PROJ
      dku semantic-model sync-descriptions SM -P PROJ
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        sm = resolve_semantic_model(proj, sm_ref)
        version_id = _resolve_version_id(sm, version)

        with _version_write_lock(client, project_key, sm, version_id, timeout_s=300.0):
            settings, raw = _load_version_settings(sm, version_id)

            targets = [_find_entity(raw, entity)] if entity else raw.get("entities", [])
            if not targets:
                exit_with_error(
                    f"No entities on version '{version_id}' — nothing to sync.",
                    details=[
                        "Add one: dku semantic-model add-entity "
                        f"{sm_ref} --from-dataset DS -P {project_key}",
                    ],
                )

            attrs_updated = 0
            entities_updated = 0
            available_total = 0
            failures: list[str] = []
            coverage: list[str] = []
            for ent in targets:
                a_upd, e_upd, avail, line, failure = _sync_entity_descriptions(
                    client, project_key, ent, overwrite
                )
                if failure:
                    failures.append(failure)
                    continue
                attrs_updated += a_upd
                entities_updated += e_upd
                available_total += avail
                coverage.append(line)

            if attrs_updated or entities_updated:
                settings.save()
        _report_sync_results(
            version_id=version_id,
            sm_ref=sm_ref,
            project_key=project_key,
            targets=targets,
            attrs_updated=attrs_updated,
            entities_updated=entities_updated,
            available_total=available_total,
            coverage=coverage,
            failures=failures,
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
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip safety guard"),
) -> None:
    """Remove an entity from a semantic model version.

    Also removes any relationships that reference this entity.
    """
    from dku_cli.safety import Tier, guard

    project_key = resolve_project(project)
    guard(
        ctx,
        tier=Tier.DELETE,
        action="semantic_model.remove_entity",
        subject=f"entity '{entity_name}' on semantic model '{sm_ref}' in {project_key}",
        yes=yes,
        prompt=(
            f"Remove entity '{entity_name}' from semantic model '{sm_ref}' in "
            f"{project_key}? This also drops any relationships that reference it."
        ),
    )
    try:
        client, _proj, sm, version_id = _resolve_locked_version(
            ctx, project_key, sm_ref, version
        )
        with _version_settings_lock(client, project_key, sm, version_id) as settings:
            raw = settings.get_raw()

            entities = raw.get("entities", [])
            new_entities = [e for e in entities if e.get("name") != entity_name]
            if len(new_entities) == len(entities):
                exit_with_error(
                    f"Entity '{entity_name}' not found on version '{version_id}'.",
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
            details=[
                "Simple: --on CustomerID",
                "Composite: --on ACCOUNT_SK,MONTH",
                'Custom: --expression "LOWER(left.email) = LOWER(right.email)"',
            ],
        )

    project_key = resolve_project(project)
    try:
        client, _proj, sm, version_id = _resolve_locked_version(
            ctx, project_key, sm_ref, version
        )
        with _version_write_lock(client, project_key, sm, version_id):
            settings, raw = _load_version_settings(sm, version_id)

            entity_names = {e.get("name") for e in raw.get("entities", [])}
            missing = [
                ent for ent in (first_entity, second_entity) if ent not in entity_names
            ]
            if missing:
                exit_with_error(
                    f"Entity not found on version '{version_id}': {', '.join(missing)}",
                    details=[
                        "Available entities: "
                        + (
                            ", ".join(sorted(entity_names))
                            if entity_names
                            else "(none)"
                        ),
                        "Add with: dku semantic-model add-entity SM --from-dataset DS -P PROJ",
                    ],
                )

            if on:
                cols = _dedupe_preserve_order(_split_csv(on))
                if not cols:
                    exit_with_error(
                        "--on produced no valid join columns (empty or whitespace only).",
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
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip safety guard"),
) -> None:
    """Remove a relationship between two entities (matches either order)."""
    from dku_cli.safety import Tier, guard

    project_key = resolve_project(project)
    guard(
        ctx,
        tier=Tier.DELETE,
        action="semantic_model.remove_relationship",
        subject=(
            f"relationship '{first_entity}'–'{second_entity}' on semantic model "
            f"'{sm_ref}' in {project_key}"
        ),
        yes=yes,
        prompt=(
            f"Remove the relationship between '{first_entity}' and '{second_entity}' "
            f"on '{sm_ref}' in {project_key}?"
        ),
    )
    try:
        client, _proj, sm, version_id = _resolve_locked_version(
            ctx, project_key, sm_ref, version
        )
        with _version_settings_lock(client, project_key, sm, version_id) as settings:
            raw = settings.get_raw()

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
                    details=[
                        "List relationships: dku semantic-model list-relationships "
                        f"{sm_ref} -P {project_key}",
                    ],
                )

            raw["relationships"] = kept
        success(
            f"Removed {removed} relationship(s) between '{first_entity}' and '{second_entity}' on version '{version_id}'"
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
) -> None:
    """List entities in a semantic model version (name, dataset, attribute count, PK)."""
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        sm = resolve_semantic_model(proj, sm_ref)
        version_id = _resolve_version_id(sm, version)
        _, raw = _load_version_settings(sm, version_id)

        data = []
        for e in raw.get("entities", []):
            pk_attrs = e.get("primaryKey", {}).get("attributes", [])
            described, total = _described_ratio(e.get("attributes", []))
            data.append(
                {
                    "name": e.get("name", ""),
                    "dataset": e.get("datasetRef", ""),
                    "attributes": str(total),
                    "described": f"{described}/{total}",
                    "primary_key": ",".join(pk_attrs),
                }
            )

        render(
            data,
            ["name", "dataset", "attributes", "described", "primary_key"],
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
) -> None:
    """List relationships in a semantic model version."""
    project_key = resolve_project(project)
    output = resolve_output_format()
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
            details=[
                'Set:   --values "Low,Medium,High"',
                "Clear: --clear",
            ],
        )

    project_key = resolve_project(project)
    try:
        client, _proj, sm, version_id = _resolve_locked_version(
            ctx, project_key, sm_ref, version
        )
        with _version_write_lock(client, project_key, sm, version_id):
            settings, raw = _load_version_settings(sm, version_id)

            ent = _find_entity(raw, entity)
            attrs = ent.get("attributes", [])
            target = next((a for a in attrs if a.get("name") == attribute), None)
            if target is None:
                exit_with_error(
                    f"Attribute '{attribute}' not found on entity '{entity}'.",
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
