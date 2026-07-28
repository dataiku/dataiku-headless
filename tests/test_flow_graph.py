"""Tests for the ``flow.get_flow_graph`` programmatic graph tool.

These never touch the network: ``get_dss_client`` is replaced by a fake client
returning a fake project whose flow is driven from canned Python objects. The
tool under test returns the whole flow in one call as ``node_types`` plus
``edges``, with zone filtering, clipping metadata, and response-budget guards.
"""

import asyncio
import json

import pytest

from dataiku_mcp.tools import flow


class FakeCtx:
    def __init__(self):
        self.infos = []

    async def info(self, message, **kwargs):
        self.infos.append(message)


class FakeGraph:
    def __init__(self, nodes):
        self.nodes = nodes


class FakeZone:
    """Mirrors dataikuapi's DSSFlowZone: id/name properties plus get_graph()."""

    def __init__(self, zone_id, name, nodes=None):
        self.id = zone_id
        self.name = name
        self._nodes = nodes or {}

    def get_graph(self):
        return FakeGraph(self._nodes)


class FakeFlow:
    def __init__(self, nodes, zones):
        self._nodes = nodes
        self._zones = zones

    def get_graph(self):
        return FakeGraph(self._nodes)

    def list_zones(self):
        return list(self._zones)


class FakeProject:
    def __init__(self, key, *, nodes=None, zones=None):
        self.project_key = key
        self._nodes = nodes or {}
        self._zones = zones or []

    def get_flow(self):
        return FakeFlow(self._nodes, self._zones)


class FakeClient:
    def __init__(self, project):
        self._project = project

    def get_project(self, key):
        return self._project


def run(coro):
    return asyncio.run(coro)


def bind(monkeypatch, project):
    client = FakeClient(project)
    monkeypatch.setattr(flow, "get_dss_client", lambda: client)


def flow_graph(project_key="PROJ", **kwargs):
    return json.loads(run(flow.get_flow_graph(project_key, FakeCtx(), **kwargs)))


def _dataset(ref, successors=(), predecessors=()):
    return {
        "type": "COMPUTABLE_DATASET",
        "ref": ref,
        "predecessors": list(predecessors),
        "successors": list(successors),
    }


def _recipe(ref, successors=(), predecessors=()):
    return {
        "type": "RUNNABLE_RECIPE",
        "ref": ref,
        "predecessors": list(predecessors),
        "successors": list(successors),
    }


def diamond_nodes():
    return {
        "orders": _dataset("orders", successors=["join_recipe"]),
        "customers": _dataset("customers", successors=["join_recipe"]),
        "join_recipe": _recipe(
            "join_recipe",
            predecessors=["orders", "customers"],
            successors=["joined"],
        ),
        "joined": _dataset(
            "joined", predecessors=["join_recipe"], successors=["enrich_recipe"]
        ),
        "enrich_recipe": _recipe(
            "enrich_recipe", predecessors=["joined"], successors=["final"]
        ),
        "final": _dataset("final", predecessors=["enrich_recipe"]),
    }


_CYCLE_WARNING = (
    "flow contains a cycle; a valid flow is acyclic, the backend data may be malformed"
)


def test_flow_graph_node_types_and_edges_on_diamond(monkeypatch):
    bind(monkeypatch, FakeProject("PROJ", nodes=diamond_nodes()))

    res = flow_graph()

    assert res["node_count"] == 6
    assert res["source_count"] == 2
    assert res["node_types"] == {
        "orders": "dataset",
        "customers": "dataset",
        "join_recipe": "recipe",
        "joined": "dataset",
        "enrich_recipe": "recipe",
        "final": "dataset",
    }
    assert {tuple(edge) for edge in res["edges"]} == {
        ("orders", "join_recipe"),
        ("customers", "join_recipe"),
        ("join_recipe", "joined"),
        ("joined", "enrich_recipe"),
        ("enrich_recipe", "final"),
    }


def test_flow_graph_zone_filter(monkeypatch):
    nodes = diamond_nodes()
    zone_nodes = {key: nodes[key] for key in ("orders", "join_recipe", "joined")}
    zones = [FakeZone("zone_prep", "prep", zone_nodes)]
    bind(monkeypatch, FakeProject("PROJ", nodes=nodes, zones=zones))

    res = flow_graph(zone="prep")

    assert res["node_count"] == 3
    assert res["node_types"] == {
        "orders": "dataset",
        "join_recipe": "recipe",
        "joined": "dataset",
    }
    assert {tuple(edge) for edge in res["edges"]} == {
        ("orders", "join_recipe"),
        ("join_recipe", "joined"),
    }
    assert res["source_count"] == 1


def test_flow_graph_zone_resolves_by_id(monkeypatch):
    nodes = diamond_nodes()
    zones = [FakeZone("zone_prep", "prep", {"orders": nodes["orders"]})]
    bind(monkeypatch, FakeProject("PROJ", nodes=nodes, zones=zones))

    assert flow_graph(zone="zone_prep")["node_count"] == 1


def test_flow_graph_zone_id_match_beats_name_shadowing(monkeypatch):
    nodes = diamond_nodes()
    zones = [
        FakeZone("first-id", "target", {"orders": nodes["orders"]}),
        FakeZone("target", "other", {"final": nodes["final"]}),
    ]
    bind(monkeypatch, FakeProject("PROJ", nodes=nodes, zones=zones))

    assert flow_graph(zone="target")["node_types"] == {"final": "dataset"}


def test_flow_graph_ambiguous_zone_name_is_rejected(monkeypatch):
    nodes = diamond_nodes()
    zones = [
        FakeZone("z1", "dup", {"orders": nodes["orders"]}),
        FakeZone("z2", "dup", {"final": nodes["final"]}),
    ]
    bind(monkeypatch, FakeProject("PROJ", nodes=nodes, zones=zones))

    with pytest.raises(ValueError, match="Ambiguous flow zone name 'dup'"):
        flow_graph(zone="dup")


def test_flow_graph_default_zone_uses_server_side_membership(monkeypatch):
    nodes = diamond_nodes()
    zones = [FakeZone("default", "Default zone", nodes)]
    bind(monkeypatch, FakeProject("PROJ", nodes={}, zones=zones))

    res = flow_graph(zone="default")

    assert res["node_count"] == 6
    assert res["source_count"] == 2
    assert len(res["edges"]) == 5


def test_flow_graph_unknown_zone_errors(monkeypatch):
    zones = [FakeZone("zone_prep", "prep")]
    bind(monkeypatch, FakeProject("PROJ", nodes=diamond_nodes(), zones=zones))

    with pytest.raises(ValueError, match="Unknown flow zone 'nope'"):
        flow_graph(zone="nope")


def test_flow_graph_node_and_edge_limits_are_explicit(monkeypatch):
    nodes = {
        "a": _dataset("a", successors=["b", "c"]),
        "b": _dataset("b", predecessors=["a"]),
        "c": _dataset("c", predecessors=["a"]),
    }
    bind(monkeypatch, FakeProject("PROJ", nodes=nodes))

    res = flow_graph(max_nodes=2, max_edges=1)

    assert res["node_count"] == 3
    assert res["returned_node_count"] == 2
    assert res["edge_count"] == 2
    assert res["returned_edge_count"] == 1
    assert res["truncated"] is True
    assert res["warnings"] == [
        "nodes: returning 2 of 3; increase max_nodes within the documented ceiling or scope by zone",
        "edges: returning 1 of 2; increase max_edges within the documented ceiling or scope by zone",
    ]


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"max_nodes": 2001}, "max_nodes.*<= 2000"),
        ({"max_edges": 2001}, "max_edges.*<= 2000"),
        ({"max_edges": 0}, "max_edges.*>= 1"),
    ],
)
def test_flow_graph_rejects_unbounded_limits(monkeypatch, kwargs, message):
    bind(monkeypatch, FakeProject("PROJ"))
    with pytest.raises(ValueError, match=message):
        flow_graph(**kwargs)


def test_flow_graph_flags_cycle(monkeypatch):
    nodes = {
        "a": _dataset("a", successors=["b"], predecessors=["b"]),
        "b": _dataset("b", successors=["a"], predecessors=["a"]),
    }
    bind(monkeypatch, FakeProject("PROJ", nodes=nodes))

    res = flow_graph()

    assert _CYCLE_WARNING in res["warnings"]


def test_flow_graph_cycle_warning_uses_full_graph_not_returned_subset(monkeypatch):
    nodes = {
        "n0": _dataset("n0"),
        "n1": _dataset("n1"),
        "n2": _dataset("n2", successors=["n3"], predecessors=["n4"]),
        "n3": _dataset("n3", successors=["n4"], predecessors=["n2"]),
        "n4": _dataset("n4", successors=["n2"], predecessors=["n3"]),
    }
    bind(monkeypatch, FakeProject("PROJ", nodes=nodes))

    res = flow_graph(max_nodes=2)

    assert res["returned_node_count"] == 2
    assert _CYCLE_WARNING in res["warnings"]


def test_flow_graph_reconvergence_does_not_warn_about_cycles(monkeypatch):
    bind(monkeypatch, FakeProject("PROJ", nodes=diamond_nodes()))

    res = flow_graph()

    assert "warnings" not in res


def test_flow_graph_response_is_capped_even_with_maximal_refs(monkeypatch):
    inputs = [f"in{i:03d}".ljust(512, "x") for i in range(44)]
    recipes = [f"r{i:03d}".ljust(512, "y") for i in range(44)]
    outputs = [f"out{i:03d}".ljust(512, "z") for i in range(44)]
    nodes = {}
    for ref in inputs:
        nodes[ref] = _dataset(ref, successors=list(recipes))
    for index, ref in enumerate(recipes):
        nodes[ref] = _recipe(
            ref, predecessors=list(inputs), successors=[outputs[index]]
        )
    for index, ref in enumerate(outputs):
        nodes[ref] = _dataset(ref, predecessors=[recipes[index]])

    bind(monkeypatch, FakeProject("PROJ", nodes=nodes))

    raw = run(flow.get_flow_graph("PROJ", FakeCtx(), max_edges=2_000))
    res = json.loads(raw)

    assert len(raw) <= 1_000_000
    assert res["node_count"] == 132
    assert res["edge_count"] == 1_980
    assert res["truncated"] is True
    assert res["returned_edge_count"] == len(res["edges"])
    assert res["returned_edge_count"] < 1_980
    assert any("response size budget" in warning for warning in res["warnings"])


def test_flow_graph_json_escaping_cannot_blow_the_response_cap(monkeypatch):
    nodes = {f"star{i:04d}": _dataset(("★" * 507) + f"{i:04d}") for i in range(1200)}
    bind(monkeypatch, FakeProject("PROJ", nodes=nodes))

    raw = run(flow.get_flow_graph("PROJ", FakeCtx(), max_nodes=1200))
    res = json.loads(raw)

    assert len(raw) <= 1_000_000
    assert res["truncated"] is True
    if "response_prefix" in res:
        assert res["warnings"] == [
            "response truncated wholesale to fit the response size budget"
        ]
    else:
        assert res["node_count"] == 1200
        assert res["returned_node_count"] == len(res["node_types"])
        assert any("node_types: clipped" in warning for warning in res["warnings"])


def test_flow_graph_pathological_project_key_cannot_break_the_cap(monkeypatch):
    bind(monkeypatch, FakeProject("PROJ", nodes={}))

    raw = run(flow.get_flow_graph("K" * 1_000_000, FakeCtx()))
    res = json.loads(raw)

    assert len(raw) <= 1_000_000
    assert res["truncated"] is True
    assert res["warnings"] == [
        "response truncated wholesale to fit the response size budget"
    ]
    assert "response_prefix" in res


def test_flow_graph_source_count_is_full_graph_truth_under_clipping(monkeypatch):
    count = 2_001
    refs = [f"iso{i:04d}".ljust(512, "s") for i in range(count)]
    nodes = {ref: _dataset(ref) for ref in refs}
    bind(monkeypatch, FakeProject("PROJ", nodes=nodes))

    raw = run(flow.get_flow_graph("PROJ", FakeCtx(), max_nodes=2_000))
    res = json.loads(raw)

    assert len(raw) <= 1_000_000
    assert res["node_count"] == count
    assert res["edge_count"] == 0
    assert res["source_count"] == count
    assert res["returned_node_count"] == len(res["node_types"])
    assert res["returned_node_count"] < res["node_count"]
    assert res["truncated"] is True
    assert any("response size budget" in warning for warning in res["warnings"])


def test_flow_graph_captures_client_before_first_await(monkeypatch):
    first = FakeClient(FakeProject("PROJ", nodes={"first": _dataset("first")}))
    second = FakeClient(FakeProject("PROJ", nodes={"second": _dataset("second")}))
    calls = []

    def current_client():
        calls.append(True)
        return first if len(calls) == 1 else second

    monkeypatch.setattr(flow, "get_dss_client", current_client)

    assert flow_graph()["node_types"] == {"first": "dataset"}
    assert len(calls) == 1
