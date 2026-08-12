"""Regression tests for per-request Dataiku instance pinning."""

import asyncio

from dataiku_mcp import config
from dataiku_mcp.tools import projects


class _SwitchingContext:
    def __init__(self, next_instance):
        self.next_instance = next_instance

    async def info(self, message: str) -> None:
        config._current_instance = self.next_instance


class _FakeProject:
    def set_variables(self, variables: dict) -> None:
        self.variables = variables


class _FakeClient:
    def __init__(self):
        self.project = _FakeProject()

    def get_project(self, project_key: str) -> _FakeProject:
        return self.project


def test_tool_keeps_its_initial_instance_after_a_concurrent_switch(monkeypatch):
    instance_a = config.DSSInstance(
        "instance-a", "https://a.example", "key-a", False, "config"
    )
    instance_b = config.DSSInstance(
        "instance-b", "https://b.example", "key-b", False, "config"
    )
    observed_instances = []
    fake_client = _FakeClient()

    monkeypatch.setattr(config, "_current_instance", instance_a)

    def get_client():
        observed_instances.append(config.get_current_instance().name)
        return fake_client

    monkeypatch.setattr(projects, "get_dss_client", get_client)

    asyncio.run(
        projects.set_project_variables(
            "PROJECT",
            {"standard": {}},
            _SwitchingContext(instance_b),
        )
    )

    assert observed_instances == ["instance-a"]
    assert config.get_current_instance() == instance_b
