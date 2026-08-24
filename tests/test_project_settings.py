"""Unit tests for project settings inspection and updates."""

import asyncio
import json

import pytest

from dataiku_mcp.tools import projects

from tests.utils.fakes import FakeContext, FakeDSSClient


class _FakeProjectSettings:
    def __init__(self, raw: dict):
        self.raw = raw
        self.save_calls = 0

    def get_raw(self) -> dict:
        return self.raw

    def save(self) -> None:
        self.save_calls += 1


class _FakeProject:
    def __init__(self, raw: dict):
        self.settings = _FakeProjectSettings(raw)

    def get_settings(self) -> _FakeProjectSettings:
        return self.settings


def _install_fake_project(monkeypatch, raw: dict) -> _FakeProject:
    project = _FakeProject(raw)
    client = FakeDSSClient({"PROJ": project})
    monkeypatch.setattr(projects, "get_dss_client", lambda: client)
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


def test_update_project_settings_merges_nested_patch(monkeypatch):
    raw = {
        "settings": {
            "flowDisplaySettings": {
                "showFlowZoneDescriptions": False,
                "zonesGraphConnectZones": True,
            },
            "flowBuildSettings": {"mergeSqlPipelines": False},
            "codeEnvs": {
                "python": {"mode": "INHERIT", "preventOverride": False},
                "r": {"mode": "INHERIT", "preventOverride": False},
            },
        },
        "permissions": [{"group": "data-team"}],
    }
    project = _install_fake_project(monkeypatch, raw)
    patch = {
        "flowDisplaySettings": {"showFlowZoneDescriptions": True},
        "flowBuildSettings": {"mergeSqlPipelines": True},
        "codeEnvs": {
            "python": {
                "mode": "EXPLICIT_ENV",
                "envName": "PYTHON_ENV",
                "preventOverride": True,
            }
        },
    }

    result = json.loads(
        asyncio.run(projects.update_project_settings("PROJ", patch, FakeContext()))
    )

    assert result == {
        "flowDisplaySettings": {
            "showFlowZoneDescriptions": True,
            "zonesGraphConnectZones": True,
        },
        "flowBuildSettings": {"mergeSqlPipelines": True},
        "codeEnvs": {
            "python": {
                "mode": "EXPLICIT_ENV",
                "envName": "PYTHON_ENV",
                "preventOverride": True,
            },
            "r": {"mode": "INHERIT", "preventOverride": False},
        },
    }
    assert raw["permissions"] == [{"group": "data-team"}]
    assert project.settings.save_calls == 1


def test_update_project_settings_accepts_json_string(monkeypatch):
    project = _install_fake_project(
        monkeypatch,
        {
            "settings": {
                "container": {"containerMode": "INHERIT"},
                "containerForVisualRecipesWorkloads": {"containerMode": "INHERIT"},
            }
        },
    )

    asyncio.run(
        projects.update_project_settings(
            "PROJ",
            '{"container": {"containerMode": "EXPLICIT_CONTAINER", '
            '"containerConf": "container-config"}, '
            '"containerForVisualRecipesWorkloads": {'
            '"containerMode": "EXPLICIT_CONTAINER", '
            '"containerConf": "visual-container-config"}}',
            FakeContext(),
        )
    )

    assert project.settings.raw["settings"]["container"] == {
        "containerMode": "EXPLICIT_CONTAINER",
        "containerConf": "container-config",
    }
    assert project.settings.raw["settings"]["containerForVisualRecipesWorkloads"] == {
        "containerMode": "EXPLICIT_CONTAINER",
        "containerConf": "visual-container-config",
    }


def test_update_project_settings_null_removes_explicit_selection_fields(monkeypatch):
    project = _install_fake_project(
        monkeypatch,
        {
            "settings": {
                "codeEnvs": {
                    "python": {
                        "mode": "EXPLICIT_ENV",
                        "envName": "PYTHON_ENV",
                        "preventOverride": True,
                    }
                },
                "container": {
                    "containerMode": "EXPLICIT_CONTAINER",
                    "containerConf": "container-config",
                },
            }
        },
    )

    patch = {
        "codeEnvs": {
            "python": {
                "mode": "USE_BUILTIN_MODE",
                "envName": None,
                "preventOverride": False,
            }
        },
        "container": {"containerMode": "NONE", "containerConf": None},
    }
    asyncio.run(projects.update_project_settings("PROJ", patch, FakeContext()))

    assert project.settings.raw["settings"] == {
        "codeEnvs": {
            "python": {
                "mode": "USE_BUILTIN_MODE",
                "preventOverride": False,
            }
        },
        "container": {"containerMode": "NONE"},
    }


def test_update_project_settings_does_not_add_nested_null_fields(monkeypatch):
    project = _install_fake_project(monkeypatch, {"settings": {}})

    patch = {"codeEnvs": {"python": {"mode": "INHERIT", "envName": None}}}
    asyncio.run(projects.update_project_settings("PROJ", patch, FakeContext()))

    assert project.settings.raw["settings"] == {
        "codeEnvs": {"python": {"mode": "INHERIT"}}
    }


def test_update_project_settings_rejects_empty_patch(monkeypatch):
    _install_fake_project(monkeypatch, {"settings": {}})

    with pytest.raises(ValueError, match="must not be empty"):
        asyncio.run(projects.update_project_settings("PROJ", {}, FakeContext()))


def test_update_project_settings_rejects_non_object_payload():
    with pytest.raises(ValueError, match="'settings_patch' must be a JSON object"):
        asyncio.run(projects.update_project_settings("PROJ", "[1,2]", FakeContext()))
