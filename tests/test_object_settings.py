"""Tests for the generic ``get_object_settings`` deep-read.

These never touch the network: ``get_dss_client`` is replaced by a fake client
returning a fake project whose per-type accessors hand back canned raw settings.
The tool under test is the one INDEPENDENT read path over the object types
Cobuild builds (agents, dashboards, wikis, semantic models, …) — the thing that
lets a supervisor verify Cobuild's report instead of taking its word.

Coverage: happy path for several object types, the closed-enum rejection, the
version-argument rules, secret redaction, and the hard byte-ceiling bounding.
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


class FakeVersion:
    def __init__(self, raw):
        self._raw = raw

    def get_settings(self):
        return FakeSettings(self._raw)


class FakeSemanticModel:
    def __init__(self, versions):
        self._versions = versions

    def get_version(self, version_id):
        if version_id not in self._versions:
            raise DataikuException(f"no such version {version_id}")
        return FakeVersion(self._versions[version_id])


class FakeVersionDetails:
    def __init__(self, snippet):
        self._snippet = snippet

    def get_raw_snippet(self):
        return self._snippet


class FakeSavedModel:
    def __init__(self, versions):
        self._versions = versions

    def get_version_details(self, version_id):
        if version_id not in self._versions:
            raise DataikuException(f"no such version {version_id}")
        return FakeVersionDetails(self._versions[version_id])


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


class FakeProject:
    def __init__(
        self,
        *,
        dashboards=None,
        wiki_articles=None,
        agents=None,
        semantic_models=None,
        saved_models=None,
        reviews=None,
    ):
        self._dashboards = dashboards or {}
        self._wiki = FakeWiki(wiki_articles or {})
        self._agents = agents or {}
        self._semantic_models = semantic_models or {}
        self._saved_models = saved_models or {}
        self._reviews = reviews or {}

    def get_dashboard(self, object_id):
        if object_id not in self._dashboards:
            raise DataikuException(f"no such dashboard {object_id}")
        return _Settingsable(self._dashboards[object_id])

    def get_wiki(self):
        return self._wiki

    def get_agent(self, object_id):
        if object_id not in self._agents:
            raise DataikuException(f"no such agent {object_id}")
        return FakeAgent(self._agents[object_id])

    def get_semantic_model(self, object_id):
        if object_id not in self._semantic_models:
            raise DataikuException(f"no such semantic model {object_id}")
        return FakeSemanticModel(self._semantic_models[object_id])

    def get_saved_model(self, object_id):
        if object_id not in self._saved_models:
            raise DataikuException(f"no such saved model {object_id}")
        return FakeSavedModel(self._saved_models[object_id])

    def get_agent_review(self, object_id):
        if object_id not in self._reviews:
            raise DataikuException(f"no such review {object_id}")
        return FakeReview(self._reviews[object_id])


class _Settingsable:
    """An object exposing ``.get_settings().get_raw()`` over a canned dict."""

    def __init__(self, raw):
        self._raw = raw

    def get_settings(self):
        return FakeSettings(self._raw)


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


def test_semantic_model_requires_and_uses_version(monkeypatch):
    bind(
        monkeypatch,
        FakeProject(semantic_models={"sm1": {"v3": {"entities": ["orders"]}}}),
    )
    out = call(object_type="semantic_model", object_id="sm1", version_id="v3")
    assert out["version_id"] == "v3"
    assert out["settings"] == {"entities": ["orders"]}


def test_saved_model_version_detail(monkeypatch):
    bind(monkeypatch, FakeProject(saved_models={"sm": {"v1": {"auc": 0.9}}}))
    out = call(object_type="saved_model", object_id="sm", version_id="v1")
    assert out["settings"]["snippet"] == {"auc": 0.9}
    assert out["settings"]["details_class"] == "FakeVersionDetails"


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


def test_version_required_type_without_version_errors(monkeypatch):
    bind(monkeypatch, FakeProject(saved_models={"sm": {"v1": {}}}))
    with pytest.raises(ValueError) as exc:
        call(object_type="saved_model", object_id="sm")
    assert "version_id" in str(exc.value)


def test_version_on_non_versioned_type_errors(monkeypatch):
    bind(monkeypatch, FakeProject(dashboards={"d": {}}))
    with pytest.raises(ValueError) as exc:
        call(object_type="dashboard", object_id="d", version_id="v1")
    assert "version_id" in str(exc.value)


# --------------------------------------------------------------------------- #
# Redaction + bounding
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


def test_oversized_settings_are_bounded(monkeypatch):
    big = {"blob": "x" * (object_settings.MAX_SETTINGS_BYTES + 5000)}
    bind(monkeypatch, FakeProject(dashboards={"d": big}))
    out = call(object_type="dashboard", object_id="d")
    assert out["truncated"] is True
    assert "settings" not in out
    assert out["total_bytes"] > object_settings.MAX_SETTINGS_BYTES
    assert out["returned_bytes"] <= object_settings.MAX_SETTINGS_BYTES
    assert isinstance(out["settings_json_truncated"], str)
