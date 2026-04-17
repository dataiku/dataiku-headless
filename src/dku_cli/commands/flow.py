"""dku flow — graph, zones, create-zone, set-zone, move, propagate, check, sources, successors."""

from __future__ import annotations

import typer

from dku_cli.errors import exit_with_error, handle_api_error, is_not_found_error
from dku_cli.helpers import get_client_from_ctx, resolve_folder, resolve_project
from dku_cli.output import (
    error,
    render,
    render_dag,
    render_raw,
    resolve_output_format,
    success,
)

app = typer.Typer(help="Inspect and manage DSS project flow.")


@app.command()
def graph(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show flow graph summary."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        flow = proj.get_flow()
        graph_obj = flow.get_graph()

        if output == "json":
            render_raw(graph_obj.data, output_format="json")
        else:
            data = []
            for node_id, node in graph_obj.nodes.items():
                data.append(
                    {
                        "id": node_id,
                        "type": node.get("type", ""),
                        "subtype": node.get("subType", ""),
                        "ref": node.get("ref", node_id),
                    }
                )

            render(
                data,
                ["id", "type", "subtype", "ref"],
                output_format=output,
                title=f"Flow Graph ({project_key})",
            )
    except Exception as e:
        handle_api_error(e)


@app.command()
def visualize(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Render flow DAG as an ASCII tree."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        graph_obj = client.get_project(project_key).get_flow().get_graph()
        render_dag(graph_obj.nodes, f"Flow DAG ({project_key})")
    except Exception as e:
        handle_api_error(e)


@app.command()
def zones(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List flow zones with their items (objectType + objectId per member)."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        flow = proj.get_flow()
        zone_list = flow.list_zones()

        data = []
        for z in zone_list:
            raw_items = getattr(z, "_raw", {}).get("items", []) or []
            items = [
                {
                    "objectType": i.get("objectType"),
                    "objectId": i.get("objectId"),
                    "projectKey": i.get("projectKey", project_key),
                }
                for i in raw_items
            ]
            data.append(
                {
                    "id": z.id,
                    "name": z.name,
                    "itemCount": len(items),
                    "items": items,
                }
            )

        # Table view only shows id/name/itemCount; items shipped in JSON.
        render(
            data,
            ["id", "name", "itemCount"],
            output_format=output,
            title=f"Flow Zones ({project_key})",
        )
    except Exception as e:
        handle_api_error(e)


@app.command("create-zone")
def create_zone(
    ctx: typer.Context,
    name: str = typer.Argument(help="Zone name"),
    color: str | None = typer.Option(
        None, "--color", "-c", help="Zone color (hex, e.g. #FF5500)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a new flow zone."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        flow = proj.get_flow()
        zone = flow.create_zone(name)
        if color is not None:
            settings = zone.get_settings()
            settings.color = color
            settings.save()
        success(f"Created zone '{name}' (id: {zone.id})")
    except Exception as e:
        handle_api_error(e)


@app.command("set-zone")
def set_zone(
    ctx: typer.Context,
    zone_ref: str = typer.Argument(help="Zone name or ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    name: str | None = typer.Option(None, "--name", "-n", help="New zone name"),
    color: str | None = typer.Option(
        None, "--color", "-c", help="Zone color (hex, e.g. #FF5500)"
    ),
) -> None:
    """Update a flow zone's name and/or color."""
    if name is None and color is None:
        error("Provide --name and/or --color to update.")
        raise typer.Exit(1)
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        flow = proj.get_flow()
        zone = _resolve_zone(flow, zone_ref, project_key)
        settings = zone.get_settings()
        if name is not None:
            settings.name = name
        if color is not None:
            settings.color = color
        settings.save()
        success(f"Updated zone '{zone_ref}'")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


def _resolve_zone(flow, zone_ref: str, project_key: str):
    """Resolve a zone by name (case-insensitive) or ID. Returns the zone object."""
    zones = flow.list_zones()
    # Try exact ID match first
    for z in zones:
        if z.id == zone_ref:
            return z
    # Try case-insensitive name match
    for z in zones:
        if z.name.lower() == zone_ref.lower():
            return z
    # Not found — prescriptive error
    zone_list = ", ".join(f"'{z.name}' (id: {z.id})" for z in zones)
    exit_with_error(
        f"Zone '{zone_ref}' not found in project '{project_key}'.",
        code="not_found",
        details=[
            f"Available zones: {zone_list}",
            f"List zones: dku flow zones -P {project_key}",
            f'Create zone: dku flow create-zone "<name>" -P {project_key}',
        ],
    )


_ITEM_RESOLVERS = {
    "DATASET": "get_dataset",
    "RECIPE": "get_recipe",
    "MANAGED_FOLDER": "get_managed_folder",
    "SAVED_MODEL": "get_saved_model",
}


@app.command()
def move(
    ctx: typer.Context,
    items: list[str] = typer.Argument(
        help="Item names to move (datasets by default). Use --type for other item types."
    ),
    zone: str = typer.Option(
        ...,
        "--zone",
        "-z",
        help="Target zone name or ID. Use 'dku flow zones' to list.",
    ),
    item_type: str = typer.Option(
        "DATASET",
        "--type",
        "-t",
        help="Item type: DATASET, RECIPE, MANAGED_FOLDER, SAVED_MODEL",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Move items to a flow zone. Use instead of manually organizing in the DSS UI.

    Move datasets, recipes, folders, or models to a named zone.
    Zones help organize complex flows into logical sections.

    Examples:
      dku flow move my_dataset --zone Processing -P PROJ
      dku flow move ds1 ds2 ds3 --zone Analytics -P PROJ
      dku flow move my_recipe --zone ETL --type RECIPE -P PROJ
    """
    project_key = resolve_project(project)
    item_type_upper = item_type.upper()
    if item_type_upper not in _ITEM_RESOLVERS:
        exit_with_error(
            f"Unknown item type '{item_type}'.",
            code="invalid_argument",
            details=[f"Valid types: {', '.join(sorted(_ITEM_RESOLVERS))}"],
        )
    resolver_method = _ITEM_RESOLVERS[item_type_upper]
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        flow = proj.get_flow()

        target_zone = _resolve_zone(flow, zone, project_key)

        # Resolve item objects
        resolved = []
        for name in items:
            try:
                if item_type_upper == "MANAGED_FOLDER":
                    obj = resolve_folder(proj, name)
                else:
                    obj = getattr(proj, resolver_method)(name)
                resolved.append(obj)
            except Exception as e:
                if is_not_found_error(e):
                    list_cmd = {
                        "DATASET": "dataset list",
                        "RECIPE": "recipe list",
                        "MANAGED_FOLDER": "folder list",
                        "SAVED_MODEL": "model list",
                    }
                    exit_with_error(
                        f"{item_type_upper} '{name}' not found in project '{project_key}'.",
                        code="not_found",
                        details=[
                            f"List available: dku {list_cmd.get(item_type_upper, 'dataset list')} -P {project_key}"
                        ],
                    )
                raise

        # Move: batch for multiple, single for one
        if len(resolved) == 1:
            target_zone.add_item(resolved[0])
        else:
            target_zone.add_items(resolved)

        names = ", ".join(f"'{n}'" for n in items)
        success(f"Moved {names} to zone '{target_zone.name}' in {project_key}")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def propagate(
    ctx: typer.Context,
    dataset: str = typer.Argument(help="Starting dataset name for schema propagation"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    stop_at: list[str] | None = typer.Option(
        None, "--stop-at", help="Recipe to stop propagation at (repeatable)"
    ),
    mark_ok: list[str] | None = typer.Option(
        None, "--mark-ok", help="Recipe to mark as OK during propagation (repeatable)"
    ),
    no_auto_rebuild: bool = typer.Option(
        False, "--no-auto-rebuild", help="Disable automatic rebuild during propagation"
    ),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Run schema propagation from a dataset through downstream recipes."""
    project_key = resolve_project(project)
    output = resolve_output_format(output, allowed=("table", "json"), default="json")
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        flow = proj.get_flow()

        builder = flow.new_schema_propagation(dataset)
        if no_auto_rebuild:
            builder.set_auto_rebuild(False)
        for recipe_name in stop_at or []:
            builder.stop_at(recipe_name)
        for recipe_name in mark_ok or []:
            builder.mark_recipe_as_ok(recipe_name)

        result = builder.start().wait_for_result()

        render_raw(result, output_format=output)
        success(f"Schema propagation from '{dataset}' complete.")
    except Exception as e:
        handle_api_error(e)


@app.command()
def check(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Run flow consistency check (schema + data consistency)."""
    project_key = resolve_project(project)
    output = resolve_output_format(output, allowed=("table", "json"), default="json")
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        flow = proj.get_flow()

        tool = flow.start_tool("CHECK_CONSISTENCY")
        try:
            future = tool.update(
                {
                    "recheckAll": True,
                    "datasets": {"consistencyWithData": True},
                    "recipes": {
                        "schemaConsistency": True,
                        "otherExpensiveChecks": False,
                    },
                }
            )
            future.wait_for_result()
            state = tool.get_state()
            summary = state.get("summary", {})
            errors = []
            for node_id, node_state in state.get("stateByNode", {}).items():
                for check_key in ("recipeCheckResult", "datasetCheckResult"):
                    check = node_state.get(check_key, {})
                    for msg in check.get("messages", []):
                        if msg.get("isFatal") or msg.get("severity") in (
                            "ERROR",
                            "FATAL",
                        ):
                            errors.append(
                                {
                                    "node": node_id,
                                    "code": msg.get("code", ""),
                                    "message": msg.get("message", ""),
                                }
                            )
            if output == "json":
                render_raw({"summary": summary, "errors": errors}, output_format="json")
            else:
                render(
                    [{"field": k, "value": str(v)} for k, v in summary.items()],
                    ["field", "value"],
                    output_format=output,
                    title=f"Flow Check Summary ({project_key})",
                )
                if errors:
                    render(
                        errors,
                        ["node", "code", "message"],
                        output_format=output,
                        title="Errors",
                    )
                success("Consistency check complete.")
        finally:
            try:
                tool.stop()
            except Exception:
                pass
    except Exception as e:
        handle_api_error(e)


@app.command()
def sources(
    ctx: typer.Context,
    dataset: str = typer.Argument(
        None, help="Dataset to find upstream sources for (omit for all project sources)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Find source datasets (nodes with no upstream dependencies).

    Without an argument, lists all root sources in the project.
    With a dataset argument, traces upstream from that dataset to find its sources.
    """
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        flow = proj.get_flow()
        graph_obj = flow.get_graph()

        if dataset:
            # Trace upstream from the given dataset to find its sources
            # Build reverse adjacency: child -> set of parents
            parents: dict[str, set[str]] = {}
            for node_id, node in graph_obj.nodes.items():
                for succ in node.get("successors", []):
                    parents.setdefault(succ, set()).add(node_id)

            # BFS upstream from target
            visited: set[str] = set()
            queue = [dataset]
            source_nodes: list[str] = []
            while queue:
                current = queue.pop(0)
                if current in visited:
                    continue
                visited.add(current)
                ups = parents.get(current, set())
                if not ups:
                    source_nodes.append(current)
                else:
                    queue.extend(ups)

            data = []
            for node_id in source_nodes:
                node = graph_obj.nodes.get(node_id, {})
                data.append(
                    {
                        "id": node_id,
                        "type": node.get("type", ""),
                        "ref": node.get("ref", node_id),
                    }
                )

            title = f"Sources of {dataset} ({project_key})"
        else:
            # Original behavior: all project root sources
            downstream_nodes: set[str] = set()
            for node_id, node in graph_obj.nodes.items():
                successors = node.get("successors", [])
                downstream_nodes.update(successors)

            data = []
            for node_id, node in graph_obj.nodes.items():
                if node_id not in downstream_nodes:
                    data.append(
                        {
                            "id": node_id,
                            "type": node.get("type", ""),
                            "ref": node.get("ref", node_id),
                        }
                    )

            title = f"Source Nodes ({project_key})"

        render(
            data,
            ["id", "type", "ref"],
            output_format=output,
            title=title,
        )
    except Exception as e:
        handle_api_error(e)


@app.command()
def successors(
    ctx: typer.Context,
    node: str = typer.Argument(help="Node ID to find successors for"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Show downstream successors of a flow node."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        flow = proj.get_flow()
        graph_obj = flow.get_graph()

        # Try graph_obj.get_successors() first, fall back to parsing nodes
        try:
            successor_ids = graph_obj.get_successors(node)
        except (AttributeError, TypeError):
            # Parse from graph data — look for "successors" list on the node
            node_data = graph_obj.nodes.get(node, {})
            successor_ids = node_data.get("successors", [])

        data = []
        for s_id in successor_ids:
            s_node = graph_obj.nodes.get(s_id, {})
            data.append(
                {
                    "id": s_id,
                    "type": s_node.get("type", ""),
                    "ref": s_node.get("ref", s_id),
                }
            )

        render(
            data,
            ["id", "type", "ref"],
            output_format=output,
            title=f"Successors of {node} ({project_key})",
        )
    except Exception as e:
        handle_api_error(e)
