"""Launcher for the dku MCP server — ``python -m dku_cli.mcp`` or the ``dku-mcp`` script.

This is intentionally **not** registered on the main ``dku`` app. The MCP server
is infrastructure that *hosts* the CLI inside a Dataiku Code Studio, not a DSS
verb an agent types. Keeping it off the ``dku`` surface keeps the agent-facing
verb catalog clean.

Commands:
  - serve   start the MCP server (stdio for a local agent, http for remote)
  - doctor  preflight check (fastmcp, bubblewrap/userns, dku, auth)
"""

from __future__ import annotations

import typer

app = typer.Typer(
    name="dku-mcp",
    help="Dataiku dku MCP server — skill lookup + dku executor (code-mode).",
    no_args_is_help=True,
    add_completion=False,
)


@app.command()
def serve(
    transport: str = typer.Option(
        "stdio",
        "--transport",
        "-t",
        help="Transport: 'stdio' (local agent) or 'http' (remote)",
    ),
    host: str = typer.Option(
        "127.0.0.1", "--host", help="Bind host for http transport"
    ),
    port: int = typer.Option(5050, "--port", help="Bind port for http transport"),
    state_root: str = typer.Option(
        None,
        "--state-root",
        help="Per-session state dir (else DKU_MCP_STATE_ROOT / temp)",
    ),
    sandbox: str = typer.Option(
        "auto",
        "--sandbox",
        help="Executor sandbox: 'auto', 'bubblewrap', or 'subprocess'",
    ),
    no_network: bool = typer.Option(
        False, "--no-network", help="Cut sandbox network egress (bubblewrap only)"
    ),
    allow_insecure_sandbox: bool = typer.Option(
        False,
        "--allow-insecure-sandbox",
        help="Permit HTTP serving without bubblewrap isolation (UNSAFE; local testing only)",
    ),
    behind_proxy: bool = typer.Option(
        False,
        "--behind-proxy",
        help="Strip the DSS Code Studio reverse-proxy path prefix before routing (http)",
    ),
    proxy_prefix_env: str = typer.Option(
        "",
        "--proxy-prefix-env",
        help="Env var holding the proxy path prefix (default: DKU_CODE_STUDIO_BROWSER_PATH_<port>)",
    ),
    public_url: str = typer.Option(
        "", "--public-url", help="External base URL shown on the landing page (http)"
    ),
    no_landing: bool = typer.Option(
        False, "--no-landing", help="Disable the connect-info landing page at / (http)"
    ),
    trust: str = typer.Option(
        "auto",
        "--trust",
        help=(
            "Executor trust level: 'local' (permissive — full env, your project "
            "dir, no sandbox; default for stdio), 'hosted' (locked down — env "
            "scrub, isolated workdir, ulimits; default for http), or 'auto'"
        ),
    ),
) -> None:
    """Start the MCP server exposing dku_exec."""
    from dku_cli.errors import exit_with_error
    from dku_cli.mcp.server import run_server
    from dku_cli.output import info

    # Resolved once below for the HTTP safety check, then threaded into
    # run_server so the bubblewrap probe is not run twice per serve.
    resolved_backend = None

    if transport not in ("stdio", "http", "streamable-http"):
        exit_with_error(
            f"Unknown transport: {transport!r}.",
            code="bad_argument",
            details=[
                "Use --transport stdio (local agent) or --transport http (remote)."
            ],
            status=1,
        )

    if trust not in ("auto", "local", "hosted"):
        exit_with_error(
            f"Unknown trust level: {trust!r}.",
            code="bad_argument",
            details=["Use --trust local, --trust hosted, or --trust auto."],
            status=1,
        )

    # Refuse to expose the executor to remote agents without real isolation: the
    # subprocess fallback gives none, so it must never back an HTTP server.
    if transport in ("http", "streamable-http"):
        # local trust = full host env (incl. injected DSS credential), no
        # --dangerous sanitize, no ulimits — it must never back a network server.
        if trust == "local":
            exit_with_error(
                "Refusing --trust local on an HTTP transport.",
                code="bad_argument",
                details=[
                    "local trust runs the executor with your full environment, no",
                    "--dangerous sanitization, and no ulimits — unsafe for a",
                    "network-reachable server. Use --trust hosted (or auto) for http.",
                ],
                status=1,
            )

        from dku_cli.mcp.sandbox import select_backend

        resolved_backend = select_backend(sandbox, allow_network=not no_network)
        backend = resolved_backend
        if backend.name != "bubblewrap" and not allow_insecure_sandbox:
            exit_with_error(
                "Refusing to serve HTTP without bubblewrap isolation.",
                code="insecure_sandbox",
                details=[
                    f"Selected sandbox backend: {backend.name} (no kernel isolation).",
                    "HTTP exposes the executor to remote agents. Run it under bubblewrap:",
                    "  install bwrap + enable unprivileged user namespaces, then --sandbox bubblewrap",
                    "Override for trusted/local testing only: --allow-insecure-sandbox",
                ],
                status=1,
            )

    info(
        f"Starting dku MCP server (transport={transport}, sandbox={sandbox}, "
        f"trust={trust})…"
    )
    run_server(
        transport=transport,
        host=host,
        port=port,
        state_root=state_root,
        sandbox=sandbox,
        allow_network=not no_network,
        behind_proxy=behind_proxy,
        proxy_prefix_env=proxy_prefix_env,
        public_url=public_url,
        landing=not no_landing,
        mode=trust,
        backend=resolved_backend,
    )


@app.command()
def doctor(
    output: str = typer.Option(
        None, "--output", "-o", help="Output format: table or json"
    ),
) -> None:
    """Check MCP prerequisites: fastmcp, bubblewrap/userns, dku, auth env."""
    import os
    import shutil

    from dku_cli.mcp import sandbox
    from dku_cli.output import render, resolve_output_format

    fmt = resolve_output_format(output, allowed=("table", "json"), default="table")
    rows: list[dict] = []

    def check(name: str, ok: bool, detail: str) -> None:
        rows.append(
            {"check": name, "status": "ok" if ok else "MISSING", "detail": detail}
        )

    # fastmcp (the optional runtime dependency)
    try:
        import fastmcp  # noqa: F401

        check("fastmcp", True, "installed")
    except ModuleNotFoundError:
        check("fastmcp", False, "not installed — run: pip install fastmcp")

    # bubblewrap + unprivileged user namespaces
    bwrap_path = shutil.which("bwrap")
    if sandbox.probe_bubblewrap():
        check("bubblewrap", True, f"{bwrap_path} (userns works)")
    elif bwrap_path:
        check(
            "bubblewrap", False, f"{bwrap_path} present but userns blocked — falls back"
        )
    else:
        check("bubblewrap", False, "not installed — executor falls back to subprocess")

    selected = sandbox.select_backend("auto")
    is_secure = selected.name == "bubblewrap"
    check(
        "sandbox backend",
        is_secure,
        f"selected: {selected.name}"
        + ("" if is_secure else " — NOT isolated; install bubblewrap for multi-tenant"),
    )

    # dku on PATH (the executor shells out to it)
    dku_path = shutil.which("dku")
    check(
        "dku on PATH",
        bool(dku_path),
        dku_path or "not found — vendor the wheel in the block",
    )

    # auth env (executor inherits this; ticket OR key is enough)
    has_url = bool(os.environ.get("DKU_URL"))
    has_key = bool(os.environ.get("DKU_API_KEY") or os.environ.get("DKU_API_TICKET"))
    check(
        "DSS auth env",
        has_url and has_key,
        f"DKU_URL={'set' if has_url else 'unset'}, key/ticket={'set' if has_key else 'unset'}",
    )

    render(
        rows, ["check", "status", "detail"], output_format=fmt, title="dku-mcp doctor"
    )
