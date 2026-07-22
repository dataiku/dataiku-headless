"""Runtime tests for MCP server startup."""

import dataiku_mcp


def test_run_server_uses_stdio(monkeypatch):
    calls = []
    monkeypatch.setattr(dataiku_mcp.mcp, "run", lambda **kwargs: calls.append(kwargs))

    dataiku_mcp.run_server()

    assert calls == [{"transport": "stdio"}]
