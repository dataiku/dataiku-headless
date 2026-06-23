"""Reverse-proxy-aware HTTP assembly for the dku MCP server.

When the server runs behind a reverse proxy (the DSS Code Studio exposed-port
proxy), the proxy forwards the *full* external path — Code Studio declares
``proxiedUrlSuffix: "/$request_uri"`` — e.g. ``/web-apps/PROJ/cs-id/5050/mcp``.
FastMCP only knows its own mount path (``/mcp``), so we strip the proxy prefix
before routing. We also serve a small connect-info landing page at ``/`` so a
human who opens the exposed-port URL in a browser sees exactly how to wire an
external agent harness to the endpoint.

Everything here is deployment-generic (any reverse proxy) and unit-testable
without a live DSS; callers only need to launch the server with
``--behind-proxy``.
"""

from __future__ import annotations

import html
import os

# The conventional env var DSS injects per exposed port: the browser path prefix
# the reverse proxy serves this port under.
_BROWSER_PATH_PREFIX = "DKU_CODE_STUDIO_BROWSER_PATH_"


def resolve_proxy_prefix(prefix_env: str = "", port: int = 0) -> str:
    """Resolve the reverse-proxy path prefix this server is served under.

    Precedence (mirrors the agentos/CLI-Vector blocks):
      1. an explicit env var name (``prefix_env``) if it holds a value;
      2. the port-specific ``DKU_CODE_STUDIO_BROWSER_PATH_<port>``;
      3. any ``DKU_CODE_STUDIO_BROWSER_PATH_*`` that holds a value;
      4. empty string (not behind a proxy / prefix unknown).
    """
    if prefix_env:
        val = os.environ.get(prefix_env, "").strip()
        if val:
            return val
    if port:
        val = os.environ.get(f"{_BROWSER_PATH_PREFIX}{port}", "").strip()
        if val:
            return val
    # Deterministic fallback: env dict-iteration order is not guaranteed across
    # processes, so on a Code Studio exposing several ports we must not return
    # whichever DKU_CODE_STUDIO_BROWSER_PATH_* happens to enumerate first. Sort
    # the keys so the result is stable regardless of insertion order.
    for key in sorted(os.environ):
        if key.startswith(_BROWSER_PATH_PREFIX) and os.environ[key].strip():
            return os.environ[key].strip()
    return ""


class ProxyPrefixMiddleware:
    """ASGI middleware that strips a reverse-proxy path prefix before routing.

    The prefix is resolved per request (cached after first hit) because DSS may
    inject ``DKU_CODE_STUDIO_BROWSER_PATH_<port>`` into the environment after the
    process starts. A request to ``<prefix>/mcp`` is rewritten to ``/mcp`` so the
    FastMCP routes (mounted at their bare paths) match.
    """

    def __init__(self, app, *, prefix: str = "", prefix_env: str = "", port: int = 0):
        self.app = app
        self._fixed = (prefix or "").rstrip("/")
        self._prefix_env = prefix_env or ""
        self._port = int(port or 0)
        self._cached: str | None = self._fixed or None

    def _resolve(self) -> str:
        if self._cached is not None:
            return self._cached
        resolved = resolve_proxy_prefix(self._prefix_env, self._port).rstrip("/")
        # Only latch a NON-EMPTY resolution. DSS may inject
        # DKU_CODE_STUDIO_BROWSER_PATH_<port> after the process starts, so an
        # early request that resolves "" must keep re-resolving on later
        # requests instead of caching the unresolved sentinel forever.
        if resolved:
            self._cached = resolved
        return resolved

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        prefix = self._resolve()
        if prefix:
            path = scope.get("path", "")
            if path == prefix or path.startswith(prefix + "/"):
                scope = dict(scope)
                scope["path"] = path[len(prefix) :] or "/"
                raw = scope.get("raw_path")
                if isinstance(raw, (bytes, bytearray)):
                    praw = prefix.encode("latin-1")
                    if raw == praw or raw.startswith(praw + b"/"):
                        scope["raw_path"] = raw[len(praw) :] or b"/"
        await self.app(scope, receive, send)


def external_base(request, prefix: str, public_url: str = "") -> str:
    """Best-effort external base URL the client used to reach this server."""
    if public_url:
        return public_url.rstrip("/")
    headers = request.headers
    scheme = headers.get("x-forwarded-proto") or request.url.scheme or "https"
    # X-Forwarded-Proto can be a comma list ("https,http"); take the first.
    scheme = scheme.split(",")[0].strip()
    host = (
        (
            headers.get("x-forwarded-host")
            or headers.get("host")
            or request.url.netloc
            or "your-dss-host"
        )
        .split(",")[0]
        .strip()
    )
    return f"{scheme}://{host}{prefix}".rstrip("/")


# The bearer is intentionally left as a placeholder the user fills in (model A:
# each caller authenticates with their own DSS personal API key).
_PLACEHOLDER = "<YOUR_DSS_API_KEY>"

# Plain template (not an f-string) so the embedded CSS/JS braces stay literal;
# values are injected via @@TOKEN@@ replacement.
_LANDING_TPL = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>dku MCP server</title>
<style>
  :root { color-scheme: light dark; }
  body { font: 15px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
         max-width: 760px; margin: 3rem auto; padding: 0 1.25rem; color: #1c1c1f; }
  @media (prefers-color-scheme: dark) { body { color: #e6e6ea; background: #161618; } }
  h1 { font-size: 1.5rem; margin: 0 0 .25rem; }
  .diamond { color: #2c6fff; }
  .sub { color: #8a8a92; margin: 0 0 1.5rem; }
  .badge { display:inline-block; font-size:.72rem; font-weight:600; letter-spacing:.02em;
           padding:.15rem .5rem; border-radius:999px; background:#e7f0ff; color:#2c6fff; vertical-align:middle; }
  @media (prefers-color-scheme: dark) { .badge { background:#16243f; } }
  code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: .85em; }
  .endpoint { font-size: 1rem; padding:.6rem .8rem; background:#f4f5f7; border:1px solid #e2e3e8;
              border-radius:8px; word-break:break-all; display:block; }
  @media (prefers-color-scheme: dark) { .endpoint { background:#1f1f23; border-color:#2c2c31; } }
  pre { background:#f4f5f7; border:1px solid #e2e3e8; border-radius:8px; padding:.9rem 1rem; overflow:auto; margin:.5rem 0 0; }
  @media (prefers-color-scheme: dark) { pre { background:#1f1f23; border-color:#2c2c31; } }
  h2 { font-size: .95rem; margin: 1.8rem 0 .5rem; text-transform: uppercase; letter-spacing:.04em; color:#8a8a92; }
  ul { padding-left: 1.1rem; }
  .tool { font-weight:600; }
  .note { font-size:.85rem; color:#8a8a92; border-left:3px solid #2c6fff; padding-left:.75rem; margin-top:1.5rem; }
  .tabs { display:flex; gap:.25rem; border-bottom:1px solid #e2e3e8; margin-top:.5rem; }
  .tab { border:none; background:none; padding:.5rem .8rem; font:inherit; font-size:.9rem; color:#8a8a92;
         cursor:pointer; border-bottom:2px solid transparent; margin-bottom:-1px; }
  .tab.active { color:#2c6fff; border-bottom-color:#2c6fff; font-weight:600; }
  .panel { display:none; }
  .panel.active { display:block; }
  .snip { position:relative; }
  .copy { position:absolute; top:.55rem; right:.55rem; font:inherit; font-size:.72rem; padding:.2rem .6rem;
          border:1px solid #d3d4da; border-radius:6px; background:#fff; color:#1c1c1f; cursor:pointer; }
  .copy:hover { background:#eef0f3; }
  .cap { font-size:.78rem; color:#8a8a92; margin:.6rem 0 0; }
  .hint { font-size:.85rem; color:#8a8a92; margin-top:.75rem; }
  @media (prefers-color-scheme: dark) {
    .tabs { border-bottom-color:#2c2c31; }
    .copy { background:#26262b; color:#e6e6ea; border-color:#3a3a40; }
    .copy:hover { background:#303036; }
  }
</style>
</head>
<body>
  <h1><span class="diamond">&#9670;</span> dku MCP server <span class="badge">running</span></h1>
  <p class="sub">A code-mode MCP for Dataiku DSS, driven by your own CLI.</p>

  <h2>Endpoint</h2>
  <code class="endpoint">@@URL@@</code>
  <p>Transport: <strong>Streamable HTTP</strong>. Connect any external agent harness below.</p>

  <h2>Connect your agent</h2>
  <div class="tabs">
    <button class="tab active" data-target="p-claude">Claude Code</button>
    <button class="tab" data-target="p-codex">Codex</button>
  </div>
  <div class="panel active" id="p-claude">
    <div class="snip"><button class="copy" data-copy="c-claude">Copy</button>
    <pre><code id="c-claude">@@CLAUDE@@</code></pre></div>
  </div>
  <div class="panel" id="p-codex">
    <div class="snip"><button class="copy" data-copy="c-codex">Copy</button>
    <pre><code id="c-codex">@@CODEX@@</code></pre></div>
  </div>
  <p class="hint">Replace <code>&lt;YOUR_DSS_API_KEY&gt;</code> with your DSS personal API key
     (DSS &rarr; <em>Profile &amp; settings &rarr; API keys</em>). Each user uses their own &mdash;
     every <code>dku</code> command runs as that user, with their permissions and audit trail.</p>

  <h2>Tools</h2>
  <ul>
    <li><span class="tool">dku_exec</span> &mdash; run <code>dku</code> / <code>jq</code> /
        <code>python3</code> in a sandbox authed as you; only stdout/stderr/exit return.</li>
  </ul>

  <h2>Smoke test</h2>
  <div class="snip"><button class="copy" data-copy="c-curl">Copy</button>
  <pre><code id="c-curl">@@CURL@@</code></pre></div>

  <p class="note">@@SANDBOX_NOTE@@
     Requests without a valid bearer are rejected. This page serves no data &mdash;
     it is connection info only.</p>

<script>
(function(){
  document.querySelectorAll('.tab').forEach(function(b){
    b.addEventListener('click', function(){
      document.querySelectorAll('.tab').forEach(function(x){ x.classList.remove('active'); });
      document.querySelectorAll('.panel').forEach(function(x){ x.classList.remove('active'); });
      b.classList.add('active');
      document.getElementById(b.getAttribute('data-target')).classList.add('active');
    });
  });
  function fallback(txt){
    var ta=document.createElement('textarea'); ta.value=txt; ta.style.position='fixed';
    ta.style.opacity='0'; document.body.appendChild(ta); ta.focus(); ta.select();
    try { document.execCommand('copy'); } catch(e) {} document.body.removeChild(ta);
  }
  document.querySelectorAll('.copy').forEach(function(btn){
    btn.addEventListener('click', function(){
      var txt=document.getElementById(btn.getAttribute('data-copy')).textContent;
      function done(){ var o=btn.textContent; btn.textContent='Copied ✓';
        setTimeout(function(){ btn.textContent=o; }, 1500); }
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(txt).then(done, function(){ fallback(txt); done(); });
      } else { fallback(txt); done(); }
    });
  });
})();
</script>
</body>
</html>"""


def landing_html(*, mcp_url: str, base: str, backend: str = "bubblewrap") -> str:
    """A connect-info page for the exposed port, with one-click copy snippets.

    Shown to a human who opens the Code Studio's exposed-port URL in a browser.
    Provides ready-to-paste "connect" commands for Claude Code and Codex; the
    bearer stays a ``<YOUR_DSS_API_KEY>`` placeholder the user fills in (model A:
    each caller uses their own DSS personal API key).

    ``backend`` is the selected sandbox backend name; the isolation note degrades
    honestly when it is not ``bubblewrap`` (e.g. under ``--allow-insecure-sandbox``
    with the subprocess fallback, which gives NO kernel isolation).
    """
    if backend == "bubblewrap":
        sandbox_note = "The executor is sandboxed (bubblewrap) and isolated per caller."
    else:
        sandbox_note = (
            f"WARNING: the executor is NOT sandboxed (backend: {backend}) &mdash; "
            "it has no kernel isolation between callers. This is only safe for "
            "trusted/local testing."
        )
    claude_cmd = (
        f'claude mcp add --transport http dku-dss "{mcp_url}" \\\n'
        f'  --header "Authorization: Bearer {_PLACEHOLDER}"'
    )
    codex_cmd = (
        f'export DKU_DSS_KEY="{_PLACEHOLDER}"\n'
        f'codex mcp add dku --url "{mcp_url}" --bearer-token-env-var DKU_DSS_KEY'
    )
    curl = html.escape(
        f"curl -sS {mcp_url} \\\n"
        f'  -H "Authorization: Bearer {_PLACEHOLDER}" \\\n'
        '  -H "Accept: application/json, text/event-stream" \\\n'
        '  -H "Content-Type: application/json" \\\n'
        '  -d \'{"jsonrpc":"2.0","id":1,"method":"tools/list"}\''
    )
    return (
        _LANDING_TPL.replace("@@URL@@", html.escape(mcp_url))
        .replace("@@CLAUDE@@", html.escape(claude_cmd))
        .replace("@@CODEX@@", html.escape(codex_cmd))
        .replace("@@CURL@@", curl)
        .replace("@@SANDBOX_NOTE@@", sandbox_note)
    )


def build_http_app(
    mcp,
    *,
    mcp_path: str = "/mcp",
    behind_proxy: bool = False,
    proxy_prefix_env: str = "",
    port: int = 0,
    landing: bool = True,
    public_url: str = "",
    backend: str = "bubblewrap",
):
    """Register landing/health routes and return the FastMCP Starlette app.

    The returned app exposes:
      * ``<mcp_path>`` — the Streamable HTTP MCP endpoint (FastMCP),
      * ``/`` — the connect-info landing page (when ``landing``),
      * ``/healthz`` — a liveness probe.

    When ``behind_proxy`` is set, a :class:`ProxyPrefixMiddleware` strips the DSS
    reverse-proxy path prefix before routing. ``backend`` is the selected sandbox
    backend name so the landing page's isolation note reflects reality.
    """
    from starlette.middleware import Middleware
    from starlette.responses import HTMLResponse, JSONResponse

    if landing:

        @mcp.custom_route("/", methods=["GET"])
        async def _landing(request):  # noqa: ANN001
            prefix = (
                resolve_proxy_prefix(proxy_prefix_env, port) if behind_proxy else ""
            )
            base = external_base(request, prefix, public_url)
            return HTMLResponse(
                landing_html(mcp_url=f"{base}{mcp_path}", base=base, backend=backend)
            )

    @mcp.custom_route("/healthz", methods=["GET"])
    async def _healthz(request):  # noqa: ANN001
        return JSONResponse({"status": "ok", "server": "dku-mcp"})

    middleware = None
    if behind_proxy:
        middleware = [
            Middleware(ProxyPrefixMiddleware, prefix_env=proxy_prefix_env, port=port)
        ]

    return mcp.http_app(
        path=mcp_path, transport="streamable-http", middleware=middleware
    )


def run_http_app(app, *, host: str = "127.0.0.1", port: int = 5050) -> None:
    """Serve the composed ASGI app with uvicorn (FastMCP's own HTTP runtime).

    Defaults to loopback; callers that need to expose the authed shell executor
    on all interfaces must pass ``host="0.0.0.0"`` explicitly.
    """
    import uvicorn

    uvicorn.run(app, host=host, port=port, log_level="info")
