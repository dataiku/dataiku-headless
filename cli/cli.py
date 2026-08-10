"""``dataiku-headless`` command-line interface.

Subcommand:

* ``serve`` — run the FastMCP server (the default when no subcommand is given, preserving the legacy ``dataiku-headless`` behavior).

Skills ship in the plugin's standard ``skills/`` directory. Claude Code discovers that directory automatically, Codex discovers it through the root Agent Plugins package, and Cortex Code consumes the compatible Claude plugin layout. Anyone cloning this repo directly already has ``skills/`` on disk to point their harness at, so this CLI doesn't duplicate that as a copy command.
"""

from __future__ import annotations

import typer

app = typer.Typer(
    name="dataiku-headless",
    help="Headless Dataiku agent kit — run the MCP server.",
    rich_markup_mode="rich",
    no_args_is_help=False,
    add_completion=False,
)


# ---------------------------------------------------------------------------
# serve  (+ legacy default)
# ---------------------------------------------------------------------------


@app.command()
def serve() -> None:
    """Run the Dataiku FastMCP server over stdio."""
    from dataiku_mcp import run_server

    run_server()


@app.callback(invoke_without_command=True)
def _main(ctx: typer.Context) -> None:
    """Run the MCP server when invoked with no subcommand (legacy behavior)."""
    if ctx.invoked_subcommand is None:
        serve()


if __name__ == "__main__":
    app()
