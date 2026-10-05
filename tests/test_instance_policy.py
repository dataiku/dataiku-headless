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

"""Instance policy contracts and enforcement through MCP dispatch."""

import asyncio
import json
from contextvars import ContextVar
from types import SimpleNamespace
from typing import get_args

import pytest
from fastmcp import Client

from dataiku_mcp import mcp, server
from dataiku_mcp.config import http, request, stdio
from dataiku_mcp.config.models import DSSInstance, InstanceType
from dataiku_mcp.instance_policy import require_instance_type
from dataiku_mcp.tools import projects
from tests.test_tool_surface import EXPECTED_TOOLS_BY_MODULE
from tests.utils.fakes import FakeContext

PROJECT_EDIT_TOOLS = EXPECTED_TOOLS_BY_MODULE["cobuild"] | {
    "create_project",
    "update_project_settings",
    "set_project_variables",
    "set_container_exec_config",
    "create_upload_dataset",
    "create_managed_folder",
    "upload_file_to_managed_folder",
    "write_project_library_file",
}
INSTANCE_TOOLS = EXPECTED_TOOLS_BY_MODULE["instances"]


def _instance(instance_type):
    return DSSInstance(
        name=instance_type,
        url="https://example.com",
        api_key="private-key",
        api_ticket=None,
        instance_type=instance_type,
        source="config",
        no_check_certificate=False,
    )


def _allowed(tool_name):
    if tool_name in INSTANCE_TOOLS:
        return set(get_args(InstanceType))
    if tool_name in PROJECT_EDIT_TOOLS:
        return {"design", "agent-management"}
    return {"design", "automation", "agent-management"}


def test_every_registered_tool_declares_its_exact_instance_policy():
    tools = asyncio.run(mcp.list_tools(run_middleware=False))
    assert len(tools) == sum(map(len, EXPECTED_TOOLS_BY_MODULE.values()))
    for tool in tools:
        allowed = tool.meta["allowed_instance_types"]
        assert isinstance(allowed, list)
        assert len(allowed) == len(set(allowed))
        assert set(allowed) == _allowed(tool.name), tool.name
        for instance_type in get_args(InstanceType):
            if instance_type in _allowed(tool.name):
                require_instance_type(tool.name, instance_type, tool.meta)
            else:
                with pytest.raises(ValueError, match=f"{tool.name}.*{instance_type}"):
                    require_instance_type(tool.name, instance_type, tool.meta)


@pytest.mark.parametrize(
    "metadata",
    [
        None,
        {},
        {"allowed_instance_types": None},
        {"allowed_instance_types": []},
        {"allowed_instance_types": "design"},
        {"allowed_instance_types": ["unknown"]},
        {"allowed_instance_types": [42]},
        {"allowed_instance_types": ["design", "design"]},
    ],
)
def test_invalid_policy_fails_closed_even_for_instance_controls(metadata):
    with pytest.raises(ValueError, match="invalid instance-type policy"):
        require_instance_type("switch_instance", None, metadata)


@pytest.mark.parametrize("instance_type", ["automation", "govern", "deployer"])
def test_mcp_dispatch_denies_every_disallowed_tool_before_validation_or_sdk(
    monkeypatch, instance_type
):
    monkeypatch.setattr(stdio, "_current_instance", _instance(instance_type))

    async def dispatch():
        tools = await mcp.list_tools(run_middleware=False)
        async with Client(mcp) as client:
            for tool in tools:
                if instance_type in _allowed(tool.name):
                    continue
                result = await client.call_tool(tool.name, {}, raise_on_error=False)
                assert result.is_error, tool.name
                message = result.content[0].text
                assert tool.name in message
                assert instance_type in message
                assert "Allowed types:" in message
                assert "switch_instance" in message
                assert "private-key" not in message

    asyncio.run(dispatch())


@pytest.mark.parametrize("instance_type", ["design", "automation", "agent-management"])
def test_mcp_allowed_read_and_recovery_after_denial(monkeypatch, instance_type):
    monkeypatch.setattr(stdio, "_current_instance", _instance(instance_type))
    calls = []

    def keys():
        calls.append(request.get_pinned_instance().instance_type)
        return ["PROJECT"]

    monkeypatch.setattr(
        projects, "get_dss_client", lambda: SimpleNamespace(list_project_keys=keys)
    )

    async def dispatch():
        async with Client(mcp) as client:
            stdio._current_instance = _instance("govern")
            rejected = await client.call_tool(
                "count_projects", {}, raise_on_error=False
            )
            assert rejected.is_error
            stdio._current_instance = _instance(instance_type)
            result = await client.call_tool("count_projects", {})
            assert json.loads(result.content[0].text) == {"project_count": 1}

    asyncio.run(dispatch())
    assert calls == [instance_type]


@pytest.mark.parametrize("instance_type", ["govern", "deployer"])
def test_mcp_unsupported_status_needs_no_client(monkeypatch, instance_type):
    from dataiku_mcp.tools import instances

    monkeypatch.setattr(stdio, "_current_instance", _instance(instance_type))
    monkeypatch.setattr(
        instances, "get_dss_client", lambda: pytest.fail("No SDK call is allowed")
    )

    async def dispatch():
        async with Client(mcp) as client:
            result = await client.call_tool("get_current_instance", {})
            data = json.loads(result.content[0].text)
            assert data["connection_status"] == "unsupported"
            assert "dataiku_version" not in data
            assert "private-key" not in result.content[0].text

    asyncio.run(dispatch())


@pytest.mark.parametrize(
    "tool_name",
    ["list_instances", "switch_instance", "configure_instance", "delete_instance"],
)
def test_local_controls_dispatch_without_a_selection(monkeypatch, tool_name):
    monkeypatch.setattr(stdio, "get_current_instance", lambda: None)
    monkeypatch.setattr(stdio, "get_instances", lambda: {})

    async def dispatch():
        context = SimpleNamespace(
            message=SimpleNamespace(name=tool_name), fastmcp_context=None
        )

        async def handler(_):
            assert request._pinned_instance.get() is None
            return "local-result"

        assert (
            await server.RequestContextMiddleware().on_call_tool(context, handler)
            == "local-result"
        )

    asyncio.run(dispatch())


@pytest.mark.parametrize(
    "outcome", ["denial", "exchange-error", "handler-error", "cancelled"]
)
def test_http_request_context_is_restored_on_all_failure_paths(monkeypatch, outcome):
    instances = {"design": _instance("design"), "govern": _instance("govern")}
    selected = "govern" if outcome == "denial" else "design"
    monkeypatch.setattr(
        http,
        "get_instances_and_selections",
        lambda: (instances, {"issuer": {"alice": selected}}),
    )
    monkeypatch.setattr(
        server,
        "get_access_token",
        lambda: SimpleNamespace(
            token="mcp-token", claims={"iss": "issuer", "sub": "alice"}
        ),
    )

    async def exchange(_):
        if outcome == "exchange-error":
            raise RuntimeError("exchange failed")
        return "delegated-token"

    monkeypatch.setattr(server, "exchange_http_token", exchange)

    async def dispatch():
        async def handler(_):
            assert request.get_http_dss_token() == "delegated-token"
            if outcome == "cancelled":
                raise asyncio.CancelledError()
            raise RuntimeError("handler failed")

        context = SimpleNamespace(
            message=SimpleNamespace(name="count_projects"), fastmcp_context=None
        )
        expected = (
            ValueError
            if outcome == "denial"
            else asyncio.CancelledError
            if outcome == "cancelled"
            else RuntimeError
        )
        with pytest.raises(expected):
            await server.RequestContextMiddleware().on_call_tool(context, handler)
        assert request._pinned_instance.get() is None
        assert not request.is_http_request()
        with pytest.raises(ValueError, match="No delegated DSS token"):
            request.get_http_dss_token()

    asyncio.run(dispatch())


def test_concurrent_http_users_keep_separate_policies_and_sdk_targets(monkeypatch):
    profiles = {kind: _instance(kind) for kind in ("design", "govern")}
    selections = {"issuer": {"alice": "design", "bob": "govern"}}
    monkeypatch.setattr(
        http, "get_instances_and_selections", lambda: (profiles, selections)
    )
    identity = ContextVar("test_identity")
    monkeypatch.setattr(
        server,
        "get_access_token",
        lambda: SimpleNamespace(
            token="mcp-token", claims={"iss": "issuer", "sub": identity.get()}
        ),
    )
    exchanges, sdk_calls = [], []

    async def exchange(_):
        exchanges.append(request.get_request_owner()[-1])
        selections["issuer"]["alice"] = "govern"
        await asyncio.sleep(0)
        return "delegated-token"

    monkeypatch.setattr(server, "exchange_http_token", exchange)

    def keys():
        sdk_calls.append(
            (
                request.get_request_owner()[-1],
                request.get_pinned_instance().instance_type,
            )
        )
        return ["PROJECT"]

    monkeypatch.setattr(
        projects, "get_dss_client", lambda: SimpleNamespace(list_project_keys=keys)
    )

    async def call(user):
        token = identity.set(user)
        try:
            context = SimpleNamespace(
                message=SimpleNamespace(name="count_projects"), fastmcp_context=None
            )

            async def handler(_):
                return await projects.count_projects(FakeContext())

            if user == "bob":
                with pytest.raises(ValueError, match="govern"):
                    await server.RequestContextMiddleware().on_call_tool(
                        context, handler
                    )
            else:
                result = await server.RequestContextMiddleware().on_call_tool(
                    context, handler
                )
                assert json.loads(result) == {"project_count": 1}
            assert not request.is_http_request()
            assert request._pinned_instance.get() is None
        finally:
            identity.reset(token)

    async def dispatch():
        await asyncio.gather(call("alice"), call("bob"))

    asyncio.run(dispatch())
    assert exchanges == ["alice"]
    assert sdk_calls == [("alice", "design")]


def test_mcp_dispatch_fails_closed_when_registered_policy_is_missing(monkeypatch):
    monkeypatch.setattr(stdio, "_current_instance", _instance("design"))

    async def dispatch():
        tool = await mcp.get_tool("count_projects")
        monkeypatch.setattr(tool, "meta", {})
        async with Client(mcp) as client:
            result = await client.call_tool("count_projects", {}, raise_on_error=False)
            assert result.is_error
            assert "invalid instance-type policy" in result.content[0].text

    asyncio.run(dispatch())


def test_mcp_dispatch_keeps_concurrent_http_identities_separate(monkeypatch):
    profiles = {kind: _instance(kind) for kind in ("design", "govern")}
    selections = {"issuer": {"alice": "design", "bob": "govern"}}
    monkeypatch.setattr(
        http, "get_instances_and_selections", lambda: (profiles, selections)
    )
    identity = ContextVar("mcp_test_identity")
    monkeypatch.setattr(
        server,
        "get_access_token",
        lambda: SimpleNamespace(
            token="mcp-token", claims={"iss": "issuer", "sub": identity.get()}
        ),
    )
    exchanges, sdk_calls = [], []

    async def exchange(_):
        exchanges.append(request.get_request_owner()[-1])
        selections["issuer"]["alice"] = "govern"
        await asyncio.sleep(0)
        return "delegated-token"

    monkeypatch.setattr(server, "exchange_http_token", exchange)

    def keys():
        sdk_calls.append(
            (
                request.get_request_owner()[-1],
                request.get_pinned_instance().instance_type,
            )
        )
        assert request.get_http_dss_token() == "delegated-token"
        return ["PROJECT"]

    monkeypatch.setattr(
        projects, "get_dss_client", lambda: SimpleNamespace(list_project_keys=keys)
    )

    async def call(user):
        token = identity.set(user)
        try:
            async with Client(mcp) as client:
                result = await client.call_tool(
                    "count_projects", {}, raise_on_error=False
                )
                if user == "bob":
                    assert result.is_error
                    assert "govern" in result.content[0].text
                else:
                    assert not result.is_error
                    assert json.loads(result.content[0].text) == {"project_count": 1}
            assert not request.is_http_request()
            assert request._pinned_instance.get() is None
        finally:
            identity.reset(token)

    async def dispatch():
        await asyncio.gather(call("alice"), call("bob"))

    asyncio.run(dispatch())
    assert exchanges == ["alice"]
    assert sdk_calls == [("alice", "design")]
