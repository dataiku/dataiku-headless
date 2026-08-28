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
        "set_http_dss_token",
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
        "get_current_instance",
        "configure_instance",
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
