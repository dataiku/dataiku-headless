"""End-to-end integration: drive the real FastMCP server through an MCP client.

Unlike the unit tests, these exercise the actual FastMCP tool registration,
schemas, and dispatch — the same path a real agent uses. Skipped unless the
optional ``mcp`` extra (fastmcp) is installed.
"""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("fastmcp")

from fastmcp import Client

from dku_cli.mcp.server import build_server


def _server(tmp_path):
    return build_server(
        state_root=str(tmp_path),
        sandbox="subprocess",
    )


def _text(result) -> str:
    """Extract the string payload from a fastmcp CallToolResult, version-tolerant."""
    data = getattr(result, "data", None)
    if isinstance(data, str):
        return data
    content = getattr(result, "content", None)
    if content:
        text = getattr(content[0], "text", None)
        if text is not None:
            return text
    return str(result)


def _run(coro):
    return asyncio.run(coro)


def test_server_exposes_only_dku_exec(tmp_path):
    server = _server(tmp_path)

    async def go():
        async with Client(server) as client:
            tools = await client.list_tools()
            return sorted(t.name for t in tools)

    assert _run(go()) == ["dku_exec"]


def test_dku_exec_runs_bash_and_python(tmp_path):
    server = _server(tmp_path)

    async def go():
        async with Client(server) as client:
            return _text(
                await client.call_tool(
                    "dku_exec",
                    {"commands": "echo hi && python3 -c 'print(40 + 2)'"},
                )
            )

    payload = _run(go())
    assert payload.startswith("exit 0\n")
    assert "hi" in payload
    assert "42" in payload


def test_dku_exec_strips_dangerous_flag(tmp_path):
    server = _server(tmp_path)

    async def go():
        async with Client(server) as client:
            return _text(
                await client.call_tool(
                    "dku_exec", {"commands": "echo keep --dangerous end"}
                )
            )

    payload = _run(go())
    assert "--dangerous" not in payload
    assert "keep" in payload and "end" in payload


def test_dku_exec_isolated_per_session_workdir(tmp_path):
    """A file written by one exec is visible to the next (same stdio session)."""
    server = _server(tmp_path)

    async def go():
        async with Client(server) as client:
            await client.call_tool("dku_exec", {"commands": "echo marker > probe.txt"})
            return _text(
                await client.call_tool("dku_exec", {"commands": "cat probe.txt"})
            )

    payload = _run(go())
    assert payload.startswith("exit 0\n")
    assert "marker" in payload


def test_build_server_uses_passed_backend_without_reprobing(tmp_path, monkeypatch):
    """idx 10: a pre-resolved backend is reused so select_backend isn't called."""
    from dku_cli.mcp import sandbox
    from dku_cli.mcp import server as server_mod

    calls = {"n": 0}
    real = sandbox.select_backend

    def _counting(*args, **kwargs):
        calls["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(server_mod, "select_backend", _counting)

    backend = sandbox.SubprocessBackend()
    build_server(
        state_root=str(tmp_path),
        backend=backend,
    )
    assert calls["n"] == 0  # the passed backend short-circuits the probe


def test_http_dku_exec_rejects_missing_bearer(tmp_path):
    """idx 23/31: HTTP mode with no bearer rejects (auth required), never the pod
    key, and never serves the shared 'anon' session."""
    server = build_server(
        state_root=str(tmp_path),
        sandbox="subprocess",
        mode="hosted",
        is_http=True,
    )

    async def go():
        async with Client(server) as client:
            return _text(
                await client.call_tool("dku_exec", {"commands": "echo should-not-run"})
            )

    payload = _run(go())
    assert payload.startswith("exit 1\n")
    assert "--- stderr ---" in payload
    assert "Authentication required" in payload
    assert "should-not-run" not in payload
    # No 'anon' session workdir was minted for the rejected caller.
    sessions_dir = tmp_path / "sessions"
    assert not sessions_dir.exists() or not any(sessions_dir.iterdir())
