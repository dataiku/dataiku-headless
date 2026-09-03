# Copyright 2026 Dataiku
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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


_MAX_GRAPH_NODES = 2_000
_MAX_GRAPH_EDGES = 5_000
_RESPONSE_CHAR_LIMIT = 1_000_000
_RESPONSE_CHAR_SLACK = 2_000


def _group_by_type(pairs) -> dict:
    """Group ``(ref, short_type)`` pairs into ``{short_type: [ref, ...]}``."""
    grouped: dict = {}
    for ref, short_type in pairs:
        grouped.setdefault(short_type, []).append(ref)
    return grouped


def _flatten_by_type(grouped: dict) -> list:
    """Inverse of ``_group_by_type``, preserving group order."""
    return [(ref, short_type) for short_type, refs in grouped.items() for ref in refs]


def _has_cycle(nodes: dict) -> bool:
    """Return whether the successor graph contains a cycle."""
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
    """Return the graph nodes for a flow zone by id or name."""
    zones = flow.list_zones()
    # Exact id match wins over a same-named zone because names can collide.
    match = next((z for z in zones if z.id == zone), None)
    if match is None:
        name_matches = [z for z in zones if z.name == zone]
        if len(name_matches) > 1:
            candidates = sorted(f"{z.name} (id={z.id})" for z in name_matches[:50])
            raise ValueError(
                f"Ambiguous flow zone name '{zone}': matches {candidates}. "
                "Pass the zone id instead."
            )
        if name_matches:
            match = name_matches[0]
    if match is None:
        available = sorted(f"{z.name} (id={z.id})" for z in zones[:50])
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
    total_edge_count = 0
    full_has_predecessor: set = set()
    for node in nodes.values():
        for successor in node.get("successors", []):
            if successor in nodes:
                total_edge_count += 1
                full_has_predecessor.add(successor)
    # Keep named sources because clipped edges can no longer identify roots reliably.
    sources = [
        node.get("ref", node_id)
        for node_id, node in nodes.items()
        if node_id not in full_has_predecessor
    ]
    edges: list = []
    for node_id, node in selected.items():
        for successor in node.get("successors", []):
            if successor in selected:
                if len(edges) < max_edges:
                    edges.append(
                        [
                            selected[node_id].get("ref", node_id),
                            selected[successor].get("ref", successor),
                        ]
                    )
    truncated_nodes = total_node_count > len(selected)
    truncated_edges = total_edge_count > len(edges)
    result = {
        "project_key": project_key,
        "node_count": total_node_count,
        "returned_node_count": len(selected),
        "edge_count": total_edge_count,
        "returned_edge_count": len(edges),
        "source_count": len(sources),
        "sources": sources,
        "nodes_by_type": _group_by_type(
            (node.get("ref", node_id), _short_type(node.get("type")))
            for node_id, node in selected.items()
        ),
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
    if _has_cycle(nodes):
        warnings.append(
            "flow contains a cycle; a valid flow is acyclic, "
            "the backend data may be malformed"
        )
    if warnings:
        result["warnings"] = warnings
    return omit_empty(result)


def _clip_to_budget(result: dict, budget: int, label: str, items: list, write) -> str:
    """Halve ``items`` until ``result`` serializes within ``budget``."""
    kept = len(items)
    payload = compact_json(result)
    while len(payload) > budget and items:
        items = items[: len(items) // 2]
        write(items)
        payload = compact_json(result)
    if len(items) < kept:
        result["warnings"].append(
            f"{label}: clipped to {len(items)} of {kept} to fit the response size "
            "budget; use the relevant list/get tools for deeper inspection"
        )
        payload = compact_json(result)
    return payload


def _fit_response_to_budget(result: dict) -> str:
    """Serialize a flow-graph result within the response-size cap."""
    payload = compact_json(result)
    if len(payload) <= _RESPONSE_CHAR_LIMIT:
        return payload
    budget = _RESPONSE_CHAR_LIMIT - _RESPONSE_CHAR_SLACK
    result.setdefault("warnings", [])
    result["truncated"] = True

    def write_edges(kept: list) -> None:
        result["edges"] = kept
        result["returned_edge_count"] = len(kept)

    def write_nodes(kept: list) -> None:
        result["nodes_by_type"] = _group_by_type(kept)
        result["returned_node_count"] = len(kept)

    def write_sources(kept: list) -> None:
        result["sources"] = kept

    # Clip edges first and sources last.
    for label, items, write in (
        ("edges", result.get("edges") or [], write_edges),
        ("nodes", _flatten_by_type(result.get("nodes_by_type") or {}), write_nodes),
        ("sources", result.get("sources") or [], write_sources),
    ):
        payload = _clip_to_budget(result, budget, label, items, write)
        if len(payload) <= budget:
            break
    if len(payload) > _RESPONSE_CHAR_LIMIT:
        prefix = payload[: (_RESPONSE_CHAR_LIMIT // 2) - 200]
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
    max_nodes: int = 1_000,
    max_edges: int = 2_000,
) -> str:
    """Get a flow graph: sources, node refs by type, edges; optionally zone-scoped."""
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
