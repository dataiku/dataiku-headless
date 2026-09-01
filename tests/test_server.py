"""Runtime tests for MCP server startup."""

from pathlib import Path

import dataiku_mcp
import dataiku_mcp.server as server
from dataiku_mcp.config import http, stdio
from dataiku_mcp.config.models import HTTPServerConfig


def test_run_stdio_server_uses_stdio(monkeypatch):
    calls = []
    paths = []
    monkeypatch.setattr(stdio, "set_settings_path", lambda path: paths.append(path))
    monkeypatch.setattr(
        stdio,
        "initialize_current_instance",
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


def test_run_http_server_uses_streamable_http(monkeypatch):
    calls = []
    paths = []
    stdio_initializations = []
    monkeypatch.setattr(
        stdio,
        "initialize_current_instance",
        lambda: stdio_initializations.append(True),
    )
    monkeypatch.setattr(
        http,
        "get_server_settings",
        lambda: HTTPServerConfig(host="127.0.0.1", port=8000, path="/mcp"),
    )
    auth = object()
    monkeypatch.setattr(server, "_http_auth", lambda: auth)
    monkeypatch.setattr(http, "set_settings_path", lambda path: paths.append(path))
    monkeypatch.setattr(dataiku_mcp.mcp, "run", lambda **kwargs: calls.append(kwargs))

    dataiku_mcp.run_http_server(Path("/tmp/http.json"))

    assert calls == [
        {
            "transport": "streamable-http",
            "host": "127.0.0.1",
            "port": 8000,
            "path": "/mcp",
        }
    ]
    assert dataiku_mcp.mcp.auth is auth
    assert paths == [Path("/tmp/http.json")]
    assert stdio_initializations == []
