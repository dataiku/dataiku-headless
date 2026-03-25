"""dku flow — graph, zones, propagate, check, sources, successors."""

from __future__ import annotations

import json

import typer

from dku_cli.errors import handle_api_error
from dku_cli.helpers import get_client_from_ctx, resolve_project
from dku_cli.output import render, render_raw, resolve_output_format, success

app = typer.Typer(help="Inspect DSS project flow.")


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
            print(json.dumps(graph_obj.data, indent=2, default=str))
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
def zones(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """List flow zones."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        flow = proj.get_flow()
        zone_list = flow.list_zones()

        data = []
        for z in zone_list:
            data.append(
                {
                    "id": z.id,
                    "name": z.name,
                }
            )

        render(
            data,
            ["id", "name"],
            output_format=output,
            title=f"Flow Zones ({project_key})",
        )
    except Exception as e:
        handle_api_error(e)


@app.command("create-zone")
def create_zone(
    ctx: typer.Context,
    name: str = typer.Argument(help="Zone name"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a new flow zone."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        flow = proj.get_flow()
        zone = flow.create_zone(name)
        success(f"Created zone '{name}' (id: {zone.id})")
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
            render_raw(state, output_format=output)
            success("Consistency check complete.")
        finally:
            tool.stop()
    except Exception as e:
        handle_api_error(e)


@app.command()
def sources(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output format"),
) -> None:
    """Find source datasets (nodes with no upstream dependencies)."""
    project_key = resolve_project(project)
    output = resolve_output_format(output)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        flow = proj.get_flow()
        graph_obj = flow.get_graph()

        # Build set of all nodes that are downstream of something
        downstream_nodes: set[str] = set()
        for node_id, node in graph_obj.nodes.items():
            successors = node.get("successors", [])
            downstream_nodes.update(successors)

        # Sources are nodes not in the downstream set
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

        render(
            data,
            ["id", "type", "ref"],
            output_format=output,
            title=f"Source Nodes ({project_key})",
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
