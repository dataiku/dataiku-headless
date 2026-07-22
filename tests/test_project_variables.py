"""Unit tests for the project variables tools (get/set) in ``tools/projects.py``.

These intentionally avoid any live Dataiku DSS connection: the DSS client is
replaced with an in-memory fake, so CI can run them on a bare runner (same
constraint as ``test_smoke.py``).
"""

import asyncio
import json

import pytest

from dataiku_mcp.tools import projects


class _FakeContext:
    async def info(self, message: str) -> None:
        pass


class _FakeProject:
    def __init__(self, variables: dict):
        self.variables = variables
        self.set_calls: list[dict] = []

    def get_variables(self) -> dict:
        return json.loads(json.dumps(self.variables))

    def set_variables(self, obj: dict) -> None:
        self.set_calls.append(obj)
        self.variables = json.loads(json.dumps(obj))


class _FakeClient:
    def __init__(self, project: _FakeProject):
        self.project = project

    def get_project(self, project_key: str) -> _FakeProject:
        return self.project


def _install_fake_project(monkeypatch, variables: dict) -> _FakeProject:
    project = _FakeProject(variables)
    monkeypatch.setattr(projects, "get_dss_client", lambda: _FakeClient(project))
    return project


def test_get_project_variables_returns_variables(monkeypatch):
    variables = {"standard": {"DATE_REFERENCE": "2022-10-07"}, "local": {"env": "dev"}}
    _install_fake_project(monkeypatch, variables)
    result = json.loads(
        asyncio.run(projects.get_project_variables("PROJ", _FakeContext()))
    )
    assert result == variables


def test_set_project_variables_replaces_wholesale(monkeypatch):
    project = _install_fake_project(
        monkeypatch, {"standard": {"OLD": "x"}, "local": {}}
    )
    payload = {"standard": {"DATE_REFERENCE": "2022-10-07"}, "local": {}}
    result = json.loads(
        asyncio.run(projects.set_project_variables("PROJ", payload, _FakeContext()))
    )
    assert project.set_calls == [payload]
    assert project.variables == payload
    assert result == {"project_key": "PROJ"}


def test_set_project_variables_accepts_json_string(monkeypatch):
    project = _install_fake_project(monkeypatch, {"standard": {}, "local": {}})
    payload = '{"standard": {"DATE_REFERENCE": "2022-10-07"}, "local": {}}'
    asyncio.run(projects.set_project_variables("PROJ", payload, _FakeContext()))
    assert project.set_calls == [
        {"standard": {"DATE_REFERENCE": "2022-10-07"}, "local": {}}
    ]


def test_set_project_variables_rejects_empty_project_key():
    with pytest.raises(ValueError, match="project_key"):
        asyncio.run(
            projects.set_project_variables("  ", {"standard": {}}, _FakeContext())
        )


def test_set_project_variables_rejects_non_object_payload():
    with pytest.raises(ValueError, match="'variables' must be a JSON object"):
        asyncio.run(projects.set_project_variables("PROJ", "[1,2]", _FakeContext()))
