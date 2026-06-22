"""Tests for `dku project audit` (logic in commands/_project_audit.py)."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from dku_cli.commands import _project_audit
from dku_cli.main import app

runner = CliRunner()
ORIGINAL_FLOW_CHECK_CLEAN = _project_audit.flow_check_clean


# --- fake DSS project --------------------------------------------------------
class _Graph:
    def __init__(self, nodes):
        self.nodes = nodes


class _Zone:
    def __init__(self, raw):
        self.id = raw["id"]
        self.name = raw["name"]
        self._raw = raw


class _Flow:
    def __init__(self, state):
        self._state = state

    def get_graph(self):
        return _Graph(self._state["graph"]["nodes"])

    def list_zones(self):
        return [_Zone(z) for z in self._state["zones"]]

    def start_tool(self, tool_type):
        return _FlowCheckTool(self._state["flow_check_state"])


class _FlowCheckTool:
    def __init__(self, state):
        self._state = state
        self.stopped = False

    def update(self, payload):
        return self

    def wait_for_result(self):
        return None

    def get_state(self):
        return self._state

    def stop(self):
        self.stopped = True


class _Settings:
    def __init__(self, recipe):
        self._recipe = recipe

    def get_recipe_raw_definition(self):
        if self._recipe.get("metadata_error"):
            raise RuntimeError("metadata unavailable")
        return {
            "description": self._recipe.get("description", ""),
            "shortDesc": self._recipe.get("shortDesc", ""),
        }


class _Recipe:
    def __init__(self, recipe):
        self._recipe = recipe

    def get_settings(self):
        return _Settings(self._recipe)


class _Metrics:
    def __init__(self, value):
        self._value = value

    def get_global_value(self, metric_id):
        if self._value is None:
            raise KeyError(metric_id)
        return self._value


class _Dataset:
    def __init__(self, ds):
        self._ds = ds

    def get_metadata(self):
        if self._ds.get("metadata_error"):
            raise RuntimeError("metadata unavailable")
        # DSS dataset metadata exposes description (+ tags/checklists/custom) but
        # never a shortDesc — modelling that here is what keeps the audit honest.
        return {
            "description": self._ds.get("description", ""),
            "tags": self._ds.get("tags", []),
        }

    def get_definition(self):
        return {"schema": self._ds["schema"]}

    def iter_rows(self):
        names = [c["name"] for c in self._ds["schema"]["columns"]]
        for row in self._ds.get("rows", []):
            yield [row.get(n) for n in names]

    def get_last_metric_values(self):
        return _Metrics(self._ds.get("row_count"))

    def compute_metrics(self, metric_ids):
        return {
            "result": {
                "computed": [
                    {
                        "metricId": "records:COUNT_RECORDS",
                        "value": self._ds["row_count"],
                    }
                ]
            }
        }


class _Article:
    def __init__(self, art):
        self._art = art

    def get_data(self):
        return self

    def get_name(self):
        return self._art.get("title", "")

    def get_body(self):
        return self._art.get("body", "")


class _Wiki:
    def __init__(self, state):
        self._state = state

    def list_articles(self):
        return [_Article(a) for a in self._state["wiki_articles"]]


class FakeProject:
    def __init__(self, state):
        self._state = state

    def list_datasets(self):
        return [{"name": n, "type": "UploadedFiles"} for n in self._state["datasets"]]

    def list_recipes(self):
        return [
            {"name": n, "type": r["type"]} for n, r in self._state["recipes"].items()
        ]

    def get_flow(self):
        return _Flow(self._state)

    def get_dataset(self, name):
        return _Dataset(self._state["datasets"][name])

    def get_recipe(self, name):
        return _Recipe(self._state["recipes"][name])

    def get_wiki(self):
        return _Wiki(self._state)


def _base_state():
    return {
        "datasets": {
            "orders": {
                "description": "Raw source orders from the migration fixture.",
                "schema": {
                    "columns": [
                        {"name": "order_id", "type": "string"},
                        {"name": "amount", "type": "double"},
                    ]
                },
                "row_count": 2,
                "rows": [
                    {"order_id": "o1", "amount": 12.0},
                    {"order_id": "o2", "amount": 13.0},
                ],
            },
            "orders_by_customer": {
                "description": "Customer-grain output summarizing order value.",
                "schema": {
                    "columns": [
                        {
                            "name": "customer_id",
                            "type": "string",
                            "comment": "Customer key.",
                        },
                        {
                            "name": "total_amount",
                            "type": "double",
                            "comment": "Sum of orders.",
                        },
                    ]
                },
                "row_count": 2,
                "rows": [
                    {"customer_id": "c1", "total_amount": 12.0},
                    {"customer_id": "c2", "total_amount": 13.0},
                ],
            },
        },
        "recipes": {
            "group_orders_by_customer": {
                "type": "group",
                "description": "Aggregate orders to customer grain.",
                "shortDesc": "Aggregate orders to customer grain.",
            }
        },
        "wiki_articles": [
            {
                "title": "Runbook",
                "body": "## Purpose\nparity build.\n## Sources\norders.",
            }
        ],
        "graph": {
            "nodes": {
                "orders": {
                    "type": "COMPUTABLE_DATASET",
                    "successors": ["group_orders_by_customer"],
                    "predecessors": [],
                },
                "group_orders_by_customer": {
                    "type": "RUNNABLE_RECIPE",
                    "ref": "group_orders_by_customer",
                    "predecessors": ["orders"],
                    "successors": ["orders_by_customer"],
                },
                "orders_by_customer": {
                    "type": "COMPUTABLE_DATASET",
                    "predecessors": ["group_orders_by_customer"],
                    "successors": [],
                },
            }
        },
        "zones": [
            {
                "id": "z1",
                "name": "01 Build",
                "shortDesc": "Source and aggregate stage.",
                "items": [
                    {"objectId": "orders"},
                    {"objectId": "group_orders_by_customer"},
                    {"objectId": "orders_by_customer"},
                ],
            },
            {"id": "default", "name": "Default", "shortDesc": "", "items": []},
        ],
        "flow_check_state": {"stateByNode": {}},
    }


@pytest.fixture(autouse=True)
def _clean_flow(monkeypatch):
    monkeypatch.setattr(_project_audit, "flow_check_clean", lambda proj: (True, ""))


def _audit(state, **kwargs):
    return _project_audit.run_audit(FakeProject(state), "PROJ", **kwargs)


def _check(payload, check_id):
    return next(c for c in payload["checks"] if c["id"] == check_id)


def test_clean_project_passes():
    payload = _audit(_base_state())
    assert payload["passed"] is True
    assert payload["score"] == 1.0


def test_orphan_reference_dataset_fails():
    state = _base_state()
    state["datasets"]["expected_orders_by_customer"] = {
        "description": "Reference output from the source workflow.",
        "schema": {"columns": [{"name": "customer_id", "type": "string"}]},
        "row_count": 2,
        "rows": [{"customer_id": "c1"}, {"customer_id": "c2"}],
    }
    state["graph"]["nodes"]["expected_orders_by_customer"] = {
        "type": "COMPUTABLE_DATASET",
        "predecessors": [],
        "successors": [],
    }
    payload = _audit(state)
    assert payload["passed"] is False
    assert _check(payload, "no_orphan_datasets")["status"] == "fail"
    assert _check(payload, "reference_dataset_policy")["status"] == "warn"
    assert "expected_orders_by_customer" in payload["inventory"]["orphan_datasets"]


def test_output_descriptions_fail_recipes_only_warn():
    state = _base_state()
    state["datasets"]["orders_by_customer"]["description"] = "orders_by_customer"
    state["recipes"]["group_orders_by_customer"]["description"] = ""
    state["recipes"]["group_orders_by_customer"]["shortDesc"] = ""
    payload = _audit(state)
    assert payload["passed"] is False
    assert _check(payload, "datasets_have_descriptions")["status"] == "fail"
    assert "low-quality" in _check(payload, "datasets_have_descriptions")["detail"]
    assert _check(payload, "recipes_have_descriptions")["status"] == "warn"


def test_two_word_descriptions_are_accepted():
    state = _base_state()
    state["datasets"]["orders_by_customer"]["description"] = "Daily revenue"
    payload = _audit(state)
    assert _check(payload, "datasets_have_descriptions")["status"] == "pass"
    assert _check(payload, "flow_visible_descriptions")["status"] == "pass"


def test_flow_visible_passes_on_dataset_description_without_shortdesc():
    """Regression: a real DSS dataset has only `description` (never `shortDesc`).
    The base fixture's datasets are fully described that way, so the check must
    pass — previously it FAILed unsatisfiably by reading the absent shortDesc."""
    payload = _audit(_base_state())
    assert _check(payload, "flow_visible_descriptions")["status"] == "pass"
    assert payload["passed"] is True


def test_unreadable_metadata_does_not_abort_audit():
    state = _base_state()
    state["datasets"]["orders_by_customer"]["metadata_error"] = True
    state["recipes"]["group_orders_by_customer"]["metadata_error"] = True
    payload = _audit(state)
    assert payload["checks"]
    assert _check(payload, "datasets_have_descriptions")["status"] == "pass"
    assert _check(payload, "recipes_have_descriptions")["status"] == "pass"


def test_source_dataset_description_only_warns():
    state = _base_state()
    state["datasets"]["orders"]["description"] = ""
    state["datasets"]["orders"]["shortDesc"] = ""
    payload = _audit(state)
    check = _check(payload, "source_datasets_have_descriptions")
    assert check["status"] == "warn"
    assert "orders" in check["detail"]
    assert payload["passed"] is True


def test_flow_visible_terminal_missing_description_fails():
    state = _base_state()
    state["datasets"]["orders_by_customer"]["description"] = ""
    payload = _audit(state)
    check = _check(payload, "flow_visible_descriptions")
    assert payload["passed"] is False
    assert check["status"] == "fail"
    assert (
        "Terminal datasets without a description: orders_by_customer" in check["detail"]
    )
    assert "--description" in check["fix"]


def test_flow_visible_context_missing_description_warns():
    state = _base_state()
    state["datasets"]["orders"]["description"] = ""
    state["recipes"]["group_orders_by_customer"]["shortDesc"] = ""
    payload = _audit(state)
    check = _check(payload, "flow_visible_descriptions")
    assert payload["passed"] is True
    assert check["status"] == "warn"
    assert "Source datasets without a description: orders" in check["detail"]
    assert "Recipes without a description: group_orders_by_customer" in check["detail"]


def test_missing_wiki_warns_and_present_wiki_runbook_warns():
    state = _base_state()
    state["wiki_articles"] = []
    payload = _audit(state)
    assert _check(payload, "has_wiki")["status"] == "warn"

    state = _base_state()
    state["wiki_articles"] = [{"title": "Notes", "body": "some unrelated text"}]
    payload = _audit(state)
    assert _check(payload, "has_wiki")["status"] == "pass"
    assert _check(payload, "wiki_runbook")["status"] == "warn"


def test_wiki_runbook_needs_headings_not_prose():
    # Section words present only in prose must not satisfy the runbook.
    prose = "This is the purpose, and the source of all the data we use here."
    state = _base_state()
    state["wiki_articles"] = [{"title": "Runbook", "body": prose}]
    payload = _audit(state)
    assert _check(payload, "wiki_runbook")["status"] == "warn"

    # Purpose + sources as headings pass cleanly; outputs/rebuild not required.
    headed = "## Purpose\nWhat this builds.\n## Sources\nWhere data comes from.\n"
    state = _base_state()
    state["wiki_articles"] = [{"title": "Runbook", "body": headed}]
    payload = _audit(state)
    assert _check(payload, "wiki_runbook")["status"] == "pass"


def test_terminal_evidence_catches_empty_null_and_numeric_string():
    state = _base_state()
    state["datasets"]["orders_by_customer"]["schema"] = {
        "columns": [
            {"name": "customer_id", "type": "string"},
            {"name": "score", "type": "string"},
            {"name": "blank_result", "type": "string"},
        ]
    }
    state["datasets"]["orders_by_customer"]["rows"] = [
        {"customer_id": f"c{i}", "score": str(i), "blank_result": ""}
        for i in range(1, 6)
    ]
    state["datasets"]["orders_by_customer"]["rows"][1]["customer_id"] = ""
    payload = _audit(state)
    assert _check(payload, "all_null_columns")["status"] == "warn"
    assert _check(payload, "blank_key_columns")["status"] == "warn"
    assert _check(payload, "type_smells")["status"] == "warn"


def test_empty_terminal_output_fails():
    state = _base_state()
    state["datasets"]["orders_by_customer"]["row_count"] = 0
    state["datasets"]["orders_by_customer"]["rows"] = []
    payload = _audit(state)
    assert _check(payload, "terminal_outputs_built")["status"] == "fail"


def test_warnings_do_not_fail_the_gate():
    state = _base_state()
    state["zones"][0]["shortDesc"] = ""  # named zone with no short desc -> warn
    payload = _audit(state)
    assert _check(payload, "zones_have_short_desc")["status"] == "warn"
    assert payload["passed"] is True  # warnings are advisory, never block


def test_empty_named_zone_warns():
    state = _base_state()
    state["zones"].append(
        {"id": "z2", "name": "02 Staging", "shortDesc": "", "items": []}
    )
    payload = _audit(state)
    assert _check(payload, "empty_zones")["status"] == "warn"
    assert "02 Staging" in _check(payload, "empty_zones")["detail"]
    # An empty DEFAULT zone is the goal, not a smell — base state must stay clean.
    assert _check(_audit(_base_state()), "empty_zones")["status"] == "pass"


def test_zone_coverage_warns_when_zoning_is_partial():
    # The project has a named zone, so coverage is enforced. Leave one dataset out.
    state = _base_state()
    state["zones"][0]["items"] = [{"objectId": "orders"}]
    payload = _audit(state)
    assert _check(payload, "zone_coverage")["status"] == "warn"


def test_zone_coverage_includes_recipes():
    state = _base_state()
    state["zones"][0]["items"] = [
        {"objectId": "orders"},
        {"objectId": "orders_by_customer"},
    ]
    payload = _audit(state)
    check = _check(payload, "zone_coverage")
    assert check["status"] == "warn"
    assert "group_orders_by_customer" in check["detail"]


def test_zone_coverage_skipped_without_named_zones():
    state = _base_state()
    state["zones"] = [
        {"id": "default", "name": "Default", "shortDesc": "", "items": []}
    ]
    payload = _audit(state)
    assert all(c["id"] != "zone_coverage" for c in payload["checks"])


def test_non_trivial_flow_without_named_zones_warns():
    state = _base_state()
    for i in range(4):
        name = f"prepare_extra_{i}"
        state["recipes"][name] = {
            "type": "shaker",
            "description": f"Extra prepare recipe {i}.",
            "shortDesc": f"Extra prepare {i}.",
        }
        state["graph"]["nodes"][name] = {
            "type": "RUNNABLE_RECIPE",
            "predecessors": ["orders"],
            "successors": ["orders_by_customer"],
        }
    state["zones"] = [
        {"id": "default", "name": "Default", "shortDesc": "", "items": []}
    ]
    payload = _audit(state)
    check = _check(payload, "flow_zones_present")
    assert payload["passed"] is True
    assert check["status"] == "warn"


def test_contract_checks_columns_types_min_rows_and_not_blank():
    state = _base_state()
    contract = {
        "outputs": {
            "orders_by_customer": {
                "min_rows": 3,
                "columns": ["customer_id", "missing_col"],
                "types": {"total_amount": "string"},
                "not_blank": ["customer_id"],
            }
        }
    }
    payload = _audit(state, contract=contract)
    assert payload["passed"] is False
    assert _check(payload, "contract_columns:orders_by_customer")["status"] == "fail"
    assert _check(payload, "contract_types:orders_by_customer")["status"] == "fail"
    assert _check(payload, "contract_min_rows:orders_by_customer")["status"] == "fail"


def test_contract_missing_output_fails_structured():
    payload = _audit(
        _base_state(),
        contract={"outputs": {"missing_output": {"min_rows": 1}}},
    )

    check = _check(payload, "contract_output_exists:missing_output")
    assert payload["passed"] is False
    assert check["status"] == "fail"
    assert "missing_output" in check["detail"]


def test_unknown_cached_row_count_warns():
    state = _base_state()
    state["datasets"]["orders_by_customer"]["row_count"] = None  # no cached metric
    payload = _audit(state)
    assert _check(payload, "terminal_row_counts")["status"] == "warn"
    assert "--recompute" in _check(payload, "terminal_row_counts")["fix"]


def test_terminal_columns_undocumented_warns():
    state = _base_state()
    for col in state["datasets"]["orders_by_customer"]["schema"]["columns"]:
        col.pop("comment", None)
    payload = _audit(state)
    assert _check(payload, "terminal_columns_documented")["status"] == "warn"
    assert payload["passed"] is True  # warn only


def test_blank_name_column_does_not_fail_gate():
    state = _base_state()
    state["datasets"]["orders_by_customer"]["schema"]["columns"] = [
        {"name": "customer_name", "type": "string", "comment": "Name."},
    ]
    state["datasets"]["orders_by_customer"]["rows"] = [
        {"customer_name": "" if i == 0 else f"n{i}"} for i in range(5)
    ]
    payload = _audit(state)
    assert _check(payload, "blank_key_columns")["status"] == "pass"


def test_numbered_business_names_are_not_lazy_names():
    state = _base_state()
    state["recipes"]["region_5"] = state["recipes"].pop("group_orders_by_customer")
    state["datasets"]["top_10"] = state["datasets"].pop("orders_by_customer")
    state["graph"]["nodes"]["region_5"] = state["graph"]["nodes"].pop(
        "group_orders_by_customer"
    )
    state["graph"]["nodes"]["region_5"]["successors"] = ["top_10"]
    state["graph"]["nodes"]["top_10"] = state["graph"]["nodes"].pop(
        "orders_by_customer"
    )
    state["graph"]["nodes"]["top_10"]["predecessors"] = ["region_5"]
    state["graph"]["nodes"]["orders"]["successors"] = ["region_5"]
    state["zones"][0]["items"] = [
        {"objectId": "orders"},
        {"objectId": "region_5"},
        {"objectId": "top_10"},
    ]
    payload = _audit(state)
    assert _check(payload, "recipe_naming")["status"] == "pass"
    assert _check(payload, "dataset_naming")["status"] == "pass"


def test_copy_default_names_still_warn():
    state = _base_state()
    state["recipes"]["orders_copy"] = {
        "type": "group",
        "description": "Copied recipe for testing.",
        "shortDesc": "Copied recipe.",
    }
    state["graph"]["nodes"]["orders_copy"] = {
        "type": "RUNNABLE_RECIPE",
        "predecessors": ["orders"],
        "successors": ["orders_by_customer"],
    }
    payload = _audit(state)
    assert _check(payload, "recipe_naming")["status"] == "warn"


def test_flow_check_clean_parses_fatal_messages():
    state = _base_state()
    state["flow_check_state"] = {
        "stateByNode": {
            "bad_recipe": {
                "recipeCheckResult": {
                    "messages": [{"severity": "ERROR", "message": "Schema mismatch"}]
                }
            }
        }
    }
    clean, message = ORIGINAL_FLOW_CHECK_CLEAN(FakeProject(state))
    assert clean is False
    assert message == "bad_recipe: Schema mismatch"


def test_flow_check_clean_passes_without_errors():
    clean, message = ORIGINAL_FLOW_CHECK_CLEAN(FakeProject(_base_state()))
    assert clean is True
    assert message == ""


def test_bucket_filter_runs_only_selected():
    payload = _audit(_base_state(), buckets={"structure"})
    ids = {c["id"] for c in payload["checks"]}
    assert "no_orphan_datasets" in ids
    assert "has_wiki" not in ids  # documentation skipped
    assert "flow_check_clean" not in ids  # evidence skipped


# --- CLI wiring --------------------------------------------------------------
def test_cli_exit_code_and_json(monkeypatch, patch_client):
    monkeypatch.setattr(_project_audit, "flow_check_clean", lambda proj: (True, ""))
    monkeypatch.setattr(
        _project_audit,
        "run_audit",
        lambda *a, **k: {
            "passed": False,
            "summary": "1 check(s) failed",
            "score": 0.9,
            "checks": [
                {
                    "id": "no_orphan_datasets",
                    "status": "fail",
                    "bucket": "structure",
                    "severity": "fail",
                    "detail": "Datasets not connected to any recipe: stray",
                    "fix": "delete, connect, or document reference datasets: stray",
                }
            ],
            "inventory": {"datasets": 1},
        },
    )
    result = runner.invoke(app, ["--format", "json", "project", "audit", "-P", "PROJ"])
    assert result.exit_code == 1
    parsed = json.loads(result.output)
    assert parsed["passed"] is False
    assert parsed["score"] == 0.9


def test_cli_passes_flags_through(monkeypatch, patch_client):
    captured = {}

    def fake_audit(proj, project, **kwargs):
        captured.update(kwargs)
        return {
            "passed": True,
            "summary": "passed",
            "score": 1.0,
            "checks": [],
            "inventory": {},
        }

    monkeypatch.setattr(_project_audit, "run_audit", fake_audit)
    result = runner.invoke(
        app,
        [
            "project",
            "audit",
            "-P",
            "PROJ",
            "--bucket",
            "structure",
            "--bucket",
            "evidence",
        ],
    )
    assert result.exit_code == 0
    assert captured["buckets"] == {"structure", "evidence"}


def test_cli_contract_requires_evidence_bucket(patch_client):
    result = runner.invoke(
        app,
        [
            "project",
            "audit",
            "-P",
            "PROJ",
            "--bucket",
            "structure",
            "--contract",
            '{"outputs":{}}',
        ],
    )
    assert result.exit_code == 2
    assert "--bucket evidence" in result.output


def test_cli_bad_contract_exits_usage_error(patch_client):
    result = runner.invoke(
        app,
        [
            "project",
            "audit",
            "-P",
            "PROJ",
            "--contract",
            "{not-json}",
        ],
    )
    assert result.exit_code == 2
    assert "Could not read --contract" in result.output
