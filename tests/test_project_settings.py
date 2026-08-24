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
                "python": {"mode": "INHERIT"},
                "r": {"mode": "INHERIT"},
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
                "useBuiltinEnv": False,
                "envName": "PYTHON_ENV",
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
                "useBuiltinEnv": False,
                "envName": "PYTHON_ENV",
            },
            "r": {"mode": "INHERIT"},
        },
    }
    assert raw["permissions"] == [{"group": "data-team"}]
    assert project.settings.save_calls == 1


def test_update_project_settings_accepts_json_string(monkeypatch):
    project = _install_fake_project(
        monkeypatch,
        {"settings": {"container": {"containerMode": "INHERIT"}}},
    )

    asyncio.run(
        projects.update_project_settings(
            "PROJ",
            '{"container": {"containerMode": "EXPLICIT_CONTAINER", '
            '"containerConf": "container-config"}}',
            FakeContext(),
        )
    )

    assert project.settings.raw["settings"]["container"] == {
        "containerMode": "EXPLICIT_CONTAINER",
        "containerConf": "container-config",
    }


def test_update_project_settings_rejects_empty_patch(monkeypatch):
    _install_fake_project(monkeypatch, {"settings": {}})

    with pytest.raises(ValueError, match="must not be empty"):
        asyncio.run(projects.update_project_settings("PROJ", {}, FakeContext()))


def test_update_project_settings_rejects_non_object_payload():
    with pytest.raises(ValueError, match="'settings_patch' must be a JSON object"):
        asyncio.run(projects.update_project_settings("PROJ", "[1,2]", FakeContext()))
