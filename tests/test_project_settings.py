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
                    "mode": "EXPLICIT_ENV",
                    "envName": "PYTHON_ENV",
                    "preventOverride": True,
                },
                "r": {"mode": "INHERIT", "preventOverride": False},
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
            "python": {"mode": "USE_BUILTIN_MODE", "envName": None},
            "r": {"envName": None},
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
            "python": {"mode": "USE_BUILTIN_MODE", "preventOverride": True},
            "r": {"mode": "INHERIT", "preventOverride": False},
        },
        "container": {"containerMode": "NONE"},
    }
    assert raw["permissions"] == [{"group": "data-team"}]
    assert project.settings.save_calls == 1


def test_update_project_settings_rejects_invalid_patch(monkeypatch):
    _install_fake_project(monkeypatch, {"settings": {}})

    with pytest.raises(ValueError, match="must not be empty"):
        asyncio.run(projects.update_project_settings("PROJ", {}, FakeContext()))
    with pytest.raises(ValueError, match="must be a JSON object"):
        asyncio.run(projects.update_project_settings("PROJ", "[1,2]", FakeContext()))
