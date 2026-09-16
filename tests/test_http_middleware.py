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

"""The HTTP middleware exchanges a DSS token only for DSS-backed tools."""

import asyncio
from types import SimpleNamespace

import pytest

import dataiku_mcp.server as server
from dataiku_mcp.config import request


def _call_middleware(
    monkeypatch,
    tool_name: str,
    *,
    tool_tags: set[str] | None = None,
    tool_resolves: bool = True,
    include_fastmcp_context: bool = True,
):
    events = []
    access_token = SimpleNamespace(
        token="mcp-token",
        claims={"iss": "https://idp.example", "sub": "alice"},
    )
    middleware = server.RequestContextMiddleware()

    monkeypatch.setattr(server, "get_access_token", lambda: access_token)
    monkeypatch.setattr(
        request,
        "bind_http_identity",
        lambda issuer, subject: (
            events.append(("identity", issuer, subject)) or "identity"
        ),
    )
    monkeypatch.setattr(
        request,
        "pin_current_instance",
        lambda: events.append(("pin",)) or "instance",
    )
    monkeypatch.setattr(
        request,
        "reset_pinned_instance",
        lambda token: events.append(("reset_instance", token)),
    )
    monkeypatch.setattr(
        request,
        "reset_http_identity",
        lambda token: events.append(("reset_identity", token)),
    )
    monkeypatch.setattr(
        server,
        "exchange_http_token",
        lambda token: _exchange(events, token),
    )
    monkeypatch.setattr(
        request,
        "bind_http_dss_token",
        lambda token: events.append(("set_dss", token)) or "dss",
    )
    monkeypatch.setattr(
        request,
        "reset_http_dss_token",
        lambda token: events.append(("reset_dss", token)),
    )

    async def call_next(_context):
        events.append(("tool",))
        return "result"

    class FakeFastMCP:
        async def get_tool(self, name):
            assert name == tool_name
            if not tool_resolves:
                return None
            return SimpleNamespace(tags=tool_tags or set())

    fastmcp_context = None
    if include_fastmcp_context:
        fastmcp_context = SimpleNamespace(fastmcp=FakeFastMCP())
    context = SimpleNamespace(
        message=SimpleNamespace(name=tool_name),
        fastmcp_context=fastmcp_context,
    )
    assert asyncio.run(middleware.on_call_tool(context, call_next)) == "result"
    return events


async def _exchange(events, token):
    events.append(("exchange", token))
    return "dss-token"


@pytest.mark.parametrize(
    "claims",
    [
        {"sub": "alice"},
        {"iss": "https://idp.example"},
        {"iss": None, "sub": "alice"},
        {"iss": 42, "sub": "alice"},
        {"iss": [], "sub": "alice"},
        {"iss": "https://idp.example", "sub": None},
        {"iss": "https://idp.example", "sub": 42},
        {"iss": "https://idp.example", "sub": []},
    ],
)
def test_http_invalid_identity_claims_fail_before_request_setup(monkeypatch, claims):
    events = []
    middleware = server.RequestContextMiddleware()
    access_token = SimpleNamespace(token="mcp-token", claims=claims)

    monkeypatch.setattr(server, "get_access_token", lambda: access_token)
    monkeypatch.setattr(
        request, "pin_current_instance", lambda: events.append(("pin",))
    )
    monkeypatch.setattr(
        server, "exchange_http_token", lambda _: events.append(("exchange",))
    )

    async def call_next(_context):
        events.append(("tool",))

    context = SimpleNamespace(message=SimpleNamespace(name="list_projects"))
    with pytest.raises(ValueError, match="non-empty string iss and sub claims"):
        asyncio.run(middleware.on_call_tool(context, call_next))

    assert events == []


def test_dss_independent_tools_are_tagged():
    async def get_tagged_tool_names():
        tools = await server.mcp.list_tools(run_middleware=False)
        return {
            tool.name for tool in tools if server.DSS_INDEPENDENT_TOOL_TAG in tool.tags
        }

    assert asyncio.run(get_tagged_tool_names()) == {
        "list_instances",
        "switch_instance",
        "delete_instance",
        "configure_instance",
        "get_cobuild_turn_status",
        "list_cobuild_conversations",
    }


def test_http_local_only_tool_skips_dss_token_exchange(monkeypatch):
    events = _call_middleware(
        monkeypatch,
        "switch_instance",
        tool_tags={server.DSS_INDEPENDENT_TOOL_TAG},
    )

    assert ("exchange", "mcp-token") not in events
    assert ("set_dss", "dss-token") not in events
    assert events[-2:] == [
        ("reset_instance", "instance"),
        ("reset_identity", "identity"),
    ]


def test_http_dss_tool_exchanges_and_resets_its_dss_token(monkeypatch):
    events = _call_middleware(monkeypatch, "list_projects")

    assert ("exchange", "mcp-token") in events
    assert ("set_dss", "dss-token") in events
    assert events[-3:] == [
        ("reset_dss", "dss"),
        ("reset_instance", "instance"),
        ("reset_identity", "identity"),
    ]


def test_http_current_instance_exchanges_a_dss_token(monkeypatch):
    events = _call_middleware(monkeypatch, "get_current_instance")

    assert ("exchange", "mcp-token") in events
    assert ("set_dss", "dss-token") in events


@pytest.mark.parametrize(
    ("tool_resolves", "include_fastmcp_context"),
    [(False, True), (True, False)],
)
def test_http_unknown_tool_policy_requires_dss_token_exchange(
    monkeypatch, tool_resolves, include_fastmcp_context
):
    events = _call_middleware(
        monkeypatch,
        "unknown_tool",
        tool_resolves=tool_resolves,
        include_fastmcp_context=include_fastmcp_context,
    )

    assert ("exchange", "mcp-token") in events


def test_http_identity_is_reset_when_instance_pinning_fails(monkeypatch):
    events = []
    access_token = SimpleNamespace(
        token="mcp-token",
        claims={"iss": "https://idp.example", "sub": "alice"},
    )
    middleware = server.RequestContextMiddleware()

    monkeypatch.setattr(server, "get_access_token", lambda: access_token)
    monkeypatch.setattr(request, "bind_http_identity", lambda *_: "identity")

    def fail_pinning():
        raise ValueError("invalid settings")

    monkeypatch.setattr(
        request,
        "pin_current_instance",
        fail_pinning,
    )
    monkeypatch.setattr(
        request,
        "reset_http_identity",
        lambda token: events.append(("reset_identity", token)),
    )

    async def call_next(_context):
        pytest.fail("The tool must not run after pinning fails.")

    context = SimpleNamespace(message=SimpleNamespace(name="list_projects"))
    with pytest.raises(ValueError, match="invalid settings"):
        asyncio.run(middleware.on_call_tool(context, call_next))

    assert events == [("reset_identity", "identity")]
