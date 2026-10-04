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

"""Runtime tests for MCP server startup."""

import asyncio
from pathlib import Path

import pytest

import dataiku_mcp
from dataiku_mcp.config import request, stdio
from dataiku_mcp.config.models import DSSInstance
from dataiku_mcp.executors import run_blocking
from dataiku_mcp.server import RequestContextMiddleware


def test_run_stdio_server_uses_stdio(monkeypatch):
    calls = []
    paths = []
    monkeypatch.setattr(stdio, "set_settings_path", lambda path: paths.append(path))
    monkeypatch.setattr(
        stdio,
        "initialize_config",
        lambda: calls.append("initialize_stdio"),
    )
    monkeypatch.setattr(
        dataiku_mcp.mcp,
        "run",
        lambda **kwargs: calls.append(("run", kwargs)),
    )

    dataiku_mcp.run_stdio_server(Path("/tmp/stdio-config.json"))

    assert paths == [Path("/tmp/stdio-config.json")]
    assert calls == ["initialize_stdio", ("run", {"transport": "stdio"})]


@pytest.mark.parametrize("fail", [False, True])
def test_middleware_pins_instance_across_switch_and_resets_after_call(
    monkeypatch, fail
):
    first = DSSInstance(
        name="first",
        url="https://first.example",
        api_key="key",
        no_check_certificate=False,
        source="config",
    )
    second = DSSInstance(
        name="second",
        url="https://second.example",
        api_key="key",
        no_check_certificate=False,
        source="config",
    )
    monkeypatch.setattr(stdio, "_current_instance", first)
    monkeypatch.setattr(
        stdio, "get_instances", lambda: {"first": first, "second": second}
    )
    middleware = RequestContextMiddleware()

    async def scenario():
        async def call_next(_context):
            assert request.get_pinned_instance() is first
            request.set_current_instance("second")
            # Context is carried into the SDK executor after an instance switch.
            assert await run_blocking(request.get_pinned_instance) is first
            if fail:
                raise RuntimeError("tool failed")
            return "result"

        if fail:
            with pytest.raises(RuntimeError, match="tool failed"):
                await middleware.on_call_tool(None, call_next)
        else:
            assert await middleware.on_call_tool(None, call_next) == "result"

        # A new request sees the switch; the previous call's pin was reset.
        async def next_call(_context):
            assert request.get_pinned_instance() is second

        await middleware.on_call_tool(None, next_call)
        with pytest.raises(ValueError, match="No active Dataiku instance"):
            request.get_pinned_instance()

    asyncio.run(scenario())
