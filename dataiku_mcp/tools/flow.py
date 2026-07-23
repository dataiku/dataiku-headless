"""Flow inspection utilities."""

from fastmcp import Context

from .. import mcp
from .utils.async_executor import run_blocking
from .utils.auth import get_dss_client
from .utils.serialization import columnar, compact_json, omit_empty
from .utils.validation import (
    require_allowed_value as _require_allowed_value,
    require_non_empty_string as _require_non_empty_string,
    require_positive_int as _require_positive_int,
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
            return node_type[len(prefix) :].lower()
    return node_type.lower()


# Above this size the ASCII tree stops being a readable orientation aid and just
# burns tokens; callers fall back to the flat nodes/edges lists.
_MAX_TREE_NODES = 300
# The tree emits one line per edge traversal with a depth-sized prefix, so a dense
# graph within the node ceiling can still render megabytes. Hard budget on the
# rendered text itself; past it the tree is omitted, not the nodes/edges.
_MAX_TREE_CHARS = 200_000
# Hard ceiling on the serialized response actually returned over MCP. The count
# ceilings alone are not enough: 512-char refs on 10,000 edges serialize past
# 10 MB. Measured on the final JSON string, so escaping cannot blow past it;
# past it the response degrades in stages (tree, then edges, then nodes) with
# explicit truncation metadata.
_MAX_RESPONSE_CHARS = 1_000_000
# Headroom kept while clipping so the truncation warnings added afterwards
# cannot push the final payload back over _MAX_RESPONSE_CHARS.
_RESPONSE_BUDGET_SLACK = 2_000
_DEFAULT_GRAPH_NODES = 1_000
_MAX_GRAPH_NODES = 2_000
_DEFAULT_GRAPH_EDGES = 3_000
_MAX_GRAPH_EDGES = 10_000
_MAX_FLOW_TEXT_CHARS = 512


def _clip_flow_text(value) -> str:
    text = "" if value is None else str(value)
    if len(text) <= _MAX_FLOW_TEXT_CHARS:
        return text
    return text[: _MAX_FLOW_TEXT_CHARS - 3] + "..."


class _TreeBudgetExceeded(Exception):
    """Raised internally when the rendered tree passes ``_MAX_TREE_CHARS``."""


def _render_flow_tree(nodes: dict, id_to_ref: dict, sources: list, title: str):
    """Render the flow as a plain-text DAG tree.

    ASCII-only on purpose: box-drawing glyphs double or triple in size under JSON
    string escaping, which would make any size budget dishonest about what is
    actually returned. Read top-down as build order: each source is a root, nesting
    is downstream dependency, sibling branches are parallel paths. A node shown as
    a leaf with `` (^)`` is a re-convergence point — already drawn upstream in this
    traversal, so it is not re-expanded (e.g. a join fed by two branches). A leaf
    marked `` (cycle)`` is a back-edge to a node still open on the current path,
    which a valid flow DAG never contains.

    Returns the tree text, or ``None`` when it would exceed ``_MAX_TREE_CHARS``.
    Cycle detection is NOT this function's job (rendering can abort mid-graph on
    the budget); see ``_has_cycle``.
    """
    lines = [f"Flow: {_clip_flow_text(title)}"]
    total_chars = len(lines[0])
    visited: set = set()
    on_path: set = set()

    def emit(line: str) -> None:
        nonlocal total_chars
        total_chars += len(line) + 1
        if total_chars > _MAX_TREE_CHARS:
            raise _TreeBudgetExceeded
        lines.append(line)

    def label(node_id: str) -> str:
        node = nodes.get(node_id, {})
        return (
            f"[{_short_type(node.get('type'))}] "
            f"{_clip_flow_text(id_to_ref.get(node_id, node_id))}"
        )

    def walk(node_id: str, prefix: str, is_last: bool) -> None:
        connector = "`-- " if is_last else "|-- "
        if node_id in on_path:
            # Back-edge to a node still open on this path: a cycle, not a join.
            emit(f"{prefix}{connector}{label(node_id)} (cycle)")
            return
        if node_id in visited:
            emit(f"{prefix}{connector}{label(node_id)} (^)")
            return
        emit(f"{prefix}{connector}{label(node_id)}")
        visited.add(node_id)
        on_path.add(node_id)
        children = [s for s in nodes[node_id].get("successors", []) if s in nodes]
        child_prefix = prefix + ("    " if is_last else "|   ")
        for index, child in enumerate(children):
            walk(child, child_prefix, index == len(children) - 1)
        on_path.discard(node_id)

    try:
        for index, source in enumerate(sources):
            walk(source, "", index == len(sources) - 1)
        # A valid DAG has at least one source. If malformed backend data contains a
        # cycle, still show every component once instead of returning only a title.
        for node_id in nodes:
            if node_id not in visited:
                walk(node_id, "", True)
    except _TreeBudgetExceeded:
        return None
    return "\n".join(lines)


def _has_cycle(nodes: dict) -> bool:
    """Whether the successor graph contains a cycle (iterative DFS, no string work).

    Deliberately independent of tree rendering: the renderer can abort mid-graph on
    its character budget, so any cycle flag accumulated there would depend on
    traversal order. This pass always sees the whole (selected) graph.
    """
    visited: set = set()
    on_stack: set = set()
    for root in nodes:
        if root in visited:
            continue
        visited.add(root)
        on_stack.add(root)
        stack = [(root, iter(nodes[root].get("successors", [])))]
        while stack:
            node_id, successors = stack[-1]
            advanced = False
            for successor in successors:
                if successor not in nodes:
                    continue
                if successor in on_stack:
                    return True
                if successor not in visited:
                    visited.add(successor)
                    on_stack.add(successor)
                    stack.append(
                        (successor, iter(nodes[successor].get("successors", [])))
                    )
                    advanced = True
                    break
            if not advanced:
                stack.pop()
                on_stack.discard(node_id)
    return False


def _get_zone_nodes(flow, zone: str) -> dict:
    """Return the graph nodes of the named flow zone (by id or name).

    Zone membership is resolved server-side via ``DSSFlowZone.get_graph()`` because
    DSS owns the semantics: the default zone implicitly contains everything not
    assigned to another zone, so its explicit item list can be empty while the
    zone covers most of the flow. Reconstructing membership from raw zone items
    would miss that, along with shared and foreign-project items.
    """
    zones = flow.list_zones()
    # Ids are authoritative and unique, so an exact id match wins outright; a zone
    # NAME equal to another zone's ID must not shadow it. Names are only labels
    # and can collide, so a name match is honored only when it is unambiguous.
    match = next((z for z in zones if z.id == zone), None)
    if match is None:
        name_matches = [z for z in zones if z.name == zone]
        if len(name_matches) > 1:
            candidates = sorted(
                f"{_clip_flow_text(z.name)} (id={_clip_flow_text(z.id)})"
                for z in name_matches[:50]
            )
            raise ValueError(
                f"Ambiguous flow zone name '{zone}': matches {candidates}. "
                "Pass the zone id instead."
            )
        if name_matches:
            match = name_matches[0]
    if match is None:
        available = sorted(
            f"{_clip_flow_text(z.name)} (id={_clip_flow_text(z.id)})"
            for z in zones[:50]
        )
        suffix = " (first 50 shown)" if len(zones) > 50 else ""
        raise ValueError(
            f"Unknown flow zone '{zone}'. Available zones{suffix}: {available}"
        )
    return match.get_graph().nodes


def _build_flow_graph(
    project_key: str,
    nodes: dict,
    *,
    max_nodes: int,
    max_edges: int,
) -> dict:
    total_node_count = len(nodes)
    selected_ids = list(nodes)[:max_nodes]
    selected = {node_id: nodes[node_id] for node_id in selected_ids}
    id_to_ref = {node_id: node.get("ref", node_id) for node_id, node in nodes.items()}
    # Full-graph truth, computed before any clipping: node_count, edge_count and
    # source_count always describe the whole (zone-scoped) graph, never the subset
    # that survives the count ceilings or the response size budget.
    total_edge_count = 0
    full_has_predecessor: set = set()
    for node in nodes.values():
        for successor in node.get("successors", []):
            if successor in nodes:
                total_edge_count += 1
                full_has_predecessor.add(successor)
    total_source_count = sum(
        1 for node_id in nodes if node_id not in full_has_predecessor
    )
    has_predecessor: set = set()
    edges: list = []
    for node_id, node in selected.items():
        for successor in node.get("successors", []):
            if successor in selected:
                has_predecessor.add(successor)
                if len(edges) < max_edges:
                    edges.append(
                        [
                            _clip_flow_text(id_to_ref[node_id]),
                            _clip_flow_text(id_to_ref[successor]),
                        ]
                    )
    # Roots for rendering the returned subset's tree; not reported as a count.
    sources = [node_id for node_id in selected if node_id not in has_predecessor]

    truncated_nodes = total_node_count > len(selected)
    truncated_edges = total_edge_count > len(edges)
    result = {
        "project_key": project_key,
        "node_count": total_node_count,
        "returned_node_count": len(selected),
        "edge_count": total_edge_count,
        "returned_edge_count": len(edges),
        "source_count": total_source_count,
        "nodes": [
            [_clip_flow_text(node.get("ref")), _short_type(node.get("type"))]
            for node in selected.values()
        ],
        "edges": edges,
    }
    warnings = []
    if truncated_nodes:
        warnings.append(
            f"nodes: returning {len(selected)} of {total_node_count}; "
            "increase max_nodes within the documented ceiling or scope by zone"
        )
    if truncated_edges:
        warnings.append(
            f"edges: returning {len(edges)} of {total_edge_count}; "
            "increase max_edges within the documented ceiling or scope by zone"
        )
    if truncated_nodes or truncated_edges:
        result["truncated"] = True
        warnings.append("tree omitted because the returned graph is partial")
    elif total_node_count > _MAX_TREE_NODES:
        warnings.append("tree omitted for a large flow; use nodes/edges")
    else:
        tree = _render_flow_tree(selected, id_to_ref, sources, project_key)
        if tree is None:
            warnings.append(
                f"tree omitted because its rendering exceeds {_MAX_TREE_CHARS} "
                "characters on this dense flow; use nodes/edges"
            )
        else:
            result["tree"] = tree
    # Full-graph pass, independent of whether (or how much of) the tree rendered,
    # so the warning does not depend on traversal order. Same text either way; the
    # tree, when present, additionally marks the back-edges with (cycle).
    if _has_cycle(selected):
        warnings.append(
            "flow contains a cycle; a valid flow is acyclic, "
            "the backend data may be malformed"
        )
    if warnings:
        result["warnings"] = warnings
    return omit_empty(result)


def _fit_response_to_budget(result: dict) -> str:
    """Serialize ``result``, degrading in stages until it fits ``_MAX_RESPONSE_CHARS``.

    The budget is measured on the final JSON string — what is actually returned —
    so escaping cannot blow past it. Degradation order: drop the tree, then clip
    the edges list, then the nodes list (each keeping a stable prefix and leaving
    the original counts plus explicit truncation metadata in place), then clip any
    remaining unbounded echoed strings such as ``project_key``. A final wholesale
    backstop makes the ceiling hold for ANY input.
    """
    payload = compact_json(result)
    if len(payload) <= _MAX_RESPONSE_CHARS:
        return payload
    budget = _MAX_RESPONSE_CHARS - _RESPONSE_BUDGET_SLACK
    warnings = result.setdefault("warnings", [])
    result["truncated"] = True
    if result.pop("tree", None) is not None:
        warnings.append("tree omitted to fit the response size budget")
    payload = compact_json(result)
    for field, count_key in (
        ("edges", "returned_edge_count"),
        ("nodes", "returned_node_count"),
    ):
        if len(payload) <= budget:
            break
        items = result.get(field) or []
        kept = len(items)
        while len(payload) > budget and items:
            items = items[: len(items) // 2]
            result[field] = items
            result[count_key] = len(items)
            payload = compact_json(result)
        if len(items) < kept:
            warnings.append(
                f"{field}: clipped to {len(items)} of {kept} to fit the "
                "response size budget; scope by zone for the full graph"
            )
            payload = compact_json(result)
    if len(payload) > budget:
        # Only echoed inputs (project_key) remain unbounded at this point; clip
        # every top-level string so no caller-supplied value can hold the line.
        for key, value in list(result.items()):
            if isinstance(value, str) and len(value) > _MAX_FLOW_TEXT_CHARS:
                result[key] = _clip_flow_text(value)
                warnings.append(
                    f"{key}: clipped to {_MAX_FLOW_TEXT_CHARS} characters to fit "
                    "the response size budget"
                )
        payload = compact_json(result)
    if len(payload) > _MAX_RESPONSE_CHARS:
        # Unreachable by construction (every field above is bounded), kept as a
        # provable last resort: the payload is ASCII (ensure_ascii), so escaping
        # it into the envelope string at most doubles it; halving the prefix
        # budget keeps the envelope under the ceiling for any input whatsoever.
        prefix = payload[: (_MAX_RESPONSE_CHARS // 2) - 200]
        payload = compact_json(
            {
                "truncated": True,
                "warnings": [
                    "response truncated wholesale to fit the response size budget"
                ],
                "response_prefix": prefix,
            }
        )
    return payload


@mcp.tool()
async def get_flow_graph(
    project_key: str,
    ctx: Context,
    zone: str | None = None,
    max_nodes: int = _DEFAULT_GRAPH_NODES,
    max_edges: int = _DEFAULT_GRAPH_EDGES,
) -> str:
    """Get the whole flow in one call: nodes, edges, and an ASCII build tree.

    Prefer this over walking the flow item-by-item. The ``tree`` encodes the flow's
    shape: each source dataset is a root, nesting is downstream build order, sibling
    branches are parallel paths, and a leaf marked `` (^)`` is a re-convergence point
    (a node already drawn upstream, e.g. a join fed by two branches) shown once and not
    re-expanded. A leaf marked `` (cycle)`` is a back-edge closing a cycle, which a
    valid flow never contains; cycles are always reported in ``warnings`` even when
    the tree is omitted. ``nodes`` are ``[ref, short_type]`` pairs and ``edges`` are
    ``[from_ref, to_ref]`` pairs. Count semantics: ``node_count``, ``edge_count`` and
    ``source_count`` always describe the full (zone-scoped) graph, while
    ``returned_node_count``/``returned_edge_count`` describe exactly what this
    response carries after ceilings and budgets. Pass ``zone`` to scope to a single
    flow zone (by id or unambiguous name, including the default zone); on a very
    large or very dense flow the tree is omitted (see ``warnings``) and you rely on
    nodes/edges. Responses are bounded to at most 2,000 nodes and 10,000 edges, and
    the serialized response is capped at 1,000,000 characters, degrading tree first,
    then edges, then nodes, then oversized echoed strings, always with explicit
    truncation metadata; use ``zone`` to narrow a graph or raise the count defaults
    within those hard ceilings.
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    if zone is not None:
        zone = _require_non_empty_string(zone, "zone")
    max_nodes = _require_positive_int(max_nodes, "max_nodes")
    max_edges = _require_positive_int(max_edges, "max_edges")
    if max_nodes > _MAX_GRAPH_NODES:
        raise ValueError(f"'max_nodes' must be <= {_MAX_GRAPH_NODES}")
    if max_edges > _MAX_GRAPH_EDGES:
        raise ValueError(f"'max_edges' must be <= {_MAX_GRAPH_EDGES}")
    client = get_dss_client()
    await ctx.info(
        f"Building flow graph for {project_key}"
        + (f" (zone={zone})" if zone else "")
        + "..."
    )

    def _run():
        project = client.get_project(project_key)
        flow = project.get_flow()
        if zone is not None:
            nodes = _get_zone_nodes(flow, zone)
        else:
            nodes = flow.get_graph().nodes
        result = _build_flow_graph(
            project_key,
            nodes,
            max_nodes=max_nodes,
            max_edges=max_edges,
        )
        return _fit_response_to_budget(result)

    return await run_blocking(_run)


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
