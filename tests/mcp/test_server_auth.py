"""Tests for MCP auth/env resolution helpers."""

from __future__ import annotations

from dku_cli.mcp import server


def test_resolve_dss_url_prefers_explicit_dku_url(monkeypatch):
    monkeypatch.setenv("DKU_URL", "https://explicit.example/")
    monkeypatch.setenv("DKU_BASE_PROTOCOL", "http")
    monkeypatch.setenv("DKU_SERVER_HOST", "internal")
    monkeypatch.setenv("DKU_BASE_PORT", "1234")

    assert server._resolve_dss_url() == "https://explicit.example"


def test_resolve_dss_url_from_code_studio_env(monkeypatch):
    monkeypatch.delenv("DKU_URL", raising=False)
    monkeypatch.setenv("DKU_BASE_PROTOCOL", "http")
    monkeypatch.setenv("DKU_SERVER_HOST", "dss-backend")
    monkeypatch.setenv("DKU_BASE_PORT", "11000")

    assert server._resolve_dss_url() == "http://dss-backend:11000"


def test_resolve_dss_url_uses_backend_host_fallback(monkeypatch):
    monkeypatch.delenv("DKU_URL", raising=False)
    monkeypatch.delenv("DKU_SERVER_HOST", raising=False)
    monkeypatch.setenv("DKU_BASE_PROTOCOL", "https")
    monkeypatch.setenv("DKU_BACKEND_HOST", "backend.example")
    monkeypatch.setenv("DKU_BASE_PORT", "443")

    assert server._resolve_dss_url() == "https://backend.example:443"


def test_http_auth_never_falls_back_to_pod_key(monkeypatch):
    monkeypatch.setenv("DKU_URL", "https://dss.example")
    monkeypatch.setenv("DKU_API_KEY", "POD-OWNER-SECRET")

    import sys

    fake = type(sys)("fastmcp.server.dependencies")

    def _raise():
        raise RuntimeError("no request context")

    fake.get_http_request = _raise
    monkeypatch.setitem(sys.modules, "fastmcp.server.dependencies", fake)

    auth = server._resolve_request_auth(is_http=True)
    assert auth["is_http"] is True
    assert auth["api_key"] == ""
    assert auth["api_key"] != "POD-OWNER-SECRET"
    assert auth["session_id"] == "anon"


def test_http_auth_no_bearer_returns_anon(monkeypatch):
    monkeypatch.setenv("DKU_URL", "https://dss.example")
    monkeypatch.setenv("DKU_API_KEY", "POD-OWNER-SECRET")

    import sys

    fake = type(sys)("fastmcp.server.dependencies")

    class _FakeNoAuth:
        headers = {}

    fake.get_http_request = lambda: _FakeNoAuth()
    monkeypatch.setitem(sys.modules, "fastmcp.server.dependencies", fake)

    auth = server._resolve_request_auth(is_http=True)
    assert auth["is_http"] is True
    assert auth["api_key"] == ""
    assert auth["api_key"] != "POD-OWNER-SECRET"
    assert auth["session_id"] == "anon"


def test_http_auth_with_bearer_returns_key(monkeypatch):
    monkeypatch.setenv("DKU_URL", "https://dss.example")

    import sys

    fake = type(sys)("fastmcp.server.dependencies")

    class _FakeBearer:
        headers = {"authorization": "Bearer dkuaps-test-key-123"}

    fake.get_http_request = lambda: _FakeBearer()
    monkeypatch.setitem(sys.modules, "fastmcp.server.dependencies", fake)

    auth = server._resolve_request_auth(is_http=True)
    assert auth["is_http"] is True
    assert auth["api_key"] == "dkuaps-test-key-123"
    assert auth["session_id"] == "bearer:dkuaps-test-key-123"


def test_stdio_auth_uses_pod_key(monkeypatch):
    monkeypatch.setenv("DKU_URL", "https://dss.example")
    monkeypatch.setenv("DKU_API_KEY", "POD-OWNER-SECRET")

    auth = server._resolve_request_auth(is_http=False)
    assert auth["is_http"] is False
    assert auth["api_key"] == "POD-OWNER-SECRET"
    assert auth["session_id"] == server._STDIO_SESSION
