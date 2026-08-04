"""Entry point for running the Dataiku MCP server as a module.

Usage:
    python -m dataiku_mcp
"""

from .cli import main

if __name__ == "__main__":
    main()
