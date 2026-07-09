"""Semantic-model glossary, metric, filter, and golden query commands."""

# ruff: noqa: F403,F405
from ._common import *


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
        client, _proj, sm, version_id = _resolve_locked_version(
            ctx, project_key, sm_ref, version
        )
        with _version_write_lock(client, project_key, sm, version_id):
            settings, raw = _load_version_settings(sm, version_id)
            terms = raw.setdefault("glossaryTerms", [])
            added = _append_named_item(
                terms,
                {
                    "id": str(uuid.uuid4()),
                    "term": term,
                    "description": description,
                    "source": "MANUAL",
                    "userModified": True,
                    "synonyms": _split_csv(synonyms),
                    "created": {},
                    "privateEditorData": {},
                },
                name_key="term",
                name=term,
                label="Glossary term",
                duplicate_scope=f" on version '{version_id}'",
                if_not_exists=if_not_exists,
                remove_hint=(
                    f"Remove first: dku semantic-model remove-glossary-term {sm_ref} "
                    f"--term '{term}' -P {project_key}"
                ),
            )
            if not added:
                return
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
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip safety guard"),
) -> None:
    """Remove a glossary term by its label."""
    from dku_cli.safety import Tier, guard

    project_key = resolve_project(project)
    guard(
        ctx,
        tier=Tier.DELETE,
        action="semantic_model.remove_glossary_term",
        subject=f"glossary term '{term}' on '{sm_ref}' in {project_key}",
        yes=yes,
        prompt=f"Remove glossary term '{term}' from '{sm_ref}' in {project_key}?",
    )
    try:
        version_id, lock = _locked_command_version(ctx, project_key, sm_ref, version)
        with lock as settings:
            raw = settings.get_raw()
            _remove_named_item(
                raw,
                "glossaryTerms",
                name_key="term",
                name=term,
                label="Glossary term",
                missing_scope=f" on version '{version_id}'",
                list_hint=f"List terms: dku semantic-model list-glossary {sm_ref} -P {project_key}",
            )
        success(
            f"Removed glossary term '{term}' from version '{version_id}' on '{sm_ref}'"
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
) -> None:
    """List glossary terms in a semantic model version."""
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        version_id, _, raw = _load_command_version(ctx, project_key, sm_ref, version)
        _render_collection(
            raw.get("glossaryTerms", []),
            ["term", "description", "synonyms"],
            output=output,
            title=f"Glossary (version {version_id})",
            row_builder=lambda t: {
                "term": t.get("term", ""),
                "description": t.get("description", ""),
                "synonyms": ", ".join(t.get("synonyms", [])),
            },
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
        _add_entity_expression_item(
            ctx,
            sm_ref=sm_ref,
            entity=entity,
            name=name,
            expression=expression,
            description=description,
            version=version,
            project_key=project_key,
            if_not_exists=if_not_exists,
            collection_key="metrics",
            label="Metric",
            remove_command="remove-metric",
        )
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
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip safety guard"),
) -> None:
    """Remove a metric from an entity by name."""
    from dku_cli.safety import Tier, guard

    project_key = resolve_project(project)
    guard(
        ctx,
        tier=Tier.DELETE,
        action="semantic_model.remove_metric",
        subject=f"metric '{name}' on entity '{entity}' of '{sm_ref}' in {project_key}",
        yes=yes,
        prompt=(
            f"Remove metric '{name}' (entity '{entity}') from "
            f"'{sm_ref}' in {project_key}?"
        ),
    )
    try:
        _remove_entity_expression_item(
            ctx,
            sm_ref=sm_ref,
            entity=entity,
            name=name,
            version=version,
            project_key=project_key,
            collection_key="metrics",
            label="Metric",
            list_command="list-metrics",
        )
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
) -> None:
    """List metrics defined on an entity."""
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        _list_entity_expression_items(
            ctx,
            sm_ref=sm_ref,
            entity=entity,
            version=version,
            project_key=project_key,
            output=output,
            collection_key="metrics",
            title_label="Metrics",
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
        _add_entity_expression_item(
            ctx,
            sm_ref=sm_ref,
            entity=entity,
            name=name,
            expression=expression,
            description=description,
            version=version,
            project_key=project_key,
            if_not_exists=if_not_exists,
            collection_key="filters",
            label="Filter",
            remove_command="remove-filter",
        )
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
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip safety guard"),
) -> None:
    """Remove a filter from an entity by name."""
    from dku_cli.safety import Tier, guard

    project_key = resolve_project(project)
    guard(
        ctx,
        tier=Tier.DELETE,
        action="semantic_model.remove_filter",
        subject=f"filter '{name}' on entity '{entity}' of '{sm_ref}' in {project_key}",
        yes=yes,
        prompt=(
            f"Remove filter '{name}' (entity '{entity}') from "
            f"'{sm_ref}' in {project_key}?"
        ),
    )
    try:
        _remove_entity_expression_item(
            ctx,
            sm_ref=sm_ref,
            entity=entity,
            name=name,
            version=version,
            project_key=project_key,
            collection_key="filters",
            label="Filter",
            list_command="list-filters",
        )
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
) -> None:
    """List filters defined on an entity."""
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        _list_entity_expression_items(
            ctx,
            sm_ref=sm_ref,
            entity=entity,
            version=version,
            project_key=project_key,
            output=output,
            collection_key="filters",
            title_label="Filters",
        )
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
        client, _proj, sm, version_id = _resolve_locked_version(
            ctx, project_key, sm_ref, version
        )
        with _version_write_lock(client, project_key, sm, version_id):
            settings, raw = _load_version_settings(sm, version_id)
            queries = raw.setdefault("goldenQueries", [])
            added = _append_named_item(
                queries,
                {
                    "name": name,
                    "question": question,
                    "generatedSql": sql,
                    "created": {},
                },
                name_key="name",
                name=name,
                label="Golden query",
                duplicate_scope=f" on version '{version_id}'",
                if_not_exists=if_not_exists,
                remove_hint=(
                    f"Remove first: dku semantic-model remove-golden-query {sm_ref} "
                    f"--name '{name}' -P {project_key}"
                ),
            )
            if not added:
                return
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
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip safety guard"),
) -> None:
    """Remove a golden query by name."""
    from dku_cli.safety import Tier, guard

    project_key = resolve_project(project)
    guard(
        ctx,
        tier=Tier.DELETE,
        action="semantic_model.remove_golden_query",
        subject=f"golden query '{name}' on '{sm_ref}' in {project_key}",
        yes=yes,
        prompt=f"Remove golden query '{name}' from '{sm_ref}' in {project_key}?",
    )
    try:
        version_id, lock = _locked_command_version(ctx, project_key, sm_ref, version)
        with lock as settings:
            raw = settings.get_raw()
            _remove_named_item(
                raw,
                "goldenQueries",
                name_key="name",
                name=name,
                label="Golden query",
                missing_scope=f" on version '{version_id}'",
                list_hint=(
                    f"List golden queries: dku semantic-model list-golden-queries {sm_ref} "
                    f"-P {project_key}"
                ),
            )
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
) -> None:
    """List golden queries on a semantic model version."""
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        version_id, _, raw = _load_command_version(ctx, project_key, sm_ref, version)
        _render_collection(
            raw.get("goldenQueries", []),
            ["name", "question", "sql"],
            output=output,
            title=f"Golden queries (version {version_id})",
            row_builder=lambda q: {
                "name": q.get("name", ""),
                "question": q.get("question", ""),
                "sql": q.get("generatedSql", ""),
            },
        )
    except SystemExit:
        raise
    except Exception as e:
        handle_api_error(e)
