"""Runtime tests for MCP server startup."""

import dataiku_mcp


def test_run_server_uses_stdio(monkeypatch):
    calls = []
    monkeypatch.setattr(dataiku_mcp.mcp, "run", lambda **kwargs: calls.append(kwargs))

    dataiku_mcp.run_server()

    assert calls == [{"transport": "stdio"}]


def test_run_http_server_uses_streamable_http(monkeypatch):
    calls = []
    monkeypatch.setattr(
        dataiku_mcp.config,
        "get_http_server_settings",
        lambda: {"host": "127.0.0.1", "port": 8000, "path": "/mcp"},
    )
    monkeypatch.setattr(dataiku_mcp, "_http_auth", lambda: object())
    monkeypatch.setattr(dataiku_mcp.mcp, "run", lambda **kwargs: calls.append(kwargs))

    dataiku_mcp.run_http_server()

    assert calls == [
        {
            "transport": "streamable-http",
            "host": "127.0.0.1",
            "port": 8000,
            "path": "/mcp",
        }
    ]
