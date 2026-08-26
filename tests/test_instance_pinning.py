"""Regression tests for per-request Dataiku instance pinning."""

import asyncio

from fastmcp import Client

from dataiku_mcp import mcp
from dataiku_mcp.config import request, stdio
from dataiku_mcp.config.models import DSSInstance
from dataiku_mcp.tools import projects


class _FakeProject:
    def set_variables(self, variables: dict) -> None:
        self.variables = variables


class _FakeClient:
    def __init__(self):
        self.project = _FakeProject()

    def get_project(self, project_key: str) -> _FakeProject:
        return self.project


def test_tool_keeps_its_initial_instance_after_a_concurrent_switch(monkeypatch):
    instance_a = DSSInstance(
        "instance-a", "https://a.example", "key-a", False, "config"
    )
    instance_b = DSSInstance(
        "instance-b", "https://b.example", "key-b", False, "config"
    )
    observed_instances = []
    fake_client = _FakeClient()

    monkeypatch.setattr(stdio, "_current_instance", instance_a)

    def get_client():
        stdio._current_instance = instance_b
        observed_instances.append(request.get_current_instance().name)
        return fake_client

    monkeypatch.setattr(projects, "get_dss_client", get_client)

    async def call_tool():
        async with Client(mcp) as mcp_client:
            return await mcp_client.call_tool(
                "set_project_variables",
                {"project_key": "PROJECT", "variables": {"standard": {}}},
            )

    result = asyncio.run(call_tool())

    assert not result.is_error
    assert observed_instances == ["instance-a"]
    assert request.get_current_instance() == instance_b
