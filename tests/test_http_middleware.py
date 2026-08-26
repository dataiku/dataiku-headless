"""The HTTP middleware exchanges a DSS token only for DSS-backed tools."""

import asyncio
from types import SimpleNamespace

import dataiku_mcp
from dataiku_mcp.config import request


def _call_middleware(monkeypatch, tool_name: str):
    events = []
    access_token = SimpleNamespace(
        token="mcp-token",
        claims={"iss": "https://idp.example", "sub": "alice"},
    )
    middleware = dataiku_mcp.InstancePinningMiddleware()

    monkeypatch.setattr(dataiku_mcp, "get_access_token", lambda: access_token)
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
        dataiku_mcp,
        "exchange_http_token",
        lambda token: events.append(("exchange", token)) or "dss-token",
    )

    async def run_blocking(function, *args):
        events.append(("run_blocking",))
        return function(*args)

    monkeypatch.setattr(dataiku_mcp, "run_blocking", run_blocking)
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

    context = SimpleNamespace(message=SimpleNamespace(name=tool_name))
    assert asyncio.run(middleware.on_call_tool(context, call_next)) == "result"
    return events


def test_http_local_only_tools_are_an_explicit_contract():
    assert dataiku_mcp.HTTP_LOCAL_ONLY_TOOL_NAMES == {
        "list_instances",
        "switch_instance",
        "delete_instance",
        "get_current_instance",
        "configure_instance",
    }


def test_http_local_only_tool_skips_dss_token_exchange(monkeypatch):
    events = _call_middleware(monkeypatch, "switch_instance")

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
