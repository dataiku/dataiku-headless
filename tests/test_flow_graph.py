"""Tests for the ``flow.get_flow_graph`` composed tool.

These never touch the network: ``get_dss_client`` is replaced by a fake client
returning a fake project whose flow is driven from canned Python objects. The tool
under test collapses the whole flow into one call: nodes/edges plus an ASCII build
tree, with zone filtering and a large-flow tree-omission guard.
"""

import asyncio
import json

import pytest

from dataiku_mcp.tools import flow


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #


class FakeCtx:
    def __init__(self):
        self.infos = []

    async def info(self, message, **kwargs):
        self.infos.append(message)


class FakeGraph:
    def __init__(self, nodes):
        self.nodes = nodes


class FakeZoneSettings:
    def __init__(self, raw):
        self._raw = raw

    def get_raw(self):
        return self._raw


class FakeZone:
    def __init__(self, raw):
        self._raw = raw

    def get_settings(self):
        return FakeZoneSettings(self._raw)


class FakeFlow:
    def __init__(self, nodes, zones):
        self._nodes = nodes
        self._zones = zones

    def get_graph(self):
        return FakeGraph(self._nodes)

    def list_zones(self):
        return [FakeZone(z) for z in self._zones]


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


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


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
    """Two sources -> a join recipe -> a linear enrich chain.

    ``orders`` and ``customers`` both feed ``join_recipe`` (re-convergence), whose
    output ``joined`` runs through ``enrich_recipe`` to ``final``.
    """
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


# --------------------------------------------------------------------------- #
# get_flow_graph
# --------------------------------------------------------------------------- #


def test_flow_graph_nodes_and_edges_on_diamond(monkeypatch):
    bind(monkeypatch, FakeProject("PROJ", nodes=diamond_nodes()))

    res = flow_graph()

    assert res["node_count"] == 6
    assert res["source_count"] == 2
    assert {tuple(pair) for pair in res["nodes"]} == {
        ("orders", "dataset"),
        ("customers", "dataset"),
        ("join_recipe", "recipe"),
        ("joined", "dataset"),
        ("enrich_recipe", "recipe"),
        ("final", "dataset"),
    }
    assert {tuple(edge) for edge in res["edges"]} == {
        ("orders", "join_recipe"),
        ("customers", "join_recipe"),
        ("join_recipe", "joined"),
        ("joined", "enrich_recipe"),
        ("enrich_recipe", "final"),
    }


def test_flow_graph_tree_marks_reconvergence_once(monkeypatch):
    bind(monkeypatch, FakeProject("PROJ", nodes=diamond_nodes()))

    tree = flow_graph()["tree"]

    assert tree.splitlines()[0] == "Flow: PROJ"
    # The join is reached from both sources; the second time it is a (↑) leaf.
    assert tree.count("(↑)") == 1
    assert "[recipe] join_recipe (↑)" in tree
    # It is expanded exactly once (its downstream chain appears once).
    assert tree.count("[dataset] joined") == 1
    assert tree.count("[dataset] final") == 1


def test_flow_graph_zone_filter(monkeypatch):
    nodes = diamond_nodes()
    zones = [
        {
            "id": "zone_prep",
            "name": "prep",
            "items": [
                {"objectType": "DATASET", "objectId": "orders"},
                {"objectType": "RECIPE", "objectId": "join_recipe"},
                {"objectType": "DATASET", "objectId": "joined"},
            ],
        }
    ]
    bind(monkeypatch, FakeProject("PROJ", nodes=nodes, zones=zones))

    res = flow_graph(zone="prep")

    assert res["node_count"] == 3
    assert {pair[0] for pair in res["nodes"]} == {"orders", "join_recipe", "joined"}
    # customers is outside the zone, so its edge into join_recipe is dropped.
    assert {tuple(edge) for edge in res["edges"]} == {
        ("orders", "join_recipe"),
        ("join_recipe", "joined"),
    }
    # Within the zone only `orders` has no in-zone predecessor.
    assert res["source_count"] == 1
    assert "(↑)" not in res["tree"]


def test_flow_graph_unknown_zone_errors(monkeypatch):
    zones = [{"id": "zone_prep", "name": "prep", "items": []}]
    bind(monkeypatch, FakeProject("PROJ", nodes=diamond_nodes(), zones=zones))

    with pytest.raises(ValueError, match="Unknown flow zone 'nope'"):
        flow_graph(zone="nope")


def test_flow_graph_tree_omitted_for_very_large_flow(monkeypatch):
    nodes = {
        f"ds{i}": _dataset(f"ds{i}")
        for i in range(301)  # > _MAX_TREE_NODES
    }
    bind(monkeypatch, FakeProject("PROJ", nodes=nodes))

    res = flow_graph()

    assert res["node_count"] == 301
    assert "tree" not in res
    assert res["warnings"] == ["tree omitted for a large flow; use nodes/edges"]


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
    assert "tree" not in res


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"max_nodes": 2001}, "max_nodes.*<= 2000"),
        ({"max_edges": 10001}, "max_edges.*<= 10000"),
        ({"max_edges": 0}, "max_edges.*>= 1"),
    ],
)
def test_flow_graph_rejects_unbounded_limits(monkeypatch, kwargs, message):
    bind(monkeypatch, FakeProject("PROJ"))
    with pytest.raises(ValueError, match=message):
        flow_graph(**kwargs)


def test_flow_graph_renders_cycle_instead_of_only_a_title(monkeypatch):
    nodes = {
        "a": _dataset("a", successors=["b"], predecessors=["b"]),
        "b": _dataset("b", successors=["a"], predecessors=["a"]),
    }
    bind(monkeypatch, FakeProject("PROJ", nodes=nodes))

    tree = flow_graph()["tree"]

    assert "[dataset] a" in tree
    assert "[dataset] b" in tree
    assert "(↑)" in tree


def test_flow_graph_captures_client_before_first_await(monkeypatch):
    first = FakeClient(FakeProject("PROJ", nodes={"first": _dataset("first")}))
    second = FakeClient(FakeProject("PROJ", nodes={"second": _dataset("second")}))
    calls = []

    def current_client():
        calls.append(True)
        return first if len(calls) == 1 else second

    monkeypatch.setattr(flow, "get_dss_client", current_client)

    assert flow_graph()["nodes"] == [["first", "dataset"]]
    assert len(calls) == 1
