"""Unit tests for Code Studio template and lifecycle tools."""

import asyncio
import json

import pytest

from dataiku_mcp.tools import code_studios as tools
from tests.utils.fakes import FakeContext


def _result(coro):
    return json.loads(asyncio.run(coro))


class FakeSettings:
    def __init__(self, raw):
        self.raw = raw

    def get_raw(self):
        return self.raw


class FakeFuture:
    def __init__(self, job_id):
        self.job_id = job_id


class FakeStudio:
    def __init__(self, raw, status=None):
        self.settings = FakeSettings(raw)
        self.status = FakeSettings(status or {"state": "STOPPED"})
        self.started = 0
        self.stopped = 0

    def get_settings(self):
        return self.settings

    def get_status(self):
        return self.status

    def restart(self):
        self.started += 1
        return FakeFuture("start-1")

    def stop(self):
        self.stopped += 1
        return FakeFuture("stop-1")

    @property
    def id(self):
        return self.settings.raw["id"]

    @property
    def name(self):
        return self.settings.raw["name"]

    @property
    def template_id(self):
        return self.settings.raw["templateId"]

    @property
    def owner(self):
        return self.settings.raw.get("owner", "")


class FakeProject:
    def __init__(self, studios):
        self.studios = studios
        self.created = None

    def list_code_studios(self):
        return list(self.studios.values())

    def get_code_studio(self, studio_id):
        return self.studios[studio_id]

    def create_code_studio(self, name, template_id):
        self.created = (name, template_id)
        studio = FakeStudio({"id": "new", "name": name, "templateId": template_id})
        self.studios["new"] = studio
        return studio


class FakeClient:
    def __init__(self):
        self.template = {
            "id": "phoenix",
            "name": "Phoenix",
            "description": "Elixir runtime",
            "nested": {"port": 4000, "clientSecret": "do-not-return"},
        }
        self.calls = []
        self.project = FakeProject(
            {
                "studio": FakeStudio(
                    {"id": "studio", "name": "event-ops", "templateId": "phoenix"},
                    {"state": "RUNNING", "token": "do-not-return"},
                )
            }
        )

    def _perform_json(self, method, path, body=None):
        self.calls.append((method, path, body))
        if method == "GET" and path == "/admin/code-studios/":
            return [self.template]
        if method == "GET" and path == "/admin/code-studios/phoenix":
            return self.template
        if method == "PUT" and path == "/admin/code-studios/phoenix":
            self.template = body
            return body
        if method == "POST" and path.endswith("/build"):
            return {"jobId": "build-1"}
        raise AssertionError((method, path, body))

    def get_project(self, project_key):
        assert project_key == "ELIXIR"
        return self.project


def _install(monkeypatch, client):
    monkeypatch.setattr(tools, "get_dss_client", lambda: client)

    async def _admin():
        return None

    monkeypatch.setattr(tools, "require_admin", _admin)


def _row(table, index=0):
    return dict(zip(table["columns"], table["rows"][index]))


def test_list_and_get_template_redacts_sensitive_values(monkeypatch):
    client = FakeClient()
    _install(monkeypatch, client)

    listed = _result(tools.list_code_studio_templates(FakeContext()))
    assert _row(listed["code_studio_templates"]) == {
        "id": "phoenix",
        "name": "Phoenix",
        "description": "Elixir runtime",
        "built": False,
    }

    settings = _result(
        tools.get_code_studio_template_settings("phoenix", FakeContext())
    )
    assert settings["nested"]["clientSecret"] == tools._REDACTED


def test_update_template_deep_merges_and_build_returns_future(monkeypatch):
    client = FakeClient()
    _install(monkeypatch, client)

    updated = _result(
        tools.update_code_studio_template(
            "phoenix", {"nested": {"port": 5000}}, FakeContext()
        )
    )
    assert updated == {"template_id": "phoenix", "updated": True}
    assert client.template["nested"] == {"port": 5000, "clientSecret": "do-not-return"}

    built = _result(
        tools.build_code_studio_template(
            "phoenix", FakeContext(), disable_docker_cache=True
        )
    )
    assert built == {
        "template_id": "phoenix",
        "status": "build_started",
        "future_id": "build-1",
    }
    assert client.calls[-1] == (
        "POST",
        "/admin/code-studios/phoenix/build",
        {"disableDockerCache": True},
    )


def test_update_template_requires_non_empty_patch(monkeypatch):
    _install(monkeypatch, FakeClient())
    with pytest.raises(ValueError, match="settings_patch"):
        _result(tools.update_code_studio_template("phoenix", {}, FakeContext()))


def test_code_studio_lifecycle_tools(monkeypatch):
    client = FakeClient()
    _install(monkeypatch, client)

    listed = _result(tools.list_code_studios("ELIXIR", FakeContext()))
    assert _row(listed["code_studios"])["name"] == "event-ops"

    detail = _result(tools.get_code_studio("ELIXIR", "studio", FakeContext()))
    assert detail["status"]["token"] == tools._REDACTED

    created = _result(
        tools.create_code_studio("ELIXIR", "new-studio", "phoenix", FakeContext())
    )
    assert created["id"] == "new"
    assert client.project.created == ("new-studio", "phoenix")

    started = _result(tools.start_code_studio("ELIXIR", "studio", FakeContext()))
    stopped = _result(tools.stop_code_studio("ELIXIR", "studio", FakeContext()))
    assert started["future_id"] == "start-1"
    assert stopped["future_id"] == "stop-1"
