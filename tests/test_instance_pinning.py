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

"""Regression tests for per-request Dataiku instance pinning."""

import asyncio

from fastmcp import Client

from dataiku_mcp import config, mcp
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
        config._current_instance = instance_b
        observed_instances.append(config.get_current_instance().name)
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
    assert config.get_current_instance() == instance_b
