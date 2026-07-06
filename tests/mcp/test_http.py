"""Tests for the reverse-proxy-aware HTTP assembly (``dku_cli.mcp.http``).

The pure pieces (prefix resolution, the ASGI strip middleware, the landing
page) need no fastmcp. The end-to-end app test is skipped unless fastmcp is
installed.
"""

from __future__ import annotations

import asyncio

import pytest

from dku_cli.mcp import http as mcp_http


def test_resolve_proxy_prefix_precedence(monkeypatch):
    for key in list(__import__("os").environ):
        if key.startswith("DKU_CODE_STUDIO_BROWSER_PATH_"):
            monkeypatch.delenv(key, raising=False)

    # nothing set → empty
    assert mcp_http.resolve_proxy_prefix("", 5050) == ""

    # port-specific wins when no explicit env
    monkeypatch.setenv("DKU_CODE_STUDIO_BROWSER_PATH_5050", "/web-apps/P/cs/5050")
    assert mcp_http.resolve_proxy_prefix("", 5050) == "/web-apps/P/cs/5050"

    # a wildcard match is used when the port-specific one is absent
    monkeypatch.delenv("DKU_CODE_STUDIO_BROWSER_PATH_5050")
    monkeypatch.setenv("DKU_CODE_STUDIO_BROWSER_PATH_9000", "/web-apps/P/cs/9000")
    assert mcp_http.resolve_proxy_prefix("", 5050) == "/web-apps/P/cs/9000"

    # an explicit env var name overrides everything
    monkeypatch.setenv("MY_PREFIX", "/custom/prefix")
    assert mcp_http.resolve_proxy_prefix("MY_PREFIX", 5050) == "/custom/prefix"


def test_resolve_proxy_prefix_wildcard_fallback_is_deterministic(monkeypatch):
    # Multi-exposed-port Code Studio: the port-specific var is missing but two
    # other ports' prefixes are present. The fallback must be order-independent
    # (sorted by key), not "whichever os.environ enumerates first".
    for key in list(__import__("os").environ):
        if key.startswith("DKU_CODE_STUDIO_BROWSER_PATH_"):
            monkeypatch.delenv(key, raising=False)

    monkeypatch.setenv("DKU_CODE_STUDIO_BROWSER_PATH_9000", "/web-apps/P/cs/9000")
    monkeypatch.setenv("DKU_CODE_STUDIO_BROWSER_PATH_8000", "/web-apps/P/cs/8000")
    # 8000 sorts before 9000 regardless of insertion order, so the result is
    # stable. (port 5050 has no specific var → falls back to the sorted wildcard.)
    first = mcp_http.resolve_proxy_prefix("", 5050)

    # Re-insert in the opposite order; the deterministic result must not flip.
    monkeypatch.delenv("DKU_CODE_STUDIO_BROWSER_PATH_8000")
    monkeypatch.delenv("DKU_CODE_STUDIO_BROWSER_PATH_9000")
    monkeypatch.setenv("DKU_CODE_STUDIO_BROWSER_PATH_8000", "/web-apps/P/cs/8000")
    monkeypatch.setenv("DKU_CODE_STUDIO_BROWSER_PATH_9000", "/web-apps/P/cs/9000")
    second = mcp_http.resolve_proxy_prefix("", 5050)

    assert first == second == "/web-apps/P/cs/8000"


def _run_middleware(prefix: str, path: str, raw_path: bytes) -> dict:
    captured: dict = {}

    async def downstream(scope, receive, send):
        captured["path"] = scope["path"]
        captured["raw_path"] = scope.get("raw_path")

    mw = mcp_http.ProxyPrefixMiddleware(downstream, prefix=prefix)
    scope = {"type": "http", "path": path, "raw_path": raw_path}
    asyncio.run(mw(scope, None, None))
    return captured


def test_proxy_prefix_middleware_does_not_latch_empty_prefix(monkeypatch):
    # The deferred (prefix_env/port) path must NOT permanently cache an empty
    # resolution: DSS may inject DKU_CODE_STUDIO_BROWSER_PATH_<port> AFTER the
    # process starts, so a first request that resolves "" must keep re-resolving.
    for key in list(__import__("os").environ):
        if key.startswith("DKU_CODE_STUDIO_BROWSER_PATH_"):
            monkeypatch.delenv(key, raising=False)

    captured: dict = {}

    async def downstream(scope, receive, send):
        captured["path"] = scope["path"]

    mw = mcp_http.ProxyPrefixMiddleware(downstream, prefix_env="", port=5050)

    # 1st request: prefix unresolved → pass-through, nothing cached.
    asyncio.run(
        mw(
            {"type": "http", "path": "/web-apps/P/cs/5050/mcp", "raw_path": b""},
            None,
            None,
        )
    )
    assert captured["path"] == "/web-apps/P/cs/5050/mcp"  # not stripped yet

    # DSS injects the prefix after start; the next request must pick it up.
    monkeypatch.setenv("DKU_CODE_STUDIO_BROWSER_PATH_5050", "/web-apps/P/cs/5050")
    asyncio.run(
        mw(
            {"type": "http", "path": "/web-apps/P/cs/5050/mcp", "raw_path": b""},
            None,
            None,
        )
    )
    assert captured["path"] == "/mcp"  # now stripped — no stale empty latch


def test_proxy_prefix_middleware_strips_prefix():
    out = _run_middleware(
        "/web-apps/P/cs/5050", "/web-apps/P/cs/5050/mcp", b"/web-apps/P/cs/5050/mcp"
    )
    assert out["path"] == "/mcp"
    assert out["raw_path"] == b"/mcp"


def test_proxy_prefix_middleware_exact_prefix_becomes_root():
    out = _run_middleware(
        "/web-apps/P/cs/5050", "/web-apps/P/cs/5050", b"/web-apps/P/cs/5050"
    )
    assert out["path"] == "/"


def test_proxy_prefix_middleware_leaves_non_matching_path():
    out = _run_middleware("/web-apps/P/cs/5050", "/healthz", b"/healthz")
    assert out["path"] == "/healthz"


def test_proxy_prefix_middleware_noop_without_prefix():
    out = _run_middleware("", "/web-apps/P/cs/5050/mcp", b"/web-apps/P/cs/5050/mcp")
    assert out["path"] == "/web-apps/P/cs/5050/mcp"


def test_landing_html_contains_endpoint_and_bearer():
    page = mcp_http.landing_html(
        mcp_url="https://dss.example.com/web-apps/P/cs/5050/mcp",
    )
    assert "https://dss.example.com/web-apps/P/cs/5050/mcp" in page
    assert "Authorization: Bearer" in page
    assert "dku_exec" in page
    assert "skill_lookup" not in page


def test_landing_html_has_client_quickconnect_snippets():
    page = mcp_http.landing_html(
        mcp_url="https://dss.example.com/web-apps/P/cs/5050/mcp",
    )
    assert "Claude Code" in page and "Codex" in page
    assert "claude mcp add --transport http" in page
    assert "codex mcp add dku --url" in page
    assert "--bearer-token-env-var DKU_DSS_KEY" in page
    assert 'class="copy"' in page and "data-copy" in page
    assert "YOUR_DSS_API_KEY" in page
    assert page.count("https://dss.example.com/web-apps/P/cs/5050/mcp") >= 2


def test_landing_html_note_is_backend_aware():
    bwrap = mcp_http.landing_html(
        mcp_url="https://dss.example.com/mcp",
        backend="bubblewrap",
    )
    assert "sandboxed (bubblewrap)" in bwrap
    assert "NOT sandboxed" not in bwrap

    insecure = mcp_http.landing_html(
        mcp_url="https://dss.example.com/mcp",
        backend="subprocess",
    )
    # Under the subprocess fallback the page must degrade the isolation claim.
    assert "NOT sandboxed" in insecure
    assert "subprocess" in insecure
    assert "sandboxed (bubblewrap) and isolated per caller" not in insecure


def test_external_base_prefers_forwarded_headers():
    class _Req:
        def __init__(self, headers):
            self.headers = headers

            class _U:
                scheme = "http"
                netloc = "127.0.0.1:5050"

            self.url = _U()

    req = _Req({"x-forwarded-proto": "https", "x-forwarded-host": "dss.example.com"})
    assert (
        mcp_http.external_base(req, "/web-apps/P/cs/5050")
        == "https://dss.example.com/web-apps/P/cs/5050"
    )


# --- end-to-end through the real FastMCP Starlette app -----------------------

pytest.importorskip("fastmcp")


def _app(tmp_path, monkeypatch, *, behind_proxy):
    from dku_cli.mcp.server import build_server

    server = build_server(state_root=str(tmp_path), sandbox="subprocess")
    return mcp_http.build_http_app(
        server, behind_proxy=behind_proxy, port=5050, landing=True
    )


def test_http_app_serves_health_and_landing(tmp_path):
    from starlette.testclient import TestClient

    with TestClient(_app(tmp_path, None, behind_proxy=False)) as client:
        health = client.get("/healthz")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"

        landing = client.get("/")
        assert landing.status_code == 200
        assert "Authorization: Bearer" in landing.text
        assert "/mcp" in landing.text


def test_http_app_strips_proxy_prefix_end_to_end(tmp_path, monkeypatch):
    from starlette.testclient import TestClient

    monkeypatch.setenv("DKU_CODE_STUDIO_BROWSER_PATH_5050", "/web-apps/P/cs/5050")
    with TestClient(_app(tmp_path, monkeypatch, behind_proxy=True)) as client:
        # reached through the proxy prefix → still routes to /healthz
        proxied = client.get("/web-apps/P/cs/5050/healthz")
        assert proxied.status_code == 200
        assert proxied.json()["status"] == "ok"
