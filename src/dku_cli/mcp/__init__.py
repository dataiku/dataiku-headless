"""Dataiku ``dku`` MCP server.

The server exposes one tool:

- ``dku_exec`` — a pre-authed bash surface that runs batches of ``dku`` /
  ``jq`` / ``python`` commands and returns structured results. Hosted mode runs
  in an isolated per-agent sandbox; local stdio mode runs with local trust.

This package is import-safe without the optional ``mcp`` extra: only
``server.build_server`` imports ``fastmcp`` (lazily), so ``dku``'s other
commands keep working when the extra is not installed.

See ``dataiku-mcp/README.md`` for the packaging/runtime notes.
"""

from __future__ import annotations

__all__ = [
    "audit",
    "executor",
    "policy",
    "sandbox",
    "sessions",
]
