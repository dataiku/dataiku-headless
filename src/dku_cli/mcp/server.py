"""FastMCP server exposing the ``dku_exec`` tool.

``fastmcp`` is imported lazily inside ``build_server`` so importing this module
(and therefore the standalone ``dku-mcp`` command) never requires the optional
``mcp`` extra. Only ``dku-mcp serve`` needs it.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from dku_cli.mcp import executor
from dku_cli.mcp.audit import AuditLog
from dku_cli.mcp.sandbox import SandboxBackend, select_backend
from dku_cli.mcp.sessions import SessionStore

# Over stdio the server is single-user (the pod owner), so one fixed session.
# The HTTP server will key sessions off the bearer token instead.
_STDIO_SESSION = "stdio-local"


def default_state_root() -> Path:
    env = os.environ.get("DKU_MCP_STATE_ROOT")
    if env:
        return Path(env)
    return Path(tempfile.gettempdir()) / "dku-mcp"


def _resolve_local_workdir() -> str:
    """Working dir for local (stdio) execution: the user's project directory.

    Defaults to the server process's CWD — for a stdio server spawned by the
    agent harness, that's the directory the user launched the agent in, so the
    agent's relative paths to local files (``./data.csv`` for an upload, etc.)
    resolve where the user expects. Overridable with ``DKU_MCP_WORKDIR``.
    """
    return os.environ.get("DKU_MCP_WORKDIR", "").strip() or os.getcwd()


def _resolve_dss_url() -> str:
    """Resolve the DSS backend URL from explicit or Code Studio env."""
    url = os.environ.get("DKU_URL", "").strip()
    if url:
        return url.rstrip("/")

    protocol = os.environ.get("DKU_BASE_PROTOCOL", "").strip()
    host = (
        os.environ.get("DKU_SERVER_HOST") or os.environ.get("DKU_BACKEND_HOST") or ""
    ).strip()
    port = os.environ.get("DKU_BASE_PORT", "").strip()
    if protocol and host and port:
        return f"{protocol}://{host}:{port}".rstrip("/")
    return ""


def _resolve_request_auth(*, is_http: bool) -> dict:
    """Resolve DSS auth + session id for this call (model A — per-user identity).

    ``is_http`` is the SERVER's transport mode (the server knows it), NOT inferred
    from whether a request context happens to be available — so a hosted HTTP
    server can never silently fall back to the pod's own credential.

    HTTP transport: the ``Authorization: Bearer`` token IS the caller's DSS API
    key, so every ``dku`` command runs as that user (their permissions + audit).
    The pod's own injected credential is never used for HTTP callers, and the
    session is keyed off the bearer so concurrent users get isolated workdirs. If
    the request context is unavailable (no bearer extractable), we return an
    empty key — NEVER the pod env key — so ``dku_exec`` rejects with the
    auth-required error rather than running as the pod owner.

    stdio transport: the agent is the pod owner — fall back to the pod's injected
    key (``DKU_API_KEY``, set by the Code Studio startup from ``DKU_API_TICKET``).
    """
    url = _resolve_dss_url()

    if is_http:
        request = None
        try:
            from fastmcp.server.dependencies import get_http_request

            request = get_http_request()
        except Exception:
            request = None

        api_key = ""
        if request is not None:
            header = (request.headers.get("authorization") or "").strip()
            parts = header.split(maxsplit=1)
            if len(parts) == 2 and parts[0].lower() == "bearer":
                api_key = parts[1].strip()
            if not api_key:
                # Some reverse proxies strip Authorization; accept an explicit
                # key header as a fallback so model A still works through them.
                api_key = (
                    request.headers.get("x-dku-api-key")
                    or request.headers.get("x-api-key")
                    or ""
                ).strip()
        # No fallback to the pod's DKU_API_KEY here: on HTTP the only acceptable
        # identity is the caller's bearer. A missing bearer yields an empty key,
        # which dku_exec turns into the auth-required error.
        return {
            "url": url,
            "api_key": api_key,
            "mode": "bearer",
            "session_id": f"bearer:{api_key}" if api_key else "anon",
            "is_http": True,
        }

    # stdio transport: the agent is the pod owner.
    api_key = (
        os.environ.get("DKU_API_KEY") or os.environ.get("DKU_API_TICKET") or ""
    ).strip()
    return {
        "url": url,
        "api_key": api_key,
        "mode": "pod",
        "session_id": _STDIO_SESSION,
        "is_http": False,
    }


def _require_fastmcp():
    try:
        from fastmcp import FastMCP

        return FastMCP
    except ModuleNotFoundError:
        from dku_cli.errors import exit_with_error

        exit_with_error(
            "The MCP server requires the optional 'mcp' extra (fastmcp).",
            details=[
                "Install the MCP runtime with:",
                "  pip install fastmcp",
                "(or install the dataiku-headless 'mcp' extra during the block build)",
                "Then re-run: dku-mcp serve",
            ],
            status=1,
        )


def build_server(
    *,
    state_root: str | None = None,
    sandbox: str = "auto",
    allow_network: bool = True,
    mode: str = "hosted",
    is_http: bool = False,
    backend: SandboxBackend | None = None,
):
    """Construct (but do not run) the FastMCP server.

    ``mode`` sets the executor's trust level: ``local`` (single-user stdio —
    permissive: full env, the user's project dir, no sandbox/sanitize) or
    ``hosted`` (multi-tenant HTTP — locked down). ``run_server`` derives it from
    the transport; tests construct either explicitly.

    ``is_http`` is the server transport mode threaded into ``_resolve_request_auth``
    so an HTTP server never falls back to the pod's own credential.

    ``backend`` lets the caller pass an already-resolved sandbox backend so the
    bubblewrap user-namespace probe runs ONCE per serve (the CLI safety check and
    this builder otherwise probe it twice). When ``None``, it is selected here.
    """
    FastMCP = _require_fastmcp()

    if backend is None:
        backend_preference = (
            "subprocess" if mode == "local" and sandbox == "auto" else sandbox
        )
        backend = select_backend(backend_preference, allow_network=allow_network)
    store = SessionStore(Path(state_root) if state_root else default_state_root())
    audit = AuditLog(store.root / "audit" / "exec.jsonl")

    mcp = FastMCP("Dataiku dku")

    @mcp.tool()
    def dku_exec(commands: str, project: str = "", timeout: int = 180) -> str:
        """Run dku/bash/python in an authed shell.

        Send a multi-line bash script — chain several `dku` commands, build JSON
        payloads with heredocs, pipe through `jq`/`python3`. The reply is plain
        text: an `exit N` header line, then raw stdout, then a `--- stderr ---`
        section if anything was printed there. Filter or aggregate large output
        before printing.

        Local MCP install (stdio): this runs as YOU, in your current project
        directory, with full filesystem + environment access — so you can act on
        local files: e.g. `dku dataset create-from-file sales ./data/sales.csv`
        to load a CSV, `dku folder upload MYFOLDER ~/Downloads/x.parquet`, or
        `dku dataset download out_ds result.csv` to pull DSS data back to disk.

        Auth (model A): every `dku` command runs as the DSS user whose key is
        configured (your own personal API key), with their permissions + audit.
        """
        # Clamp the agent-supplied timeout: it caps the sandbox wall-clock and
        # CPU ulimit, so an unbounded value could pin one exec for days.
        timeout = max(1, min(int(timeout), 1800))
        auth = _resolve_request_auth(is_http=is_http)
        if auth["is_http"] and not auth["api_key"]:
            return executor.result_to_text(
                executor.ExecResult(
                    exit_code=1,
                    stdout="",
                    stderr=(
                        "Authentication required: send 'Authorization: Bearer "
                        "<YOUR_DSS_PERSONAL_API_KEY>'. Every dku command runs as "
                        "that DSS user. Create a personal key in DSS under "
                        "Profile & settings > API keys."
                    ),
                    duration_ms=0,
                    truncated=False,
                )
            )
        # Defensive guard against the latent "anon" shared-session risk: the
        # empty-bearer rejection above is the ONLY thing that keeps the shared
        # "anon" session id (minted in _resolve_request_auth when no key is
        # extractable) from reaching get_or_create and handing every
        # unauthenticated HTTP caller one shared workdir. If a future refactor
        # ever weakens that guard, fail loud here rather than silently sharing.
        if auth["is_http"] and auth["session_id"] == "anon":
            raise AssertionError(
                "refusing to create the shared 'anon' session for an "
                "unauthenticated HTTP caller"
            )
        session = store.get_or_create(auth["session_id"])
        # Local mode runs in the user's project dir (relative paths to their
        # files work); hosted mode falls back to the isolated session workdir.
        cwd = _resolve_local_workdir() if mode == "local" else None
        # Lease the session so LRU eviction can't delete its workdir while
        # this command is still running in it.
        with store.lease(session):
            result = executor.run_exec(
                commands,
                session=session,
                backend=backend,
                mode=mode,
                cwd=cwd,
                project=project or None,
                timeout=timeout,
                audit=audit,
                dss_auth=auth,
            )
        return executor.result_to_text(result)

    return mcp


def run_server(
    *,
    transport: str = "stdio",
    host: str = "127.0.0.1",
    port: int = 5050,
    state_root: str | None = None,
    sandbox: str = "auto",
    allow_network: bool = True,
    behind_proxy: bool = False,
    proxy_prefix_env: str = "",
    public_url: str = "",
    landing: bool = True,
    mode: str = "auto",
    backend: SandboxBackend | None = None,
) -> None:
    """Build and run the server on the given transport.

    ``mode`` selects the executor trust level; ``auto`` derives it from the
    transport — ``stdio`` → ``local`` (permissive, single-user), ``http`` →
    ``hosted`` (locked down, multi-tenant).

    ``backend`` lets the CLI pass the sandbox backend it already resolved for its
    insecure-sandbox safety check, so the bubblewrap user-namespace probe runs
    once per serve rather than twice.

    For HTTP the app is assembled through ``mcp.http`` so it can sit behind the
    DSS Code Studio reverse proxy (path-prefix stripping) and serve a connect-info
    landing page for external agent harnesses.
    """
    resolved_mode = (
        mode
        if mode in ("local", "hosted")
        else ("local" if transport == "stdio" else "hosted")
    )
    # Invariant: HTTP transport is ALWAYS hosted. local trust hands the full host
    # env (incl. the injected DSS credential) to the agent shell and drops
    # sanitize + ulimits — it must never back a network-reachable executor, even
    # if a caller passes mode="local" explicitly. The CLI rejects this earlier
    # with a prescriptive error; this is the programmatic backstop.
    is_http = transport in ("http", "streamable-http")
    if is_http:
        resolved_mode = "hosted"
    mcp = build_server(
        state_root=state_root,
        sandbox=sandbox,
        allow_network=allow_network,
        mode=resolved_mode,
        is_http=is_http,
        backend=backend,
    )
    if transport == "stdio":
        mcp.run(transport="stdio")
    elif is_http:
        from dku_cli.mcp import http as mcp_http

        # Reuse the backend the builder resolved (it stores it on no public
        # attribute, so re-resolve only if the caller passed nothing). Selecting
        # here would re-probe; pass the CLI-resolved backend through instead.
        backend_name = backend.name if backend is not None else sandbox
        app = mcp_http.build_http_app(
            mcp,
            mcp_path="/mcp",
            behind_proxy=behind_proxy,
            proxy_prefix_env=proxy_prefix_env,
            port=port,
            landing=landing,
            public_url=public_url,
            backend=backend_name,
        )
        mcp_http.run_http_app(app, host=host, port=port)
    else:
        raise ValueError(f"Unknown transport: {transport!r} (use stdio or http)")
