"""Module entry point so the MCP server runs as ``python -m dku_cli.mcp``."""

from __future__ import annotations

from dku_cli.mcp.cli import app

if __name__ == "__main__":
    app()
