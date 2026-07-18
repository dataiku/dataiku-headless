"""Tests for the composed context tools.

These never touch the network: ``get_dss_client`` is replaced by a fake client
returning a fake project whose sections are driven from canned Python objects.
The tools under test are the two dense, one-call orientation helpers:

* ``projects.get_project_overview`` — the list_* fan-out collapsed into one call,
  with per-section failure isolation.
* ``flow.get_flow_graph`` — nodes/edges plus an ASCII build tree, with zone
  filtering and a large-flow tree-omission guard.
"""

import asyncio
import json

import pytest

from dataiku_mcp.tools import flow, projects


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #


class FakeCtx:
    def __init__(self):
        self.infos = []

    async def info(self, message, **kwargs):
        self.infos.append(message)


class FakeArticleData:
    def __init__(self, title):
        self._title = title

    def get_name(self):
        return self._title


class FakeArticle:
    def __init__(self, article_id, title):
        self.article_id = article_id
        self._title = title

    def get_data(self):
        return FakeArticleData(self._title)


class FakeWiki:
    def __init__(self, articles):
        self._articles = articles

    def list_articles(self):
        return self._articles


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
    """A project whose section returns are injected and whose failures are opt-in.

    Any section name added to ``failures`` raises when its SDK method is called, so
    tests can assert failure isolation without a real backend.
    """

    def __init__(
        self,
        key,
        *,
        metadata=None,
        datasets=None,
        recipes=None,
        folders=None,
        scenarios=None,
        nodes=None,
        jobs=None,
        articles=None,
        variables=None,
        zones=None,
        failures=None,
    ):
        self.project_key = key
        self._metadata = metadata or {}
        self._datasets = datasets or []
        self._recipes = recipes or []
        self._folders = folders or []
        self._scenarios = scenarios or []
        self._nodes = nodes or {}
        self._jobs = jobs or []
        self._articles = articles or []
        self._variables = variables or {"standard": {}, "local": {}}
        self._zones = zones or []
        self._failures = set(failures or ())

    def _guard(self, name):
        if name in self._failures:
            raise RuntimeError(f"boom-{name}")

    def get_metadata(self):
        self._guard("identity")
        return self._metadata

    def list_datasets(self):
        self._guard("datasets")
        return self._datasets

    def list_recipes(self):
        self._guard("recipes")
        return self._recipes

    def list_managed_folders(self):
        self._guard("folders")
        return self._folders

    def list_scenarios(self):
        self._guard("scenarios")
        return self._scenarios

    def list_jobs(self):
        self._guard("recent_jobs")
        return self._jobs

    def get_wiki(self):
        self._guard("wiki_articles")
        return FakeWiki(self._articles)

    def get_variables(self):
        self._guard("variables")
        return self._variables

    def get_flow(self):
        self._guard("flow_sources")
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
    monkeypatch.setattr(projects, "get_dss_client", lambda: client)
    monkeypatch.setattr(flow, "get_dss_client", lambda: client)


def overview(project_key="PROJ", **kwargs):
    return json.loads(run(projects.get_project_overview(project_key, FakeCtx(), **kwargs)))


def variables(project_key="PROJ", **kwargs):
    return json.loads(run(projects.get_project_variables(project_key, FakeCtx(), **kwargs)))


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
# get_project_overview
# --------------------------------------------------------------------------- #


def test_overview_happy_path_all_sections(monkeypatch):
    project = FakeProject(
        "PROJ",
        metadata={"label": "Retail", "shortDesc": "Sales pipeline"},
        datasets=[
            {"name": "orders", "type": "Filesystem"},
            {"name": "customers", "type": "PostgreSQL"},
        ],
        recipes=[{"name": "join_recipe", "type": "join"}],
        folders=[{"id": "fld1", "name": "exports"}],
        scenarios=[{"id": "nightly", "name": "Nightly build", "active": True}],
        nodes=diamond_nodes(),
        jobs=[
            {"def": {"id": "job-1"}, "state": "DONE"},
            {"def": {"id": "job-2"}, "state": "FAILED"},
        ],
        articles=[FakeArticle("home", "Home")],
        variables={"standard": {"env": "prod"}, "local": {"secret": "x"}},
    )
    bind(monkeypatch, project)

    res = overview()

    assert res["project_key"] == "PROJ"
    assert res["identity"] == {"name": "Retail", "description": "Sales pipeline"}
    assert res["datasets"] == {
        "columns": ["name", "type"],
        "rows": [["orders", "Filesystem"], ["customers", "PostgreSQL"]],
    }
    assert res["recipes"] == {
        "columns": ["name", "type"],
        "rows": [["join_recipe", "join"]],
    }
    assert res["folders"] == {"columns": ["id", "name"], "rows": [["fld1", "exports"]]}
    assert res["scenarios"] == {
        "columns": ["id", "name", "active"],
        "rows": [["nightly", "Nightly build", True]],
    }
    # flow_sources = COMPUTABLE_DATASET nodes with no predecessors.
    assert res["flow_sources"] == ["orders", "customers"]
    assert res["recent_jobs"] == {
        "columns": ["id", "state"],
        "rows": [["job-1", "DONE"], ["job-2", "FAILED"]],
    }
    assert res["wiki_articles"] == {"columns": ["id", "title"], "rows": [["home", "Home"]]}
    # Only the standard variables are surfaced, not local ones.
    assert res["variables"] == {"env": "prod"}
    assert res["counts"] == {
        "datasets": 2,
        "recipes": 1,
        "folders": 1,
        "scenarios": 1,
        "wiki_articles": 1,
    }
    assert "warnings" not in res


def test_overview_jobs_limit_truncates(monkeypatch):
    project = FakeProject(
        "PROJ",
        jobs=[{"def": {"id": f"job-{i}"}, "state": "DONE"} for i in range(10)],
    )
    bind(monkeypatch, project)

    res = overview(jobs_limit=3)
    assert [row[0] for row in res["recent_jobs"]["rows"]] == ["job-0", "job-1", "job-2"]


def test_overview_section_failure_is_isolated(monkeypatch):
    project = FakeProject(
        "PROJ",
        datasets=[{"name": "orders", "type": "Filesystem"}],
        recipes=[{"name": "join_recipe", "type": "join"}],
        failures={"scenarios"},
    )
    bind(monkeypatch, project)

    res = overview()

    # The failing section is dropped and reported, everything else survives.
    assert "scenarios" not in res
    assert "scenarios" not in res.get("counts", {})
    assert res["datasets"]["rows"] == [["orders", "Filesystem"]]
    assert res["recipes"]["rows"] == [["join_recipe", "join"]]
    assert len(res["warnings"]) == 1
    assert res["warnings"][0].startswith("scenarios:")


def test_overview_redacts_sensitive_standard_variables(monkeypatch):
    project = FakeProject(
        "PROJ",
        variables={
            "standard": {"api_key": "sk-secret", "env": "prod"},
            "local": {"password": "should-not-appear"},
        },
    )
    bind(monkeypatch, project)

    res = overview()

    # Sensitive-keyed values are redacted; benign ones survive.
    assert res["variables"]["api_key"] == "***REDACTED***"
    assert res["variables"]["env"] == "prod"
    # Overview only surfaces standard variables, never local ones.
    assert "should-not-appear" not in json.dumps(res)


# --------------------------------------------------------------------------- #
# get_project_variables
# --------------------------------------------------------------------------- #


def test_get_project_variables_redacts_standard_and_excludes_local_by_default(monkeypatch):
    project = FakeProject(
        "PROJ",
        variables={
            "standard": {"password": "p", "region": "eu"},
            "local": {"access_token": "t"},
        },
    )
    bind(monkeypatch, project)

    res = variables()

    assert res["standard"]["password"] == "***REDACTED***"
    assert res["standard"]["region"] == "eu"
    # Local variables are opt-in, so they are absent by default.
    assert "local" not in res


def test_get_project_variables_include_local_is_opt_in_and_redacted(monkeypatch):
    project = FakeProject(
        "PROJ",
        variables={
            "standard": {},
            "local": {"access_token": "t", "host": "db.internal"},
        },
    )
    bind(monkeypatch, project)

    res = variables(include_local=True)

    assert res["local"]["access_token"] == "***REDACTED***"
    assert res["local"]["host"] == "db.internal"


def test_overview_empty_sections_are_omitted_but_zero_counts_kept(monkeypatch):
    project = FakeProject("PROJ", metadata={"label": "Empty"})
    bind(monkeypatch, project)

    res = overview()

    assert res["identity"] == {"name": "Empty"}
    # No datasets/recipes/... lists in the payload (empty -> omitted),
    for key in ("datasets", "recipes", "folders", "scenarios", "wiki_articles"):
        assert key not in res
    # ...but the counts still record the explicit zeros.
    assert res["counts"] == {
        "datasets": 0,
        "recipes": 0,
        "folders": 0,
        "scenarios": 0,
        "wiki_articles": 0,
    }
    assert "warnings" not in res


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
        f"ds{i}": _dataset(f"ds{i}") for i in range(301)  # > _MAX_TREE_NODES
    }
    bind(monkeypatch, FakeProject("PROJ", nodes=nodes))

    res = flow_graph()

    assert res["node_count"] == 301
    assert "tree" not in res
    assert res["warnings"] == ["tree omitted for very large flow; use nodes/edges"]
