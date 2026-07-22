"""Unit tests for the project variables tools (get/set) in ``tools/projects.py``."""

import asyncio
import json

import pytest

from dataiku_mcp.tools import projects

from util import FakeContext, FakeDSSClient, FakeProject


def _install_fake_project(monkeypatch, variables: dict) -> FakeProject:
    project = FakeProject(variables)
    client = FakeDSSClient({"PROJ": project})
    monkeypatch.setattr(projects, "get_dss_client", lambda: client)
    return project


def test_get_project_variables_returns_variables(monkeypatch):
    variables = {"standard": {"DATE_REFERENCE": "2022-10-07"}, "local": {"env": "dev"}}
    _install_fake_project(monkeypatch, variables)
    result = json.loads(
        asyncio.run(projects.get_project_variables("PROJ", FakeContext()))
    )
    assert result == variables


def test_set_project_variables_replaces_wholesale(monkeypatch):
    project = _install_fake_project(
        monkeypatch, {"standard": {"OLD": "x"}, "local": {}}
    )
    payload = {"standard": {"DATE_REFERENCE": "2022-10-07"}, "local": {}}
    result = json.loads(
        asyncio.run(projects.set_project_variables("PROJ", payload, FakeContext()))
    )
    assert project.set_calls == [payload]
    assert project.variables == payload
    assert result == {"project_key": "PROJ"}


def test_set_project_variables_accepts_json_string(monkeypatch):
    project = _install_fake_project(monkeypatch, {"standard": {}, "local": {}})
    payload = '{"standard": {"DATE_REFERENCE": "2022-10-07"}, "local": {}}'
    asyncio.run(projects.set_project_variables("PROJ", payload, FakeContext()))
    assert project.set_calls == [
        {"standard": {"DATE_REFERENCE": "2022-10-07"}, "local": {}}
    ]


def test_set_project_variables_rejects_empty_project_key():
    with pytest.raises(ValueError, match="project_key"):
        asyncio.run(
            projects.set_project_variables("  ", {"standard": {}}, FakeContext())
        )


def test_set_project_variables_rejects_non_object_payload():
    with pytest.raises(ValueError, match="'variables' must be a JSON object"):
        asyncio.run(projects.set_project_variables("PROJ", "[1,2]", FakeContext()))
