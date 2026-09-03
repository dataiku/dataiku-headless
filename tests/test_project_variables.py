# Copyright 2026 Dataiku
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Unit tests for the project variables tools (get/set) in ``tools/projects.py``."""

import asyncio
import json

import pytest

from dataiku_mcp.tools import projects

from tests.utils.fakes import FakeContext, FakeDSSClient, FakeProject


def _install_fake_project(
    monkeypatch, project_key: str, variables: dict
) -> FakeProject:
    project = FakeProject(variables)
    client = FakeDSSClient({project_key: project})
    monkeypatch.setattr(projects, "get_dss_client", lambda: client)
    return project


def test_get_project_variables_returns_variables(monkeypatch):
    project_key = "PROJ"
    variables = {"standard": {"DATE_REFERENCE": "2022-10-07"}, "local": {"env": "dev"}}
    _install_fake_project(monkeypatch, project_key, variables)
    result = json.loads(
        asyncio.run(projects.get_project_variables(project_key, FakeContext()))
    )
    assert result == variables


def test_set_project_variables_replaces_wholesale(monkeypatch):
    project_key = "PROJ"
    project = _install_fake_project(
        monkeypatch, project_key, {"standard": {"OLD": "x"}, "local": {}}
    )
    payload = {"standard": {"DATE_REFERENCE": "2022-10-07"}, "local": {}}
    result = json.loads(
        asyncio.run(projects.set_project_variables(project_key, payload, FakeContext()))
    )
    assert project.set_calls == [payload]
    assert project.variables == payload
    assert result == {"project_key": project_key}


def test_set_project_variables_accepts_json_string(monkeypatch):
    project_key = "PROJ"
    project = _install_fake_project(
        monkeypatch, project_key, {"standard": {}, "local": {}}
    )
    payload = '{"standard": {"DATE_REFERENCE": "2022-10-07"}, "local": {}}'
    asyncio.run(projects.set_project_variables(project_key, payload, FakeContext()))
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
