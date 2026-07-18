"""Flow inspection utilities."""

from fastmcp import Context

from .. import mcp
from .utils.async_executor import run_blocking
from .utils.auth import get_dss_client
from .utils.serialization import columnar, compact_json, omit_empty
from .utils.validation import (
    require_allowed_value as _require_allowed_value,
    require_non_empty_string as _require_non_empty_string,
)

_TAGGABLE_TYPES = {
    "dataset",
    "recipe",
    "managed_folder",
    "agent",
    "retrieval_augmented_llm",
    "knowledge_bank",
}
_METADATA_OBJECT_TYPES = _TAGGABLE_TYPES | {"saved_model"}


def _get_metadata_settings(project, object_type: str, object_name: str):
    if object_type == "dataset":
        return project.get_dataset(object_name).get_settings()
    if object_type == "recipe":
        return project.get_recipe(object_name).get_settings()
    if object_type == "managed_folder":
        return project.get_managed_folder(object_name).get_settings()
    if object_type == "saved_model":
        return project.get_saved_model(object_name).get_settings()
    if object_type == "agent":
        return project.get_agent(object_name).get_settings()
    if object_type == "retrieval_augmented_llm":
        return project.get_retrieval_augmented_llm(object_name).get_settings()
    if object_type == "knowledge_bank":
        return project.get_knowledge_bank(object_name).get_settings()


def _read_metadata(settings, object_type: str) -> dict:
    if object_type in _TAGGABLE_TYPES:
        meta = {
            "short_description": settings.short_description,
            "description": settings.description,
            "tags": settings.tags,
            "custom_fields": settings.custom_fields,
        }
    else:
        raw = settings.get_raw()
        meta = {
            "short_description": raw.get("shortDesc"),
            "description": raw.get("description"),
            "tags": raw.get("tags", []),
            "custom_fields": raw.get("customFields"),
        }
    return omit_empty(meta)


def _short_type(node_type):
    if not node_type:
        return node_type
    for prefix in ("COMPUTABLE_", "RUNNABLE_"):
        if node_type.startswith(prefix):
            return node_type[len(prefix):].lower()
    return node_type.lower()


def _simplify_flow_node(node: dict) -> list:
    return [node.get("ref"), _short_type(node.get("type"))]


# Above this size the ASCII tree stops being a readable orientation aid and just
# burns tokens; callers fall back to the flat nodes/edges lists.
_MAX_TREE_NODES = 300


def _render_flow_tree(nodes: dict, id_to_ref: dict, sources: list, title: str) -> str:
    """Render the flow as a plain-text DAG tree (no Rich markup).

    Read top-down as build order: each source is a root, nesting is downstream
    dependency, sibling branches are parallel paths. A node shown as a leaf with
    `` (↑)`` is a re-convergence point — already drawn upstream in this traversal,
    so it is not re-expanded (e.g. a join fed by two branches).
    """
    lines = [f"Flow: {title}"]
    visited: set = set()

    def label(node_id: str) -> str:
        node = nodes.get(node_id, {})
        return f"[{_short_type(node.get('type'))}] {id_to_ref.get(node_id, node_id)}"

    def walk(node_id: str, prefix: str, is_last: bool) -> None:
        connector = "└── " if is_last else "├── "
        already = node_id in visited
        lines.append(f"{prefix}{connector}{label(node_id)}" + (" (↑)" if already else ""))
        if already:
            return
        visited.add(node_id)
        children = [s for s in nodes[node_id].get("successors", []) if s in nodes]
        child_prefix = prefix + ("    " if is_last else "│   ")
        for index, child in enumerate(children):
            walk(child, child_prefix, index == len(children) - 1)

    for index, source in enumerate(sources):
        walk(source, "", index == len(sources) - 1)
    return "\n".join(lines)


def _filter_nodes_to_zone(flow, nodes: dict, zone: str) -> dict:
    """Restrict ``nodes`` to the members of the named flow zone (by id or name)."""
    zones = [z.get_settings().get_raw() for z in flow.list_zones()]
    match = next(
        (z for z in zones if z.get("id") == zone or z.get("name") == zone), None
    )
    if match is None:
        available = sorted(f"{z.get('name')} (id={z.get('id')})" for z in zones)
        raise ValueError(f"Unknown flow zone '{zone}'. Available zones: {available}")
    member_ids = {item.get("objectId") for item in match.get("items", [])}
    return {
        node_id: node
        for node_id, node in nodes.items()
        if node.get("ref") in member_ids or node_id in member_ids
    }


def _build_flow_graph(project_key: str, nodes: dict) -> dict:
    id_to_ref = {node_id: node.get("ref", node_id) for node_id, node in nodes.items()}
    has_predecessor: set = set()
    edges: list = []
    for node_id, node in nodes.items():
        for successor in node.get("successors", []):
            if successor in nodes:
                has_predecessor.add(successor)
                edges.append([id_to_ref[node_id], id_to_ref[successor]])
    sources = [node_id for node_id in nodes if node_id not in has_predecessor]

    node_count = len(nodes)
    result = {
        "project_key": project_key,
        "node_count": node_count,
        "source_count": len(sources),
        "nodes": [_simplify_flow_node(node) for node in nodes.values()],
        "edges": edges,
    }
    if node_count > _MAX_TREE_NODES:
        result["warnings"] = ["tree omitted for very large flow; use nodes/edges"]
    else:
        result["tree"] = _render_flow_tree(nodes, id_to_ref, sources, project_key)
    return omit_empty(result)


@mcp.tool()
async def get_flow_graph(
    project_key: str,
    ctx: Context,
    zone: str | None = None,
) -> str:
    """Get the whole flow in one call: nodes, edges, and an ASCII build tree.

    Prefer this over walking the flow item-by-item. The ``tree`` encodes the flow's
    shape: each source dataset is a root, nesting is downstream build order, sibling
    branches are parallel paths, and a leaf marked `` (↑)`` is a re-convergence point
    (a node already drawn upstream, e.g. a join fed by two branches) shown once and not
    re-expanded. ``nodes`` are ``[ref, short_type]`` pairs and ``edges`` are
    ``[from_ref, to_ref]`` pairs. Pass ``zone`` to scope to a single flow zone; on a very
    large flow the tree is omitted (see ``warnings``) and you rely on nodes/edges.
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    if zone is not None:
        zone = _require_non_empty_string(zone, "zone")
    await ctx.info(
        f"Building flow graph for {project_key}"
        + (f" (zone={zone})" if zone else "")
        + "..."
    )

    def _run():
        project = get_dss_client().get_project(project_key)
        flow = project.get_flow()
        nodes = flow.get_graph().nodes
        if zone is not None:
            nodes = _filter_nodes_to_zone(flow, nodes, zone)
        return _build_flow_graph(project_key, nodes)

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def list_flow_zones(project_key: str, ctx: Context) -> str:
    """List the flow zones in the project with their items."""
    project_key = _require_non_empty_string(project_key, "project_key")
    await ctx.info(f"Listing flow zones in {project_key}...")

    def _run():
        project = get_dss_client().get_project(project_key)
        flow = project.get_flow()
        return [zone.get_settings().get_raw() for zone in flow.list_zones()]

    zones_raw = await run_blocking(_run)
    return compact_json(
        {
            "zones": columnar(
                [
                    {
                        "zone_id": zone_raw.get("id"),
                        "name": zone_raw.get("name"),
                        "description": zone_raw.get("description"),
                        "items": [
                            {
                                "object_type": item.get("objectType"),
                                "object_id": item.get("objectId"),
                            }
                            for item in zone_raw.get("items", [])
                        ],
                    }
                    for zone_raw in zones_raw
                ],
                ["zone_id", "name", "description", "items"],
            )
        }
    )


@mcp.tool()
async def get_flow_object_metadata(
    project_key: str,
    object_type: str,
    object_name: str,
    ctx: Context,
) -> str:
    """Get metadata for a flow object."""
    _require_allowed_value(object_type, "object_type", _METADATA_OBJECT_TYPES)
    await ctx.info(
        f"Fetching metadata for {object_type} '{object_name}' in {project_key}..."
    )

    def _run():
        project = get_dss_client().get_project(project_key)
        settings = _get_metadata_settings(project, object_type, object_name)
        return _read_metadata(settings, object_type)

    return compact_json(await run_blocking(_run))
