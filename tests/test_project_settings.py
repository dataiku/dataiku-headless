# Copyright 2026 Dataiku SAS
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

"""Unit tests for project settings inspection and updates."""

import asyncio
import json

import pytest

from dataiku_mcp.tools import projects

from tests.utils.fakes import FakeContext, FakeDSSClient


class _FakeSettings:
    def __init__(self, raw: dict):
        self.raw = raw
        self.save_calls = 0

    def get_raw(self) -> dict:
        return self.raw

    def save(self) -> None:
        self.save_calls += 1


class _FakeProject:
    def __init__(self, raw: dict):
        self.settings = _FakeSettings(raw)

    def get_settings(self) -> _FakeSettings:
        return self.settings


def _install_fake_project(monkeypatch, raw: dict) -> _FakeProject:
    project = _FakeProject(raw)
    monkeypatch.setattr(
        projects, "get_dss_client", lambda: FakeDSSClient({"PROJ": project})
    )
    return project


def test_get_project_settings_returns_editable_settings(monkeypatch):
    raw = {
        "settings": {"flowDisplaySettings": {"showFlowZoneDescriptions": False}},
        "permissions": [{"group": "data-team"}],
    }
    _install_fake_project(monkeypatch, raw)

    result = json.loads(
        asyncio.run(projects.get_project_settings("PROJ", FakeContext()))
    )

    assert result == raw["settings"]


def test_update_project_settings_applies_merge_patch(monkeypatch):
    raw = {
        "settings": {
            "flowDisplaySettings": {
                "showFlowZoneDescriptions": False,
                "zonesGraphConnectZones": True,
            },
            "codeEnvs": {
                "python": {
                    "mode": "USE_BUILTIN_MODE",
                    "useBuiltinEnv": True,
                    "preventOverride": True,
                },
                "r": {
                    "mode": "EXPLICIT_ENV",
                    "envName": "R_ENV",
                    "useBuiltinEnv": True,
                    "preventOverride": False,
                },
            },
            "container": {
                "containerMode": "EXPLICIT_CONTAINER",
                "containerConf": "container-config",
            },
        },
        "permissions": [{"group": "data-team"}],
    }
    project = _install_fake_project(monkeypatch, raw)
    patch = {
        "flowDisplaySettings": {"showFlowZoneDescriptions": True},
        "codeEnvs": {
            "python": {"mode": "EXPLICIT_ENV", "envName": "PYTHON_ENV"},
            "r": {"mode": "USE_BUILTIN_MODE"},
        },
        "container": {"containerMode": "NONE", "containerConf": None},
    }

    result = json.loads(
        asyncio.run(
            projects.update_project_settings("PROJ", json.dumps(patch), FakeContext())
        )
    )

    assert result == {
        "flowDisplaySettings": {
            "showFlowZoneDescriptions": True,
            "zonesGraphConnectZones": True,
        },
        "codeEnvs": {
            "python": {
                "mode": "EXPLICIT_ENV",
                "envName": "PYTHON_ENV",
                "useBuiltinEnv": False,
                "preventOverride": True,
            },
            "r": {
                "mode": "USE_BUILTIN_MODE",
                "useBuiltinEnv": True,
                "preventOverride": False,
            },
        },
        "container": {"containerMode": "NONE"},
    }
    assert raw["permissions"] == [{"group": "data-team"}]
    assert project.settings.save_calls == 1


def test_update_project_settings_rejects_invalid_patch(monkeypatch):
    project = _install_fake_project(monkeypatch, {"settings": {}})

    with pytest.raises(ValueError, match="must not be empty"):
        asyncio.run(projects.update_project_settings("PROJ", {}, FakeContext()))
    with pytest.raises(ValueError, match="must be a JSON object"):
        asyncio.run(projects.update_project_settings("PROJ", "[1,2]", FakeContext()))
    with pytest.raises(ValueError, match="codeEnvs.python.unknown"):
        asyncio.run(
            projects.update_project_settings(
                "PROJ", {"codeEnvs": {"python": {"unknown": True}}}, FakeContext()
            )
        )
    with pytest.raises(ValueError, match="must be a boolean"):
        asyncio.run(
            projects.update_project_settings(
                "PROJ",
                {"flowBuildSettings": {"mergeSqlPipelines": "yes"}},
                FakeContext(),
            )
        )
    with pytest.raises(ValueError, match="Allowed values"):
        asyncio.run(
            projects.update_project_settings(
                "PROJ", {"container": {"containerMode": "BANANA"}}, FakeContext()
            )
        )
    with pytest.raises(ValueError, match="codeEnvs.python.envName"):
        asyncio.run(
            projects.update_project_settings(
                "PROJ",
                {"codeEnvs": {"python": {"mode": "EXPLICIT_ENV"}}},
                FakeContext(),
            )
        )
    assert project.settings.save_calls == 0
