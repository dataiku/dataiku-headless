"""``dataiku-headless`` command-line interface.

Subcommands:

* ``initialize`` — copy the agent operating docs (``AGENTS.md``, ``CLAUDE.md``)
  and the full ``dataiku-skills`` library into a target project so an agent
  harness (Claude Code, Codex, …) can pick them up.
* ``serve`` — run the FastMCP server (the default when no subcommand is given,
  preserving the legacy ``dataiku-headless`` behavior).
"""

from __future__ import annotations

import importlib.metadata
import importlib.util
import re
import shutil
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

_VERSION_COMMENT = "<!-- dataiku-headless: {version} — run `dataiku-headless initialize --force` to upgrade -->"
_VERSION_RE = re.compile(r"<!--\s*dataiku-headless:\s*([\d.]+)")


def _installed_version() -> str:
    try:
        return importlib.metadata.version("dataiku-headless")
    except importlib.metadata.PackageNotFoundError:
        return "0.0.0"


def _write_doc(target: Path, src: Path, version: str) -> None:
    """Write *src* into *target* with a version header comment prepended."""
    content = src.read_text(encoding="utf-8").rstrip("\n")
    target.write_text(
        f"{_VERSION_COMMENT.format(version=version)}\n"
        f"{content}\n",
        encoding="utf-8",
    )


app = typer.Typer(
    name="dataiku-headless",
    help="Headless Dataiku DSS agent kit — initialize a project or run the MCP server.",
    rich_markup_mode="rich",
    no_args_is_help=False,
    add_completion=False,
)

console = Console()


# ---------------------------------------------------------------------------
# Source resolution
# ---------------------------------------------------------------------------

def _resolve_sources() -> tuple[Path, Path, Path]:
    """Return ``(AGENTS.md, CLAUDE.md, dataiku-skills/)`` source paths.

    Handles both layouts: a source checkout (docs + ``dataiku-skills`` at the
    repo root, next to this ``cli`` package) and an installed wheel (docs +
    ``skills`` force-included under the ``dataiku_mcp`` package). ``find_spec``
    locates the package without importing it, so resolution stays cheap.
    """
    candidates: list[tuple[Path, Path, Path]] = []

    # Source checkout: cli/ sits beside AGENTS.md, CLAUDE.md and dataiku-skills/.
    repo = Path(__file__).resolve().parent.parent
    candidates.append((repo / "AGENTS.md", repo / "CLAUDE.md", repo / "dataiku-skills"))

    # Installed wheel: hatchling force-includes the docs and skills under dataiku_mcp/.
    spec = importlib.util.find_spec("dataiku_mcp")
    if spec and spec.origin:
        pkg = Path(spec.origin).parent
        candidates.append((pkg / "AGENTS.md", pkg / "CLAUDE.md", pkg / "skills"))

    for agents, claude, skills in candidates:
        if agents.is_file() and claude.is_file() and skills.is_dir():
            return agents, claude, skills

    searched = "\n".join(f"  - {a.parent}" for a, _, _ in candidates)
    raise FileNotFoundError(
        "Could not locate the bundled AGENTS.md, CLAUDE.md and dataiku-skills/. "
        f"Looked in:\n{searched}"
    )


# ---------------------------------------------------------------------------
# initialize
# ---------------------------------------------------------------------------

def _warn_docs_merge(diverted: list[tuple[str, Path]]) -> None:
    """Print a prominent box telling the user to merge diverted docs.

    ``diverted`` is a list of ``(original_filename, headless_copy_path)`` pairs
    for docs that already existed in the target and were therefore preserved.
    """
    docs = " / ".join(original for original, _ in diverted)
    rows = "\n".join(
        f"  [bold cyan]{copy.name}[/]  →  merge into  [bold]{original}[/]"
        for original, copy in diverted
    )
    message = (
        f"The target folder already has its own [bold]{docs}[/], so your version "
        "was [bold]left untouched[/].\n\n"
        "To avoid overwriting it, the Dataiku headless docs were written as:\n"
        f"{rows}\n\n"
        "[bold]ACTION REQUIRED:[/] merge each headless copy into the file shown, "
        "then delete the copy.\n"
        "Your agent will not load the Dataiku operating instructions until you do."
    )
    console.print(
        Panel(
            message,
            title="[bold]⚠  MERGE REQUIRED  ⚠[/]",
            border_style="bold red",
            padding=(1, 4),
            expand=True,
        )
    )


@app.command()
def initialize(
    destination: Path | None = typer.Argument(
        None,
        help="Target directory to initialize. Prompted for if omitted.",
        show_default=False,
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Overwrite existing files / the dataiku-skills folder without prompting.",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Assume yes for all prompts (non-interactive).",
    ),
) -> None:
    """Copy [bold]AGENTS.md[/], [bold]CLAUDE.md[/] and the [bold]dataiku-skills[/] library into a directory."""
    agents_src, claude_src, skills_src = _resolve_sources()

    # Resolve the destination, prompting interactively when not supplied.
    if destination is None:
        answer = Prompt.ask(
            "[bold]Where should the Dataiku agent kit be installed?[/]",
            default=str(Path.cwd()),
            console=console,
        )
        destination = Path(answer)
    dest = destination.expanduser().resolve()

    # Guard against initializing into the directory we are copying *from*.
    if dest == agents_src.resolve().parent:
        console.print(
            f"[red]Refusing to initialize:[/] {dest} is the source directory for "
            "AGENTS.md / CLAUDE.md / dataiku-skills. Pick a different destination."
        )
        raise typer.Exit(code=1)

    console.print(
        Panel.fit(
            f"Destination: [bold cyan]{dest}[/]",
            title="dataiku-headless initialize",
            border_style="cyan",
        )
    )

    # Confirm creating a brand-new directory.
    if not dest.exists():
        if not (yes or Confirm.ask(f"Create [cyan]{dest}[/]?", default=True, console=console)):
            console.print("[yellow]Aborted.[/]")
            raise typer.Exit(code=1)
        dest.mkdir(parents=True, exist_ok=True)

    # Never overwrite an AGENTS.md / CLAUDE.md the target already owns.
    # Write our copy beside it as <NAME>_DATAIKU_HEADLESS.md and warn the user to merge.
    diverted: list[tuple[str, Path]] = []

    def _doc_entry(filename: str, src: Path) -> tuple[str, Path, Path, str]:
        target = dest / filename
        if not target.exists():
            return (filename, src, target, "file")
        diverted_target = target.with_name(f"{target.stem}_DATAIKU_HEADLESS{target.suffix}")
        diverted.append((filename, diverted_target))
        return (diverted_target.name, src, diverted_target, "file")

    plan = [
        _doc_entry("AGENTS.md", agents_src),
        _doc_entry("CLAUDE.md", claude_src),
        ("dataiku-skills/", skills_src, dest / "dataiku-skills", "dir"),
    ]

    # Detect conflicts and confirm overwrite once for the whole batch.
    conflicts = [(label, target) for label, _, target, _ in plan if target.exists()]
    if conflicts and not force:
        console.print("[yellow]The following already exist and will be overwritten:[/]")
        for label, target in conflicts:
            console.print(f"  • {target}")
        if not (yes or Confirm.ask("Overwrite?", default=False, console=console)):
            console.print("[yellow]Aborted.[/] Re-run with [bold]--force[/] to overwrite.")
            raise typer.Exit(code=1)

    # Copy everything.
    version = _installed_version()
    table = Table(show_header=True, header_style="bold", box=None)
    table.add_column("Item")
    table.add_column("Copied to", style="cyan")
    for label, src, target, kind in plan:
        if kind == "dir":
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(src, target)
        else:
            _write_doc(target, src, version)
        table.add_row(label, str(target))

    console.print(table)
    console.print(f"[bold green]✓ Initialized[/] (dataiku-headless {version}). Your agent harness can now load these instructions and skills.")

    if diverted:
        _warn_docs_merge(diverted)


# ---------------------------------------------------------------------------
# serve  (+ legacy default)
# ---------------------------------------------------------------------------

def _check_staleness(directory: Path) -> None:
    """Warn if AGENTS.md or CLAUDE.md in *directory* were written by an older package version."""
    installed = _installed_version()
    stale: list[str] = []
    for filename in ("AGENTS.md", "CLAUDE.md"):
        path = directory / filename
        if not path.exists():
            continue
        m = _VERSION_RE.search(path.read_text(encoding="utf-8"))
        if m and m.group(1) != installed:
            stale.append(f"{filename} ({m.group(1)})")
    if stale:
        console.print(
            f"[yellow]⚠ dataiku-headless {installed} installed but "
            f"{', '.join(stale)} {'is' if len(stale) == 1 else 'are'} out of date.[/]\n"
            "  Run [bold]dataiku-headless initialize --force[/] to upgrade."
        )


@app.command()
def serve() -> None:
    """Run the Dataiku FastMCP server (stdio or streamable-http per env config)."""
    _check_staleness(Path.cwd())

    from dataiku_mcp import run_server

    run_server()


@app.callback(invoke_without_command=True)
def _main(ctx: typer.Context) -> None:
    """Run the MCP server when invoked with no subcommand (legacy behavior)."""
    if ctx.invoked_subcommand is None:
        serve()


if __name__ == "__main__":
    app()
