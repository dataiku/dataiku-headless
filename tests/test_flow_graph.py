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


class FakeZone:
    """Mirrors dataikuapi's DSSFlowZone: id/name properties plus get_graph().

    The zone graph is served whole, like the backend endpoint, so the default
    zone can have an empty explicit item list yet still contain most of the flow.
    """

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
    # The join is reached from both sources; the second time it is a (^) leaf.
    # (Marker pinned to ASCII since the unicode arrows were dropped: box-drawing
    # glyphs double or triple under JSON escaping, defeating the size budget.)
    assert tree.count("(^)") == 1
    assert "[recipe] join_recipe (^)" in tree
    # It is expanded exactly once (its downstream chain appears once).
    assert tree.count("[dataset] joined") == 1
    assert tree.count("[dataset] final") == 1


def test_flow_graph_zone_filter(monkeypatch):
    nodes = diamond_nodes()
    zone_nodes = {key: nodes[key] for key in ("orders", "join_recipe", "joined")}
    zones = [FakeZone("zone_prep", "prep", zone_nodes)]
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
    assert "(^)" not in res["tree"]


def test_flow_graph_zone_resolves_by_id(monkeypatch):
    nodes = diamond_nodes()
    zones = [FakeZone("zone_prep", "prep", {"orders": nodes["orders"]})]
    bind(monkeypatch, FakeProject("PROJ", nodes=nodes, zones=zones))

    assert flow_graph(zone="zone_prep")["node_count"] == 1


def test_flow_graph_zone_id_match_beats_name_shadowing(monkeypatch):
    # One zone is NAMED "target", a later zone has ID "target". Ids are unique
    # and authoritative, so the id match must win regardless of list order.
    nodes = diamond_nodes()
    zones = [
        FakeZone("first-id", "target", {"orders": nodes["orders"]}),
        FakeZone("target", "other", {"final": nodes["final"]}),
    ]
    bind(monkeypatch, FakeProject("PROJ", nodes=nodes, zones=zones))

    res = flow_graph(zone="target")

    assert [pair[0] for pair in res["nodes"]] == ["final"]


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
    # The default zone's membership is implicit in DSS: nothing is listed in its
    # explicit items, yet its server-side graph holds every unassigned node. The
    # zone graph endpoint is authoritative, so the full flow comes back.
    nodes = diamond_nodes()
    zones = [FakeZone("default", "Default zone", nodes)]
    bind(monkeypatch, FakeProject("PROJ", nodes={}, zones=zones))

    res = flow_graph(zone="default")

    assert res["node_count"] == 6
    assert res["source_count"] == 2
    assert "tree" in res


def test_flow_graph_unknown_zone_errors(monkeypatch):
    zones = [FakeZone("zone_prep", "prep")]
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


# Pinned verbatim: the cycle warning must be identical whether or not the tree
# rendered, since detection is a separate graph pass from rendering.
_CYCLE_WARNING = (
    "flow contains a cycle; a valid flow is acyclic, the backend data may be malformed"
)


def test_flow_graph_flags_cycle_as_back_edge_not_reconvergence(monkeypatch):
    nodes = {
        "a": _dataset("a", successors=["b"], predecessors=["b"]),
        "b": _dataset("b", successors=["a"], predecessors=["a"]),
    }
    bind(monkeypatch, FakeProject("PROJ", nodes=nodes))

    res = flow_graph()

    # The back-edge closing the cycle is marked (cycle), never the (^) join marker.
    assert "(cycle)" in res["tree"]
    assert "(^)" not in res["tree"]
    assert _CYCLE_WARNING in res["warnings"]


def test_flow_graph_cycle_warns_even_when_tree_is_omitted(monkeypatch):
    # A dense acyclic region exhausts the tree's character budget before the
    # traversal ever reaches the self-loop appended last. Detection must not
    # depend on how far rendering got, and the warning text must be the same
    # one emitted when the tree renders.
    count = 140
    nodes = {
        f"n{i}": _dataset(
            f"n{i}",
            successors=[f"n{j}" for j in range(i + 1, count)],
            predecessors=[f"n{j}" for j in range(i)],
        )
        for i in range(count)
    }
    nodes["late_loop"] = _dataset("late_loop", successors=["late_loop"])
    bind(monkeypatch, FakeProject("PROJ", nodes=nodes))

    res = flow_graph(max_edges=10_000)

    assert "tree" not in res
    assert _CYCLE_WARNING in res["warnings"]


def test_flow_graph_reconvergence_does_not_warn_about_cycles(monkeypatch):
    bind(monkeypatch, FakeProject("PROJ", nodes=diamond_nodes()))

    res = flow_graph()

    assert "(cycle)" not in res["tree"]
    assert "warnings" not in res


def test_flow_graph_dense_flow_tree_is_budgeted(monkeypatch):
    # A complete DAG on 140 nodes: within the node ceiling and, with max_edges
    # raised to the hard ceiling, within the edge ceiling too. The tree would
    # still render one line per edge traversal with a depth-sized prefix (many
    # megabytes), so it must be dropped and the response stay bounded.
    count = 140
    nodes = {
        f"n{i}": _dataset(
            f"n{i}",
            successors=[f"n{j}" for j in range(i + 1, count)],
            predecessors=[f"n{j}" for j in range(i)],
        )
        for i in range(count)
    }
    bind(monkeypatch, FakeProject("PROJ", nodes=nodes))

    raw = run(flow.get_flow_graph("PROJ", FakeCtx(), max_edges=10_000))
    res = json.loads(raw)

    assert res["node_count"] == count
    assert res["edge_count"] == count * (count - 1) // 2
    assert res["returned_edge_count"] == res["edge_count"]
    assert "truncated" not in res
    assert "tree" not in res
    assert any("tree omitted" in warning for warning in res["warnings"])
    assert len(raw) < 500_000


def test_flow_graph_response_is_capped_even_with_maximal_refs(monkeypatch):
    # Reviewer reproduction: 99 inputs each feeding 100 recipes, each feeding one
    # output, is 299 nodes and exactly 10,000 edges. With 512-character refs the
    # count ceilings alone serialize past 10 MB, so the response-size budget must
    # clip the edges list and say so.
    inputs = [f"in{i:03d}".ljust(512, "x") for i in range(99)]
    recipes = [f"r{i:03d}".ljust(512, "y") for i in range(100)]
    outputs = [f"out{i:03d}".ljust(512, "z") for i in range(100)]
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

    raw = run(flow.get_flow_graph("PROJ", FakeCtx(), max_edges=10_000))
    res = json.loads(raw)

    assert len(raw) <= 1_000_000
    assert res["node_count"] == 299
    assert res["edge_count"] == 10_000
    assert res["truncated"] is True
    assert res["returned_edge_count"] == len(res["edges"])
    assert res["returned_edge_count"] < 10_000
    assert any("response size budget" in warning for warning in res["warnings"])


def test_flow_graph_json_escaping_cannot_blow_the_response_cap(monkeypatch):
    # Refs full of non-ASCII characters sextuple under JSON \\uXXXX escaping: the
    # tree fits the pre-escape character budget but the serialized payload would
    # not fit the response budget, so the tree must be dropped at serialization
    # time. The budget is measured on the returned string, not in-memory sizes.
    nodes = {f"star{i:03d}": _dataset("★" * 400) for i in range(250)}
    bind(monkeypatch, FakeProject("PROJ", nodes=nodes))

    raw = run(flow.get_flow_graph("PROJ", FakeCtx()))
    res = json.loads(raw)

    assert len(raw) <= 1_000_000
    assert res["node_count"] == 250
    assert "tree" not in res
    assert any(
        "tree omitted to fit the response size budget" in warning
        for warning in res["warnings"]
    )


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
