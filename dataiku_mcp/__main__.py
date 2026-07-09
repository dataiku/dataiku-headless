"""Entry point for running the Dataiku MCP server as a module.

Usage:
    python -m dataiku_mcp
"""

from . import run_server

if __name__ == "__main__":
    run_server()
