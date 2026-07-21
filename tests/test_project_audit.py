"""Tests for the read-only project reviewability audit.

These never touch the network: a small fake ``dataikuapi`` project handle
(datasets / recipes / flow graph / zones / wiki / flow-consistency tool) drives
the real :mod:`dataiku_mcp.tools.utils.audit_engine` functions. The MCP tool
wrapper is exercised against the same fake via a patched ``get_dss_client``.
"""

import asyncio
import json

import pytest

from dataiku_mcp.tools import project_audit
from dataiku_mcp.tools.utils import audit_engine as ae


# --------------------------------------------------------------------------- #
# Fakes (the dataikuapi project-handle seam)
# --------------------------------------------------------------------------- #
class FakeMetrics:
    def __init__(self, count):
        self._count = count

    def get_global_value(self, key):
        if self._count is None:
            raise ValueError(f"no cached metric {key}")
        return self._count


class FakeDataset:
    def __init__(
        self,
        name,
        description="",
        short_desc="",
        columns=None,
        count=None,
        rows=None,
        raises=None,
        meta_raises=None,
    ):
        self.name = name
        self._description = description
        self._short_desc = short_desc
        self._columns = columns or []
        self._count = count
        self._rows = rows or []
        self._raises = raises
        # A read that fails for ONE facet only (e.g. a denied metadata read while
        # schema/metrics stay readable), so a scan-level evidence gap can be
        # exercised without failing every read.
        self._meta_raises = meta_raises

    def _guard(self):
        if self._raises is not None:
            raise self._raises

    def get_metadata(self):
        self._guard()
        if self._meta_raises is not None:
            raise self._meta_raises
        meta = {}
        if self._description:
            meta["description"] = self._description
        if self._short_desc:
            meta["shortDesc"] = self._short_desc
        return meta

    def get_definition(self):
        self._guard()
        return {"schema": {"columns": self._columns}}

    def get_last_metric_values(self):
        self._guard()
        return FakeMetrics(self._count)

    def iter_rows(self):
        self._guard()
        yield from self._rows


class FakeRecipeSettings:
    def __init__(self, raw):
        self._raw = raw

    def get_recipe_raw_definition(self):
        return self._raw


class FakeRecipe:
    def __init__(self, name, type="", description="", short_desc="", raises=None):
        self.name = name
        self.type = type
        self._raw = {}
        if description:
            self._raw["description"] = description
        if short_desc:
            self._raw["shortDesc"] = short_desc
        self._raises = raises

    def get_settings(self):
        if self._raises is not None:
            raise self._raises
        return FakeRecipeSettings(self._raw)


class FakeZone:
    def __init__(self, zone_id, name, raw):
        self.id = zone_id
        self.name = name
        self._raw = raw

    def get_settings(self):
        raw = {"id": self.id, "name": self.name, **self._raw}

        class Settings:
            def get_raw(self):
                return raw

        return Settings()


class FakeGraph:
    def __init__(self, nodes):
        self.nodes = nodes


class FakeFuture:
    def __init__(self, state):
        self.state = state

    def get_state(self):
        return self.state


class FakeTool:
    def __init__(self, state=None):
        self._state = state or {"stateByNode": {}}
        self.stopped = False

    def update(self, options):
        return FakeFuture({"hasResult": True})

    def get_state(self, options=None):
        return self._state

    def stop(self):
        self.stopped = True


class FakeFlow:
    def __init__(self, nodes, zones, tool):
        self._nodes = nodes
        self._zones = zones
        self._tool = tool

    def get_graph(self):
        return FakeGraph(self._nodes)

    def list_zones(self):
        return self._zones

    def start_tool(self, tool_type):
        if isinstance(self._tool, BaseException):
            raise self._tool
        return self._tool


class FakeArticleData:
    def __init__(self, name, body):
        self._name = name
        self._body = body

    def get_name(self):
        return self._name

    def get_body(self):
        return self._body


class FakeArticle:
    def __init__(self, name, body):
        self._data = FakeArticleData(name, body)

    def get_data(self):
        return self._data


class FakeWiki:
    def __init__(self, articles):
        self._articles = articles

    def list_articles(self):
        return [FakeArticle(n, b) for n, b in self._articles]


class FakeProject:
    def __init__(self, datasets, recipes, nodes, zones, tool, wiki):
        self._datasets = datasets
        self._recipes = recipes
        self._nodes = nodes
        self._zones = zones
        self._tool = tool
        self._wiki = wiki

    def list_datasets(self):
        return [{"name": name} for name in self._datasets]

    def list_recipes(self):
        return [{"name": r.name, "type": r.type} for r in self._recipes.values()]

    def get_dataset(self, name):
        return self._datasets[name]

    def get_recipe(self, name):
        return self._recipes[name]

    def get_flow(self):
        return FakeFlow(self._nodes, self._zones, self._tool)

    def get_wiki(self):
        return FakeWiki(self._wiki)


class FakeClient:
    def __init__(self, project):
        self._project = project

    def get_project(self, key):
        return self._project


class FakeCtx:
    def __init__(self):
        self.infos = []

    async def info(self, message, **kwargs):
        self.infos.append(message)


# --------------------------------------------------------------------------- #
# Builders
# --------------------------------------------------------------------------- #
def col(name, type="string", comment=""):
    return {"name": name, "type": type, "comment": comment}


def recipe_node(inputs, outputs):
    return {"type": "RUNNABLE_RECIPE", "predecessors": list(inputs), "successors": list(outputs)}


def make_project(*, datasets=None, recipes=None, nodes=None, zones=None, tool=None, wiki=None):
    ds_specs = datasets or {}
    rc_specs = recipes or {}
    ds_objs = {name: FakeDataset(name, **spec) for name, spec in ds_specs.items()}
    rc_objs = {name: FakeRecipe(name, **spec) for name, spec in rc_specs.items()}
    return FakeProject(
        ds_objs,
        rc_objs,
        nodes or {},
        zones or [],
        tool if tool is not None else FakeTool(),
        wiki or [],
    )


def checks_for_bucket(proj, bucket):
    actx = ae.load_context(proj, "PROJ")
    return {c.id: c for c in ae.run_bucket(actx, bucket)}


def run_audit(proj, project_key, *, contract=None, buckets=None):
    """Compose the engine (context + buckets + optional contract) into a payload.

    The engine ships no all-in-one wrapper; the MCP tool composes the same pieces
    with per-bucket progress reporting. This test helper mirrors that composition.
    """
    selected = ae.validate_buckets(buckets)
    normalized = ae.normalize_contract(contract) if contract is not None else None
    actx = ae.load_context(proj, project_key)
    checks = []
    for bucket in selected:
        checks += ae.run_bucket(actx, bucket)
    if normalized is not None:
        checks += ae.run_contract_checks(actx, normalized)
    return ae.build_payload(project_key, checks, actx.inventory)


# A linear flow: src -> compute_out -> out. `out` is the terminal output.
def linear_project(**overrides):
    datasets = {
        "src": {"description": "Raw source rows", "columns": [col("id", comment="row id")], "count": 10, "rows": []},
        "out": {"description": "Cleaned output", "columns": [col("id", comment="row id")], "count": 5, "rows": []},
    }
    datasets.update(overrides.get("datasets", {}))
    recipes = {"compute_out": {"type": "prepare", "short_desc": "Cleans the source rows"}}
    recipes.update(overrides.get("recipes", {}))
    nodes = {"compute_out": recipe_node(["src"], ["out"])}
    return make_project(datasets=datasets, recipes=recipes, nodes=nodes, tool=overrides.get("tool"))


# --------------------------------------------------------------------------- #
# graph_sets / inventory
# --------------------------------------------------------------------------- #
def test_graph_sets_terminal_and_source_derivation():
    datasets = {"A", "B", "C"}
    nodes = {
        "r1": recipe_node(["A"], ["B"]),
        "r2": recipe_node(["B"], ["C"]),
    }
    inputs, outputs, terminal = ae.graph_sets(nodes, datasets)
    assert inputs == {"A", "B"}
    assert outputs == {"B", "C"}
    assert terminal == {"C"}  # outputs - inputs
    assert sorted(inputs - outputs) == ["A"]  # source


def test_documentation_uses_true_graph_sources_not_every_non_terminal_dataset():
    proj = make_project(
        datasets={
            "src": {"count": 5},
            "mid": {"count": 5},
            "out": {"description": "Final business output", "count": 5},
            "orphan": {"count": 0},
        },
        recipes={
            "prepare_mid": {"type": "prepare", "short_desc": "Prepare source rows"},
            "prepare_out": {"type": "prepare", "short_desc": "Create final output"},
        },
        nodes={
            "prepare_mid": recipe_node(["src"], ["mid"]),
            "prepare_out": recipe_node(["mid"], ["out"]),
        },
    )

    check = checks_for_bucket(proj, "documentation")[
        "source_datasets_have_descriptions"
    ]

    assert check.status == "warn"
    assert "src" in check.detail
    assert "mid" not in check.detail
    assert "orphan" not in check.detail


def test_orphan_detection_in_structure_and_inventory():
    proj = make_project(
        datasets={
            "src": {"description": "src", "count": 3},
            "out": {"description": "out", "count": 3},
            "leftover": {"description": "orphan", "count": 0},
        },
        recipes={"compute_out": {"type": "prepare"}},
        nodes={"compute_out": recipe_node(["src"], ["out"])},
    )
    actx = ae.load_context(proj, "PROJ")
    assert actx.inventory["orphan_datasets"] == ["leftover"]
    assert actx.inventory["terminal_datasets"] == ["out"]
    assert actx.inventory["source_datasets"] == ["src"]

    checks = {c.id: c for c in ae.run_bucket(actx, "structure")}
    orphan = checks["no_orphan_datasets"]
    assert orphan.status == "warn"
    assert "leftover" in orphan.detail
    assert "Cobuild" in orphan.fix


# --------------------------------------------------------------------------- #
# Documentation: basic presence checks only (no text-quality heuristics)
# --------------------------------------------------------------------------- #
def test_documentation_flags_missing_descriptions_and_absent_wiki():
    proj = make_project(
        datasets={
            "src": {"description": "clean source of customer records", "count": 4},
            # terminal output: no description at all -> missing (a presence gap)
            "out": {"count": 4, "columns": [col("v", comment="value")]},
        },
        recipes={"compute_out": {"type": "prepare"}},  # no description -> missing
        nodes={"compute_out": recipe_node(["src"], ["out"])},
    )
    checks = checks_for_bucket(proj, "documentation")
    out_desc = checks["datasets_have_descriptions"]
    assert out_desc.status == "warn"
    assert "out" in out_desc.detail
    # Presence check only — description quality (repeats-name / templated) is NOT judged.
    assert "low-quality" not in out_desc.detail
    # Recipe with no description is an advisory warn.
    assert checks["recipes_have_descriptions"].status == "warn"
    # No wiki present.
    assert checks["has_wiki"].status == "warn"


def test_documentation_present_descriptions_pass_regardless_of_quality():
    # A short / name-repeating description now PASSES: only presence is checked.
    proj = make_project(
        datasets={
            "src": {"description": "src", "count": 4},
            "out": {"description": "out", "count": 4, "columns": [col("v", comment="value")]},
        },
        recipes={"compute_out": {"type": "prepare", "short_desc": "x"}},
        nodes={"compute_out": recipe_node(["src"], ["out"])},
        wiki=[("Runbook", "# Purpose\nDoc.")],
    )
    checks = checks_for_bucket(proj, "documentation")
    assert checks["datasets_have_descriptions"].status == "pass"
    assert checks["source_datasets_have_descriptions"].status == "pass"
    assert checks["recipes_have_descriptions"].status == "pass"
    assert checks["has_wiki"].status == "pass"


# --------------------------------------------------------------------------- #
# Evidence
# --------------------------------------------------------------------------- #
def test_evidence_zero_row_terminal_output_warns_via_cached_metric():
    proj = linear_project(datasets={"out": {"description": "out", "columns": [col("id", comment="c")], "count": 0}})
    checks = checks_for_bucket(proj, "evidence")
    built = checks["terminal_outputs_built"]
    assert built.status == "warn"
    assert "out" in built.detail
    assert "build_datasets" in built.fix  # names the MCP action for the direct build
    # Cached count was readable (0), so row-count warn does NOT fire.
    assert checks["terminal_row_counts"].status == "pass"


def test_evidence_unknown_row_count_is_a_warning():
    proj = linear_project(datasets={"out": {"description": "out", "columns": [col("id", comment="c")], "count": None}})
    checks = checks_for_bucket(proj, "evidence")
    assert checks["terminal_row_counts"].status == "warn"
    assert "out" in checks["terminal_row_counts"].detail


def test_evidence_column_smells_all_null_and_blank_keys():
    rows = [[None, "x"], [None, "y"], [None, None], [None, "z"], [None, "w"]]
    proj = linear_project(
        datasets={
            "out": {
                "description": "out",
                "count": 5,
                "columns": [col("customer_id"), col("label")],
                "rows": rows,
            }
        }
    )
    checks = checks_for_bucket(proj, "evidence")
    assert checks["all_null_columns"].status == "warn"
    assert "out.customer_id" in checks["all_null_columns"].detail
    assert checks["blank_key_columns"].status == "warn"  # id column with blanks


def test_flow_consistency_dirty_flow_fails():
    tool = FakeTool(
        state={
            "stateByNode": {
                "node1": {"recipeCheckResult": {"messages": [{"severity": "ERROR", "message": "schema mismatch"}]}}
            }
        }
    )
    proj = linear_project(tool=tool)
    checks = checks_for_bucket(proj, "evidence")
    assert checks["flow_check_clean"].status == "fail"
    assert checks["flow_check_clean"].detail == "node1: fatal consistency error"
    assert "schema mismatch" not in checks["flow_check_clean"].detail


# --------------------------------------------------------------------------- #
# Per-check failure isolation: FAIL raise -> error, WARN raise -> skip
# --------------------------------------------------------------------------- #
def test_collect_fail_severity_raise_becomes_error_warn_becomes_skip():
    def boom():
        raise RuntimeError("nope")

    units = [
        ("fc", "evidence", ae.FAIL, boom),
        ("wc", "documentation", ae.WARN, boom),
    ]
    checks = {c.id: c for c in ae._collect(units)}
    # A FAIL-severity check that cannot be evaluated is an error, not a skip.
    assert checks["fc"].status == "error"
    assert "RuntimeError" in checks["fc"].detail
    assert "nope" not in checks["fc"].detail
    # A WARN-severity check that cannot run stays an advisory skip.
    assert checks["wc"].status == "skip"
    assert "RuntimeError" in checks["wc"].detail
    assert "nope" not in checks["wc"].detail


def test_per_check_isolation_fail_check_raise_becomes_error():
    # The flow-consistency check is FAIL-severity; when the flow tool explodes it
    # becomes an error (unreadable evidence), not a skip.
    proj = linear_project(tool=RuntimeError("flow tool exploded"))
    checks = checks_for_bucket(proj, "evidence")
    flow = checks["flow_check_clean"]
    assert flow.status == "error"
    assert "RuntimeError" in flow.detail
    assert "flow tool exploded" not in flow.detail
    # The rest of the evidence bucket still ran.
    assert checks["terminal_outputs_built"].status in {"pass", "warn", "skip"}
    assert checks["terminal_row_counts"].status == "pass"


def test_unreadable_fail_evidence_marks_incomplete_and_not_passed():
    proj = linear_project(tool=RuntimeError("boom"))
    payload = run_audit(proj, "PROJ", buckets=["evidence"])
    # The unreadable FAIL check is an error, which blocks the gate...
    assert payload["checks"]["counts"].get("error") == 1
    assert payload["passed"] is False
    # ...and marks the whole audit incomplete with an error count.
    assert payload["incomplete"] is True
    assert payload["errors"] == 1


def test_denied_terminal_metadata_read_is_advisory_but_visible():
    # Documentation is a reviewability convention, not a correctness gate. A
    # denied metadata read stays visible without turning an otherwise sound Flow
    # into a failed audit.
    denied = PermissionError("metadata read denied")
    proj = linear_project(
        datasets={"out": {"columns": [col("id", comment="c")], "count": 5, "meta_raises": denied}}
    )
    checks = checks_for_bucket(proj, "documentation")

    ddesc = checks["datasets_have_descriptions"]
    assert ddesc.status == "warn"
    assert "out" in ddesc.detail
    assert "evidence gap" in ddesc.detail

    payload = run_audit(proj, "PROJ", buckets=["documentation"])
    assert payload["passed"] is True
    assert "incomplete" not in payload


def test_warn_scan_notes_evidence_gap_without_erroring():
    # A denied SOURCE-dataset read feeds only a WARN check: it never blocks, but
    # the gap must be noted in the detail rather than silently dropped.
    denied = PermissionError("denied")
    proj = linear_project(
        datasets={"src": {"columns": [col("id")], "count": 3, "meta_raises": denied}}
    )
    checks = checks_for_bucket(proj, "documentation")
    src = checks["source_datasets_have_descriptions"]
    assert src.status == "warn"
    assert "src" in src.detail and "evidence gap" in src.detail


def test_unreadable_terminal_schema_is_noted_not_counted_documented():
    # A denied schema read must not be silently treated as "columns documented".
    class NoSchema(FakeDataset):
        def get_definition(self):
            raise PermissionError("schema denied")

    proj = linear_project()
    proj._datasets["out"] = NoSchema("out", description="Cleaned output", count=5)
    checks = checks_for_bucket(proj, "evidence")
    # Sample read failed -> surfaced by the row-count evidence check, not hidden.
    assert checks["terminal_row_counts"].status == "warn"
    assert "out" in checks["terminal_row_counts"].detail
    doc_checks = checks_for_bucket(proj, "documentation")
    tcd = doc_checks["terminal_columns_documented"]
    assert tcd.status == "warn"
    assert "unreadable" in tcd.detail and "out" in tcd.detail


def test_unreadable_terminal_row_count_skips_advisory_build_heuristic():
    # Without an explicit min_rows contract, a missing cached count is an
    # advisory evidence gap rather than proof that a graph leaf is wrong.
    proj = linear_project(
        datasets={"out": {"description": "out", "columns": [col("id", comment="c")], "count": None}}
    )
    checks = checks_for_bucket(proj, "evidence")
    built = checks["terminal_outputs_built"]
    assert built.status == "skip"
    assert "out" in built.detail
    # The WARN check keeps noting the same evidence gap, never blocking.
    assert checks["terminal_row_counts"].status == "warn"
    assert "out" in checks["terminal_row_counts"].detail

    payload = run_audit(proj, "PROJ", buckets=["evidence"])
    assert payload["passed"] is True
    assert "incomplete" not in payload


def test_readable_but_empty_terminal_warns_without_explicit_contract():
    proj = linear_project(
        datasets={"out": {"description": "out", "columns": [col("id", comment="c")], "count": 0}}
    )
    built = checks_for_bucket(proj, "evidence")["terminal_outputs_built"]
    assert built.status == "warn"
    assert "out" in built.detail
    assert "build_datasets" in built.fix


# --------------------------------------------------------------------------- #
# Contract
# --------------------------------------------------------------------------- #
def test_contract_missing_column_and_min_rows_failures():
    proj = make_project(
        datasets={
            "src": {"description": "s", "count": 5},
            "B": {"description": "b", "count": 5, "columns": [col("x")]},
        },
        recipes={"compute_B": {"type": "prepare"}},
        nodes={"compute_B": recipe_node(["src"], ["B"])},
    )
    actx = ae.load_context(proj, "PROJ")
    contract = ae.normalize_contract(
        {"outputs": [{"dataset": "B", "columns": ["x", "missing"], "min_rows": 100}]}
    )
    checks = {c.id: c for c in ae.run_contract_checks(actx, contract)}
    assert checks["contract_columns:B"].status == "fail"
    assert "missing" in checks["contract_columns:B"].detail
    assert checks["contract_min_rows:B"].status == "fail"
    assert "100" in checks["contract_min_rows:B"].detail and "got 5" in checks["contract_min_rows:B"].detail
    # A column that IS present passes the type check (required subset, not exact schema).
    assert checks["contract_types:B"].status == "pass"


def test_contract_min_rows_unreadable_count_errors_not_fabricated_zero():
    # A raising metric read during min_rows evaluation must not be converted into a
    # measured zero (which would *fail*, asserting the dataset is empty — a
    # fabricated claim). It errors instead: evidence unreadable, incomplete audit.
    proj = make_project(
        datasets={
            "src": {"description": "s", "count": 5},
            "B": {"description": "b", "count": None, "columns": [col("x")]},
        },
        recipes={"compute_B": {"type": "prepare"}},
        nodes={"compute_B": recipe_node(["src"], ["B"])},
    )
    actx = ae.load_context(proj, "PROJ")
    contract = ae.normalize_contract({"outputs": [{"dataset": "B", "min_rows": 100}]})
    checks_list = ae.run_contract_checks(actx, contract)
    checks = {c.id: c for c in checks_list}

    mr = checks["contract_min_rows:B"]
    assert mr.status == "error"
    assert "unreadable" in mr.detail
    # No fabricated measurement leaks into the verdict.
    assert "got 0" not in mr.detail
    assert "Expected at least" not in mr.detail

    payload = ae.build_payload("PROJ", checks_list, actx.inventory)
    assert payload["passed"] is False
    assert payload["incomplete"] is True
    assert payload["errors"] >= 1


def test_contract_not_blank_does_not_pass_vacuously_without_sample_rows():
    proj = make_project(
        datasets={
            "src": {"count": 1},
            "out": {"count": 0, "columns": [col("id")], "rows": []},
        },
        recipes={"prepare_out": {"type": "prepare"}},
        nodes={"prepare_out": recipe_node(["src"], ["out"])},
    )
    actx = ae.load_context(proj, "PROJ")
    contract = ae.normalize_contract(
        {"outputs": [{"dataset": "out", "not_blank": ["id"]}]}
    )

    check = {c.id: c for c in ae.run_contract_checks(actx, contract)}[
        "contract_not_blank:out"
    ]

    assert check.status == "error"
    assert "no rows" in check.detail


def test_contract_rejects_unknown_top_level_key_naming_allowed_set():
    # A misplaced top-level `min_rows` (it belongs inside an output spec) would be
    # silently dropped; reject it and name the allowed top-level key set.
    with pytest.raises(ValueError, match="unknown top-level key") as exc:
        ae.normalize_contract({"outputs": {"B": {"min_rows": 3}}, "min_rows": 99})
    msg = str(exc.value)
    assert "outputs" in msg  # allowed set is named
    assert "min_rows" in msg  # the offending key is named
    # The dict-vs-list outputs duality stays supported (no false rejection).
    assert ae.normalize_contract({"outputs": [{"dataset": "B", "min_rows": 3}]}) == {
        "outputs": {"B": {"min_rows": 3}}
    }


def test_contract_output_missing_dataset_fails():
    proj = linear_project()
    actx = ae.load_context(proj, "PROJ")
    contract = ae.normalize_contract({"outputs": [{"dataset": "does_not_exist", "columns": ["a"]}]})
    checks = {c.id: c for c in ae.run_contract_checks(actx, contract)}
    exists = checks["contract_output_exists:does_not_exist"]
    assert exists.status == "fail"
    assert "does not exist" in exists.detail
    assert "Cobuild" in exists.fix


def test_contract_normalization_accepts_both_shapes_and_rejects_malformed():
    list_form = ae.normalize_contract({"outputs": [{"dataset": "B", "min_rows": 3}]})
    dict_form = ae.normalize_contract({"outputs": {"B": {"min_rows": 3}}})
    assert list_form == dict_form == {"outputs": {"B": {"min_rows": 3}}}

    with pytest.raises(ValueError, match="outputs"):
        ae.normalize_contract({})
    with pytest.raises(ValueError, match="dataset"):
        ae.normalize_contract({"outputs": [{"columns": ["a"]}]})
    with pytest.raises(ValueError, match="object"):
        ae.normalize_contract("nope")


def test_contract_rejects_empty_outputs_list():
    with pytest.raises(ValueError, match="must not be empty"):
        ae.normalize_contract({"outputs": []})


def test_contract_rejects_empty_outputs_object():
    with pytest.raises(ValueError, match="must not be empty"):
        ae.normalize_contract({"outputs": {}})


def test_contract_rejects_empty_dataset_name():
    with pytest.raises(ValueError, match="dataset"):
        ae.normalize_contract({"outputs": [{"dataset": "   ", "columns": ["a"]}]})


def test_contract_rejects_duplicate_dataset_names():
    with pytest.raises(ValueError, match="duplicate"):
        ae.normalize_contract({"outputs": [{"dataset": "B"}, {"dataset": "B"}]})


def test_contract_rejects_non_int_min_rows_no_coercion():
    # A numeric string is rejected outright, not coerced to an int.
    with pytest.raises(ValueError, match="min_rows"):
        ae.normalize_contract({"outputs": [{"dataset": "B", "min_rows": "100"}]})


def test_contract_rejects_bool_and_negative_min_rows():
    with pytest.raises(ValueError, match="min_rows"):
        ae.normalize_contract({"outputs": [{"dataset": "B", "min_rows": True}]})
    with pytest.raises(ValueError, match="min_rows"):
        ae.normalize_contract({"outputs": [{"dataset": "B", "min_rows": -1}]})


def test_contract_rejects_non_list_and_empty_string_columns():
    with pytest.raises(ValueError, match="columns"):
        ae.normalize_contract({"outputs": [{"dataset": "B", "columns": "x"}]})
    with pytest.raises(ValueError, match="columns"):
        ae.normalize_contract({"outputs": [{"dataset": "B", "columns": ["ok", ""]}]})


def test_contract_rejects_non_list_and_empty_string_not_blank():
    with pytest.raises(ValueError, match="not_blank"):
        ae.normalize_contract({"outputs": [{"dataset": "B", "not_blank": "x"}]})
    with pytest.raises(ValueError, match="not_blank"):
        ae.normalize_contract({"outputs": [{"dataset": "B", "not_blank": [" "]}]})


def test_contract_accepts_zero_min_rows():
    # 0 is a valid non-negative integer and must survive normalization.
    normalized = ae.normalize_contract({"outputs": [{"dataset": "B", "min_rows": 0}]})
    assert normalized == {"outputs": {"B": {"min_rows": 0}}}


def test_contract_rejects_unknown_spec_key_typo():
    # A `min_row` typo would silently drop the row-count assertion; reject it and
    # name the allowed key set instead of ignoring the key.
    with pytest.raises(ValueError, match="unknown key"):
        ae.normalize_contract({"outputs": [{"dataset": "B", "min_row": 5}]})


def test_contract_rejects_empty_and_non_string_types():
    with pytest.raises(ValueError, match="types"):
        ae.normalize_contract({"outputs": [{"dataset": "B", "types": {}}]})
    with pytest.raises(ValueError, match="types"):
        ae.normalize_contract({"outputs": [{"dataset": "B", "types": {"col": 1}}]})
    with pytest.raises(ValueError, match="types"):
        ae.normalize_contract({"outputs": [{"dataset": "B", "types": {"": "string"}}]})


def test_contract_accepts_full_valid_contract_with_types():
    normalized = ae.normalize_contract(
        {
            "outputs": [
                {
                    "dataset": "B",
                    "columns": ["x"],
                    "not_blank": ["x"],
                    "min_rows": 3,
                    "types": {"x": "string"},
                }
            ]
        }
    )
    assert normalized == {
        "outputs": {
            "B": {
                "columns": ["x"],
                "not_blank": ["x"],
                "min_rows": 3,
                "types": {"x": "string"},
            }
        }
    }


def test_contract_size_and_identifier_limits_are_hard():
    with pytest.raises(ValueError, match="at most 25"):
        ae.normalize_contract(
            {"outputs": [{"dataset": f"out_{i}"} for i in range(26)]}
        )
    with pytest.raises(ValueError, match="at most 200"):
        ae.normalize_contract(
            {
                "outputs": [
                    {
                        "dataset": "out",
                        "columns": [f"col_{i}" for i in range(201)],
                    }
                ]
            }
        )
    with pytest.raises(ValueError, match="<= 512"):
        ae.normalize_contract({"outputs": [{"dataset": "x" * 513}]})


def test_contract_unknown_non_string_key_gets_a_clear_validation_error():
    with pytest.raises(ValueError, match="unknown top-level key"):
        ae.normalize_contract({"outputs": [{"dataset": "out"}], 3: "typo"})


def test_dataset_sample_stops_before_consuming_the_next_row():
    # The bounded row sample must consume exactly max_rows items from the live
    # iterator — never row max_rows+1 (an unnecessary read against the dataset).
    consumed = {"n": 0}

    def gen():
        i = 0
        while True:
            consumed["n"] += 1
            i += 1
            yield [i]

    class OneDataset:
        def iter_rows(self):
            return gen()

    class OneProj:
        def get_dataset(self, name):
            return OneDataset()

    rows = ae._dataset_sample(OneProj(), "d", [col("v")], 100)
    assert len(rows) == 100
    assert consumed["n"] == 100  # row 101 was never pulled


# --------------------------------------------------------------------------- #
# Buckets filtering
# --------------------------------------------------------------------------- #
def test_buckets_filtering_restricts_work():
    proj = make_project(
        datasets={"src": {"count": 3}, "orphan": {"count": 0}},
        recipes={"compute_out": {"type": "prepare"}},
        nodes={"compute_out": recipe_node(["src"], ["out"])},
    )
    payload = run_audit(proj, "PROJ", buckets=["structure"])
    issues = payload["checks"].get("issues")
    buckets_seen = set()
    if issues:
        bucket_idx = issues["columns"].index("bucket")
        buckets_seen = {row[bucket_idx] for row in issues["rows"]}
    # Only structure checks were produced.
    assert buckets_seen <= {"structure"}

    # Directly assert the produced checks are all in the requested bucket.
    actx = ae.load_context(proj, "PROJ")
    checks = ae.run_bucket(actx, "structure")
    assert {c.bucket for c in checks} == {"structure"}


def test_validate_buckets_rejects_unknown_names():
    assert ae.validate_buckets(None) == list(ae.AUDIT_BUCKETS_ORDER)
    assert ae.validate_buckets(["Evidence", "structure"]) == ["structure", "evidence"]
    with pytest.raises(ValueError, match="Invalid bucket"):
        ae.validate_buckets(["nonsense"])
    with pytest.raises(ValueError, match="at least one"):
        ae.validate_buckets([])
    # The maintainability bucket is gone from the surface.
    assert "maintainability" not in ae.AUDIT_BUCKETS


def test_empty_named_zone_is_flagged():
    proj = make_project(
        datasets={"src": {"description": "s", "count": 3}, "out": {"description": "o", "count": 3}},
        recipes={"compute_out": {"type": "prepare"}},
        nodes={"compute_out": recipe_node(["src"], ["out"])},
        zones=[
            FakeZone("default", "Default", {"items": [{"objectId": "src"}]}),
            FakeZone("z1", "Staging", {"items": [], "shortDesc": ""}),
        ],
    )
    checks = checks_for_bucket(proj, "structure")
    assert checks["empty_zones"].status == "warn"
    assert "Staging" in checks["empty_zones"].detail


# --------------------------------------------------------------------------- #
# Score / passed
# --------------------------------------------------------------------------- #
def _clean_project():
    return make_project(
        datasets={
            "customers_raw": {
                "description": "Raw customer records ingested from the CRM export",
                "count": 12,
                "columns": [col("customer_name", comment="Full name")],
            },
            "customers_clean": {
                "description": "Deduplicated and standardized customer records",
                "count": 12,
                "columns": [
                    col("customer_name", comment="Full name"),
                    col("email", comment="Primary email address"),
                ],
                "rows": [["Alice", "a@x.com"], ["Bob", "b@x.com"], ["Cara", "c@x.com"]],
            },
        },
        recipes={"prepare_customers": {"type": "prepare", "short_desc": "Cleans and standardizes customer records"}},
        nodes={"prepare_customers": recipe_node(["customers_raw"], ["customers_clean"])},
        wiki=[("Runbook", "# Purpose\nStandardize customers.\n# Inputs\ncustomers_raw from CRM")],
    )


def test_clean_project_passes_with_full_score():
    payload = run_audit(_clean_project(), "PROJ")
    assert payload["passed"] is True
    assert payload["score"] == 1.0
    assert payload["summary"] == "passed"
    # The verdict restates its narrow, flow-level scope; nothing is overclaimed.
    assert payload["scope"] == "flow-level audit (datasets, recipes, zones, wiki)"
    assert "incomplete" not in payload
    # Everything passed -> the full pass list is emitted, no issues block.
    assert "issues" not in payload["checks"]
    assert payload["checks"]["passed_checks"]
    assert payload["project_key"] == "PROJ"


def test_messy_but_consistent_project_passes_with_advisory_warnings():
    proj = make_project(
        datasets={
            "src": {"description": "raw source table", "count": 3},
            "out": {"count": 0},  # no description (warn) + zero rows (warn)
            "tmp_scratch": {"count": 0},  # orphan dataset (warn)
        },
        recipes={"compute_out": {"type": "python"}},  # no description (warn)
        nodes={"compute_out": recipe_node(["src"], ["out"])},
    )
    payload = run_audit(proj, "PROJ")
    assert payload["passed"] is True
    assert 0.0 <= payload["score"] < 1.0
    assert "warning" in payload["summary"]
    ids = set(payload["checks"]["issues"]["columns"])
    assert {"id", "status", "detail", "fix"} <= ids


def test_audit_payload_bounds_inventory_and_final_serialized_response():
    checks = [
        ae.Check(
            id=f"warning_{i}",
            status=ae.WARN,
            bucket="documentation",
            severity=ae.WARN,
            detail="d" * 10_000,
            fix="f" * 10_000,
        )
        for i in range(400)
    ]
    inventory = {
        "datasets": 1_000,
        "terminal_datasets": ["x" * 1_000 for _ in range(1_000)],
    }

    payload = ae.build_payload("PROJ", checks, inventory)
    raw = ae.compact_audit_payload(payload)
    decoded = json.loads(raw)

    assert len(raw.encode("utf-8")) <= ae.MAX_AUDIT_RESPONSE_BYTES
    assert payload["inventory"]["truncated"]["terminal_datasets"] == {
        "total": 1_000,
        "returned": ae.MAX_INVENTORY_ITEMS,
    }
    assert decoded["response_truncated"] is True
    assert decoded["results_returned"] < decoded["results_total"]


def test_compact_payload_returns_small_payload_verbatim():
    # A payload under the ceiling is returned as-is — the single-pass fitter and
    # its truncation envelope only run on oversized payloads.
    checks = [
        ae.Check(id="w1", status=ae.WARN, bucket="structure", severity=ae.WARN, detail="d", fix="f"),
    ]
    payload = ae.build_payload("PROJ", checks, {"datasets": 1})
    decoded = json.loads(ae.compact_audit_payload(payload))
    assert "response_truncated" not in decoded
    assert decoded["checks"]["issues"]["rows"]


# --------------------------------------------------------------------------- #
# Fix strings: Cobuild / MCP actions, never `dku`
# --------------------------------------------------------------------------- #
def _all_checks_across_everything():
    proj = make_project(
        datasets={
            "src": {"count": 3},  # missing description
            "out": {"count": 0, "columns": [col("id")]},  # zero rows, undocumented col
            "tmp_scratch": {"count": 0},  # orphan dataset
        },
        recipes={"compute_out": {"type": "python"}, "prepare_2": {"type": "shell"}},
        nodes={"compute_out": recipe_node(["src"], ["out"])},
        zones=[FakeZone("z1", "Empty", {"items": [], "shortDesc": ""})],
    )
    actx = ae.load_context(proj, "PROJ")
    checks = []
    for bucket in ae.AUDIT_BUCKETS_ORDER:
        checks += ae.run_bucket(actx, bucket)
    contract = ae.normalize_contract(
        {"outputs": [{"dataset": "ghost", "columns": ["a"]}, {"dataset": "out", "columns": ["nope"], "min_rows": 9}]}
    )
    checks += ae.run_contract_checks(actx, contract)
    return checks


def test_fix_strings_reference_cobuild_or_mcp_never_dku():
    checks = _all_checks_across_everything()
    fixes = [c.fix for c in checks if c.status != "pass" and c.fix]
    assert fixes, "expected several failing/advisory checks to carry fixes"
    # The CRITICAL adaptation: no `dku ...` shell commands survive.
    for fix in fixes:
        assert "dku " not in fix, f"fix still references the dku CLI: {fix!r}"
    # Every fix is copy-paste actionable against THIS server: a Cobuild prompt or
    # a named MCP tool that exists on this chain.
    for fix in fixes:
        assert any(
            tool in fix
            for tool in ("Cobuild", "build_datasets")
        ), f"fix not actionable: {fix!r}"
    # The direct-action MCP tool is named where a build is the right move.
    assert any("build_datasets" in fix for fix in fixes)


# --------------------------------------------------------------------------- #
# Tool wrapper (async + Context + run_blocking)
# --------------------------------------------------------------------------- #
def test_tool_wrapper_runs_and_reports_per_bucket(monkeypatch):
    proj = _clean_project()
    monkeypatch.setattr(project_audit, "get_dss_client", lambda: FakeClient(proj))
    ctx = FakeCtx()
    result = asyncio.run(project_audit.audit_project("PROJ", ctx, buckets=["structure", "evidence"]))
    payload = json.loads(result)
    assert payload["project_key"] == "PROJ"
    assert payload["passed"] is True
    # ctx.info was emitted per bucket as it ran.
    assert any("structure" in m for m in ctx.infos)
    assert any("evidence" in m for m in ctx.infos)


def test_tool_wrapper_captures_client_before_first_await(monkeypatch):
    first = FakeClient(_clean_project())
    second = FakeClient(make_project())
    calls = []

    def current_client():
        calls.append(True)
        return first if len(calls) == 1 else second

    monkeypatch.setattr(project_audit, "get_dss_client", current_client)

    payload = json.loads(
        asyncio.run(
            project_audit.audit_project("PROJ", FakeCtx(), buckets=["structure"])
        )
    )

    assert payload["inventory"]["datasets"] == 2
    assert len(calls) == 1


def test_tool_wrapper_sanitizes_context_load_errors(monkeypatch):
    class LeakyClient:
        def get_project(self, key):
            raise RuntimeError("password=hunter2")

    monkeypatch.setattr(project_audit, "get_dss_client", LeakyClient)

    with pytest.raises(ValueError) as exc:
        asyncio.run(project_audit.audit_project("PROJ", FakeCtx()))

    assert "RuntimeError" in str(exc.value)
    assert "hunter2" not in str(exc.value)


def test_tool_wrapper_rejects_bad_bucket_and_contract(monkeypatch):
    proj = _clean_project()
    monkeypatch.setattr(project_audit, "get_dss_client", lambda: FakeClient(proj))
    with pytest.raises(ValueError, match="Invalid bucket"):
        asyncio.run(project_audit.audit_project("PROJ", FakeCtx(), buckets=["bogus"]))
    with pytest.raises(ValueError, match="outputs"):
        asyncio.run(project_audit.audit_project("PROJ", FakeCtx(), contract={"no_outputs": 1}))
