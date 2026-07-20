"""Tests for the generic ``get_object_settings`` deep-read.

These never touch the network: ``get_dss_client`` is replaced by a fake client
returning a fake project whose per-type accessors hand back canned raw settings.
The tool under test is the one INDEPENDENT read path over the object types
Cobuild builds (agents, dashboards, wikis, semantic models, …) — the thing that
lets a supervisor verify Cobuild's report instead of taking its word.

Coverage: happy path for several object types, a parameterized dispatch contract
over ALL enum members, the closed-enum rejection, the version-argument rules and
version-discovery payloads, structure-aware secret redaction, and the hard
FINAL-serialized byte ceiling (escaping included).
"""

import asyncio
import json

import pytest
from dataikuapi.utils import DataikuException

from dataiku_mcp.tools import object_settings


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #


class FakeCtx:
    def __init__(self):
        self.infos = []

    async def info(self, message, **kwargs):
        self.infos.append(message)


class FakeSettings:
    def __init__(self, raw):
        self._raw = raw

    def get_raw(self):
        return self._raw


class _Settingsable:
    """An object exposing ``.get_settings().get_raw()`` over a canned dict."""

    def __init__(self, raw):
        self._raw = raw

    def get_settings(self):
        return FakeSettings(self._raw)


class FakeArticleData:
    def __init__(self, name, body):
        self._name = name
        self._body = body

    def get_name(self):
        return self._name

    def get_body(self):
        return self._body


class FakeArticle:
    def __init__(self, data):
        self._data = data

    def get_data(self):
        return self._data


class FakeWiki:
    def __init__(self, articles):
        self._articles = articles

    def get_article(self, article_id):
        if article_id not in self._articles:
            raise DataikuException(f"no such article {article_id}")
        return FakeArticle(self._articles[article_id])


class FakeAgent:
    def __init__(self, raw):
        self._raw = raw

    def get_settings(self):
        return FakeSettings(self._raw)


class FakeReview:
    def __init__(self, raw):
        self._raw = raw

    def get_raw(self):
        return self._raw


# --- Semantic model: mirrors the REAL SDK, which raises a plain Exception (not
# DataikuException) for an unknown version and for a missing active version. --- #
class FakeSemVersion:
    def __init__(self, versions, version_id):
        self._versions = versions
        self._version_id = version_id

    def get_settings(self):
        if self._version_id not in self._versions:
            raise Exception(f"Version {self._version_id} not found")
        return FakeSettings(self._versions[self._version_id])


class FakeSemanticModel:
    def __init__(self, versions, active_version_id=None):
        self._versions = versions
        self._active = active_version_id

    def get_active_version_id(self):
        if self._active is None:
            raise Exception("No active version set")
        return self._active

    def list_versions_ids(self):
        return list(self._versions)

    def get_version(self, version_id):
        return FakeSemVersion(self._versions, version_id)


class FakeVersionDetails:
    def __init__(self, snippet):
        self._snippet = snippet

    def get_raw_snippet(self):
        return self._snippet


class FakeSavedModel:
    def __init__(self, versions, version_list=None):
        self._versions = versions
        self._version_list = version_list or [
            {"id": vid, "active": i == 0} for i, vid in enumerate(versions)
        ]

    def list_versions(self):
        return self._version_list

    def get_version_details(self, version_id):
        if version_id not in self._versions:
            raise DataikuException(f"no such version {version_id}")
        return FakeVersionDetails(self._versions[version_id])


# --- ML analysis ----------------------------------------------------------- #
class FakeMLTask:
    def __init__(self, raw):
        self._raw = raw

    def get_settings(self):
        return FakeSettings(self._raw)


class FakeAnalysis:
    def __init__(self, analysis_id, name, mltask_id, mltask_settings):
        self.analysis_id = analysis_id
        self._name = name
        self._mltask_id = mltask_id
        self._mltask_settings = mltask_settings

    def list_ml_tasks(self):
        return {"mlTasks": [{"mlTaskId": self._mltask_id}]}

    def get_ml_task(self, mltask_id):
        return FakeMLTask(self._mltask_settings)

    def get_definition(self):
        return FakeSettings({"name": self._name})


# --- Evaluation store -------------------------------------------------------- #
class FakeEvalInfo:
    def __init__(self, **kwargs):
        self.user_meta = kwargs.get("user_meta", {})
        self.creation_date = kwargs.get("creation_date")
        self.prediction_type = kwargs.get("prediction_type")
        self.target_variable = kwargs.get("target_variable")
        self.prediction_variable = kwargs.get("prediction_variable")
        self.metrics = kwargs.get("metrics", {})


class FakeEvaluation:
    def __init__(self, evaluation_id, info):
        self.evaluation_id = evaluation_id
        self._info = info

    def get_full_info(self):
        return self._info


class _SettingsWrap:
    """Evaluation store settings expose ``.settings`` (a dict), not ``.get_raw()``."""

    def __init__(self, settings):
        self.settings = settings


class FakeEvalStore:
    def __init__(self, settings, evaluations):
        self._settings = settings
        self._evaluations = evaluations

    def get_settings(self):
        return _SettingsWrap(self._settings)

    def list_evaluations(self):
        return self._evaluations


class FakeProject:
    def __init__(
        self,
        *,
        dashboards=None,
        insights=None,
        webapps=None,
        knowledge_banks=None,
        rag_llms=None,
        agent_tools=None,
        wiki_articles=None,
        agents=None,
        semantic_models=None,
        saved_models=None,
        reviews=None,
        analyses=None,
        analysis_inputs=None,
        eval_stores=None,
    ):
        self._dashboards = dashboards or {}
        self._insights = insights or {}
        self._webapps = webapps or {}
        self._knowledge_banks = knowledge_banks or {}
        self._rag_llms = rag_llms or {}
        self._agent_tools = agent_tools or {}
        self._wiki = FakeWiki(wiki_articles or {})
        self._agents = agents or {}
        self._semantic_models = semantic_models or {}
        self._saved_models = saved_models or {}
        self._reviews = reviews or {}
        self._analyses = analyses or {}
        self._analysis_inputs = analysis_inputs or {}
        self._eval_stores = eval_stores or {}
        self.calls = []

    def _get(self, store, kind, object_id, factory):
        self.calls.append((kind, object_id))
        if object_id not in store:
            raise DataikuException(f"no such {kind} {object_id}")
        return factory(store[object_id])

    def get_dashboard(self, object_id):
        return self._get(self._dashboards, "dashboard", object_id, _Settingsable)

    def get_insight(self, object_id):
        return self._get(self._insights, "insight", object_id, _Settingsable)

    def get_webapp(self, object_id):
        return self._get(self._webapps, "webapp", object_id, _Settingsable)

    def get_knowledge_bank(self, object_id):
        return self._get(self._knowledge_banks, "knowledge_bank", object_id, _Settingsable)

    def get_retrieval_augmented_llm(self, object_id):
        return self._get(self._rag_llms, "retrieval_augmented_llm", object_id, _Settingsable)

    def get_agent_tool(self, object_id):
        return self._get(self._agent_tools, "agent_tool", object_id, _Settingsable)

    def get_wiki(self):
        self.calls.append(("wiki", None))
        return self._wiki

    def get_agent(self, object_id):
        return self._get(self._agents, "agent", object_id, FakeAgent)

    def get_semantic_model(self, object_id):
        self.calls.append(("semantic_model", object_id))
        if object_id not in self._semantic_models:
            raise DataikuException(f"no such semantic model {object_id}")
        spec = self._semantic_models[object_id]
        return FakeSemanticModel(spec["versions"], spec.get("active"))

    def get_saved_model(self, object_id):
        self.calls.append(("saved_model", object_id))
        if object_id not in self._saved_models:
            raise DataikuException(f"no such saved model {object_id}")
        return FakeSavedModel(self._saved_models[object_id])

    def get_agent_review(self, object_id):
        return self._get(self._reviews, "agent_review", object_id, FakeReview)

    def get_analysis(self, object_id):
        self.calls.append(("analysis", object_id))
        if object_id not in self._analyses:
            raise DataikuException(f"no such analysis {object_id}")
        return self._analyses[object_id]

    def list_analyses(self):
        return [
            {"analysisId": aid, "inputDataset": ds}
            for aid, ds in self._analysis_inputs.items()
        ]

    def get_model_evaluation_store(self, object_id):
        self.calls.append(("evaluation_store", object_id))
        if object_id not in self._eval_stores:
            raise DataikuException(f"no such evaluation store {object_id}")
        return self._eval_stores[object_id]


class FakeClient:
    def __init__(self, project):
        self._project = project

    def get_project(self, project_key):
        return self._project


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def run(coro):
    return asyncio.run(coro)


def bind(monkeypatch, project):
    monkeypatch.setattr(object_settings, "get_dss_client", lambda: FakeClient(project))


def call(project_key="PROJ", **kwargs):
    return json.loads(
        run(object_settings.get_object_settings(project_key, ctx=FakeCtx(), **kwargs))
    )


def raw_call(project_key="PROJ", **kwargs):
    return run(object_settings.get_object_settings(project_key, ctx=FakeCtx(), **kwargs))


# --------------------------------------------------------------------------- #
# Happy paths
# --------------------------------------------------------------------------- #


def test_dashboard_happy_path(monkeypatch):
    bind(monkeypatch, FakeProject(dashboards={"dash1": {"pages": [{"id": "p1"}]}}))
    out = call(object_type="dashboard", object_id="dash1")
    assert out["object_type"] == "dashboard"
    assert out["object_id"] == "dash1"
    assert out["settings"] == {"pages": [{"id": "p1"}]}


def test_wiki_article_happy_path(monkeypatch):
    bind(
        monkeypatch,
        FakeProject(wiki_articles={"home": FakeArticleData("Home", "# Welcome")}),
    )
    out = call(object_type="wiki_article", object_id="home")
    assert out["settings"] == {"name": "Home", "body": "# Welcome"}


def test_agent_full_settings_without_version(monkeypatch):
    raw = {"id": "a1", "type": "TOOLS_USING_AGENT", "versions": [{"versionId": "v1"}]}
    bind(monkeypatch, FakeProject(agents={"a1": raw}))
    out = call(object_type="agent", object_id="a1")
    assert out["settings"] == raw
    assert "version_id" not in out


def test_agent_single_version_when_version_given(monkeypatch):
    raw = {
        "id": "a1",
        "type": "TOOLS_USING_AGENT",
        "versions": [{"versionId": "v1", "x": 1}, {"versionId": "v2", "x": 2}],
    }
    bind(monkeypatch, FakeProject(agents={"a1": raw}))
    out = call(object_type="agent", object_id="a1", version_id="v2")
    assert out["version_id"] == "v2"
    assert "versions" not in out["settings"]
    assert out["settings"]["version"] == {"versionId": "v2", "x": 2}


def test_semantic_model_version_detail(monkeypatch):
    bind(
        monkeypatch,
        FakeProject(
            semantic_models={"sm1": {"versions": {"v3": {"entities": ["orders"]}}}}
        ),
    )
    out = call(object_type="semantic_model", object_id="sm1", version_id="v3")
    assert out["version_id"] == "v3"
    assert out["settings"] == {"entities": ["orders"]}


def test_saved_model_version_detail(monkeypatch):
    bind(monkeypatch, FakeProject(saved_models={"sm": {"v1": {"auc": 0.9}}}))
    out = call(object_type="saved_model", object_id="sm", version_id="v1")
    assert out["settings"]["snippet"] == {"auc": 0.9}
    assert out["settings"]["details_class"] == "FakeVersionDetails"


def test_ml_analysis_includes_input_dataset(monkeypatch):
    bind(
        monkeypatch,
        FakeProject(
            analyses={
                "an1": FakeAnalysis("an1", "Churn", "mltask-1", {"algo": ["RF"]})
            },
            analysis_inputs={"an1": "customers"},
        ),
    )
    out = call(object_type="ml_analysis", object_id="an1")
    assert out["settings"]["analysis_name"] == "Churn"
    assert out["settings"]["input_dataset"] == "customers"  # finding 5
    assert out["settings"]["mltask_id"] == "mltask-1"
    assert out["settings"]["mltask_settings"] == {"algo": ["RF"]}


def test_evaluation_store_includes_evaluation_summary(monkeypatch):
    info = FakeEvalInfo(
        user_meta={"name": "eval-A", "labels": ["prod"]},
        creation_date=1000,
        prediction_type="BINARY_CLASSIFICATION",
        target_variable="churned",
        prediction_variable="prediction",
        metrics={"auc": 0.87},
    )
    store = FakeEvalStore(
        settings={"name": "store", "mesFlavor": "TABULAR"},
        evaluations=[FakeEvaluation("ev1", info)],
    )
    bind(monkeypatch, FakeProject(eval_stores={"es1": store}))
    out = call(object_type="evaluation_store", object_id="es1")
    assert out["settings"]["store_settings"]["mesFlavor"] == "TABULAR"
    evals = out["settings"]["evaluations"]  # finding 2
    assert evals[0]["evaluation_id"] == "ev1"
    assert evals[0]["name"] == "eval-A"
    assert evals[0]["metrics"] == {"auc": 0.87}
    assert evals[0]["prediction_type"] == "BINARY_CLASSIFICATION"


# --------------------------------------------------------------------------- #
# Version discovery (finding 3)
# --------------------------------------------------------------------------- #


def test_saved_model_without_version_returns_discovery(monkeypatch):
    bind(monkeypatch, FakeProject(saved_models={"sm": {"v1": {}, "v2": {}}}))
    out = call(object_type="saved_model", object_id="sm")
    assert "version_id" not in out
    assert out["settings"]["discovery"] is True
    ids = {v["id"] for v in out["settings"]["versions"]}
    assert ids == {"v1", "v2"}
    assert any(v["active"] for v in out["settings"]["versions"])


def test_semantic_model_without_version_returns_discovery(monkeypatch):
    bind(
        monkeypatch,
        FakeProject(
            semantic_models={
                "sm1": {"versions": {"v1": {}, "v2": {}}, "active": "v2"}
            }
        ),
    )
    out = call(object_type="semantic_model", object_id="sm1")
    assert out["settings"]["discovery"] is True
    assert out["settings"]["active_version_id"] == "v2"
    assert set(out["settings"]["version_ids"]) == {"v1", "v2"}


def test_semantic_model_unknown_version_is_normalized_to_value_error(monkeypatch):
    # The real SDK raises a plain Exception for an unknown version; the tool must
    # surface the same clear ValueError as every other bad-version path.
    bind(
        monkeypatch,
        FakeProject(semantic_models={"sm1": {"versions": {"v1": {"a": 1}}}}),
    )
    with pytest.raises(ValueError) as exc:
        call(object_type="semantic_model", object_id="sm1", version_id="nope")
    assert "nope" in str(exc.value) and "semantic_model" in str(exc.value)


# --------------------------------------------------------------------------- #
# Parameterized dispatch contract over ALL 13 enum members (finding 7)
# --------------------------------------------------------------------------- #

DISPATCH_CASES = [
    (
        "wiki_article",
        "home",
        {},
        dict(wiki_articles={"home": FakeArticleData("Home", "body")}),
        ("wiki", None),
        {"name": "Home", "body": "body"},
    ),
    (
        "dashboard",
        "d",
        {},
        dict(dashboards={"d": {"k": 1}}),
        ("dashboard", "d"),
        {"k": 1},
    ),
    (
        "insight",
        "i",
        {},
        dict(insights={"i": {"k": 2}}),
        ("insight", "i"),
        {"k": 2},
    ),
    (
        "webapp",
        "w",
        {},
        dict(webapps={"w": {"k": 3}}),
        ("webapp", "w"),
        {"k": 3},
    ),
    (
        "knowledge_bank",
        "kb",
        {},
        dict(knowledge_banks={"kb": {"k": 4}}),
        ("knowledge_bank", "kb"),
        {"k": 4},
    ),
    (
        "retrieval_augmented_llm",
        "rag",
        {},
        dict(rag_llms={"rag": {"k": 5}}),
        ("retrieval_augmented_llm", "rag"),
        {"k": 5},
    ),
    (
        "agent_tool",
        "at",
        {},
        dict(agent_tools={"at": {"k": 6}}),
        ("agent_tool", "at"),
        {"k": 6},
    ),
    (
        "agent_review",
        "ar",
        {},
        dict(reviews={"ar": {"k": 7}}),
        ("agent_review", "ar"),
        {"k": 7},
    ),
    (
        "agent",
        "a1",
        {},
        dict(agents={"a1": {"id": "a1", "versions": []}}),
        ("agent", "a1"),
        {"id": "a1", "versions": []},
    ),
    (
        "semantic_model",
        "sm1",
        {"version_id": "v1"},
        dict(semantic_models={"sm1": {"versions": {"v1": {"e": []}}}}),
        ("semantic_model", "sm1"),
        {"e": []},
    ),
    (
        "saved_model",
        "sm",
        {"version_id": "v1"},
        dict(saved_models={"sm": {"v1": {"auc": 0.9}}}),
        ("saved_model", "sm"),
        None,  # composed snippet envelope, checked separately
    ),
    (
        "ml_analysis",
        "an1",
        {},
        dict(
            analyses={"an1": FakeAnalysis("an1", "N", "mt", {"s": 1})},
            analysis_inputs={"an1": "ds"},
        ),
        ("analysis", "an1"),
        None,  # composed envelope, checked separately
    ),
    (
        "evaluation_store",
        "es1",
        {},
        dict(
            eval_stores={
                "es1": FakeEvalStore({"name": "s"}, [])
            }
        ),
        ("evaluation_store", "es1"),
        None,  # composed envelope, checked separately
    ),
]


@pytest.mark.parametrize(
    "object_type,object_id,extra,project_kwargs,expected_call,expected_settings",
    DISPATCH_CASES,
    ids=[c[0] for c in DISPATCH_CASES],
)
def test_dispatch_contract(
    monkeypatch,
    object_type,
    object_id,
    extra,
    project_kwargs,
    expected_call,
    expected_settings,
):
    project = FakeProject(**project_kwargs)
    bind(monkeypatch, project)
    out = call(object_type=object_type, object_id=object_id, **extra)
    # Envelope shape.
    assert out["object_type"] == object_type
    assert out["object_id"] == object_id
    assert "settings" in out
    # Right dataikuapi accessor chain was reached.
    assert expected_call in project.calls
    if expected_settings is not None:
        assert out["settings"] == expected_settings


def test_dispatch_cases_cover_every_enum_member():
    assert {c[0] for c in DISPATCH_CASES} == set(object_settings._OBJECT_TYPES)


# --------------------------------------------------------------------------- #
# Enum + version argument rules
# --------------------------------------------------------------------------- #


def test_unknown_object_type_lists_valid_types(monkeypatch):
    bind(monkeypatch, FakeProject())
    with pytest.raises(ValueError) as exc:
        call(object_type="dataset", object_id="x")
    message = str(exc.value)
    assert "object_type" in message
    # The error enumerates the closed set of valid types.
    assert "dashboard" in message and "agent" in message and "wiki_article" in message


def test_missing_object_is_actionable_error(monkeypatch):
    bind(monkeypatch, FakeProject(dashboards={}))
    with pytest.raises(ValueError) as exc:
        call(object_type="dashboard", object_id="ghost")
    assert "dashboard" in str(exc.value) and "ghost" in str(exc.value)


def test_version_required_type_without_version_returns_discovery(monkeypatch):
    # After finding 3, saved_model/semantic_model no longer error without a
    # version — they hand back a discovery payload.
    bind(monkeypatch, FakeProject(saved_models={"sm": {"v1": {}}}))
    out = call(object_type="saved_model", object_id="sm")
    assert out["settings"]["discovery"] is True


def test_version_on_non_versioned_type_errors(monkeypatch):
    bind(monkeypatch, FakeProject(dashboards={"d": {}}))
    with pytest.raises(ValueError) as exc:
        call(object_type="dashboard", object_id="d", version_id="v1")
    assert "version_id" in str(exc.value)


# --------------------------------------------------------------------------- #
# Redaction (findings 1)
# --------------------------------------------------------------------------- #


def test_secret_keys_are_redacted(monkeypatch):
    raw = {
        "type": "STANDARD",
        "apiKey": "super-secret",
        "config": {"password": "hunter2", "endpoint": "https://x"},
    }
    bind(monkeypatch, FakeProject(dashboards={"d": raw}))
    out = call(object_type="dashboard", object_id="d")
    assert out["settings"]["apiKey"] == object_settings.VARIABLE_REDACTION
    assert out["settings"]["config"]["password"] == object_settings.VARIABLE_REDACTION
    # Non-sensitive values survive.
    assert out["settings"]["config"]["endpoint"] == "https://x"
    assert out["settings"]["type"] == "STANDARD"


def test_inline_secret_param_value_redacted_metadata_preserved(monkeypatch):
    # The finding-1 shape: a structured-agent param carries the secret INLINE as
    # a sibling of its own key/secret metadata. The masked field must be the
    # VALUE, and the key + secret flag must survive for wiring verification.
    raw = {
        "params": [
            {"key": "api_key", "value": "sk-live-DEADBEEF", "secret": True},
            {"key": "temperature", "value": "0.2", "secret": False},
        ]
    }
    bind(monkeypatch, FakeProject(agent_tools={"t": raw}))
    out = call(object_type="agent_tool", object_id="t")
    secret_entry, plain_entry = out["settings"]["params"]
    # Secret value gone; key + secret flag intact.
    assert secret_entry["value"] == object_settings.VARIABLE_REDACTION
    assert secret_entry["key"] == "api_key"
    assert secret_entry["secret"] is True
    assert "sk-live" not in json.dumps(out)
    # Non-secret sibling fully preserved.
    assert plain_entry == {"key": "temperature", "value": "0.2", "secret": False}


# --------------------------------------------------------------------------- #
# Bounding — FINAL serialized ceiling (finding 4)
# --------------------------------------------------------------------------- #


def test_oversized_settings_are_bounded(monkeypatch):
    big = {"blob": "x" * (object_settings.MAX_SETTINGS_BYTES + 5000)}
    bind(monkeypatch, FakeProject(dashboards={"d": big}))
    out = call(object_type="dashboard", object_id="d")
    assert out["truncated"] is True
    assert "settings" not in out
    assert out["total_bytes"] > object_settings.MAX_SETTINGS_BYTES
    assert out["returned_bytes"] <= object_settings.MAX_SETTINGS_BYTES
    assert isinstance(out["settings_json_truncated"], str)


def test_quote_heavy_payload_final_response_within_ceiling(monkeypatch):
    # A quote/backslash-heavy payload (WebApp code) doubles in size when escaped
    # into the outer envelope. The ceiling must bind the FINAL serialized MCP
    # result, not the pre-escape inner settings JSON.
    payload = {"code": '"' * (object_settings.MAX_SETTINGS_BYTES + 200_000)}
    bind(monkeypatch, FakeProject(webapps={"w": payload}))
    raw = raw_call(object_type="webapp", object_id="w")
    assert len(raw.encode("utf-8")) <= object_settings.MAX_SETTINGS_BYTES
    out = json.loads(raw)
    assert out["truncated"] is True
    assert out["returned_bytes"] <= object_settings.MAX_SETTINGS_BYTES
    # Byte counts stay truthful: the reported total exceeds the ceiling.
    assert out["total_bytes"] > object_settings.MAX_SETTINGS_BYTES
