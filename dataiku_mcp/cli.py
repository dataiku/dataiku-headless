"""Command-line interface for the Dataiku MCP server."""

import argparse
from importlib.metadata import version
from typing import Sequence

from . import run_server


def main(argv: Sequence[str] | None = None) -> None:
    """Parse command-line arguments and run the MCP server."""
    parser = argparse.ArgumentParser(
        prog="dataiku-headless",
        description="Run the Dataiku MCP server over stdio.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {version('dataiku-headless')}",
    )
    parser.parse_args(argv)
    run_server()
